# USF Guessr: Design Doc

> **usfguessr.com** (usfguesser.com redirects to it). A GeoGuessr-style game for the USF Tampa campus: you see a photo taken somewhere on campus, drop a pin where you think it was taken, and score points based on how close you were.

This doc is the shared source of truth for the project. If you use an AI assistant, give it this whole file first (see [Working with AI assistants](#14-working-with-ai-assistants)).

---

## 1. Goals

- **Real users:** launch to USF students in the first week of the Spring 2027 semester.
- **Portfolio quality:** a production-grade Python backend, SQL with PostGIS, Docker, AWS, Terraform, and CI/CD.
- **Learning:** every contributor understands the code they ship.

**Not in v1:** native mobile apps, multiple campuses, payments, real-time multiplayer.

---

## 2. Product

### Game modes
- **Daily challenge:** the same 3 photos for everyone each day. Round 1 is easy, round 2 medium, round 3 hard. One attempt per player per day, with a shareable result (Wordle-style).
- **Practice:** unlimited random rounds. Doesn't count toward the leaderboard.

### Core loop
1. A photo is shown, with a campus map below it.
2. The player drops a pin and submits.
3. The server scores the guess, then reveals the true location, the distance, the score, and a line between the two pins.
4. After round 3: total score, rank, and a share button.

### Scoring
- 5,000 points max per round, 15,000 per daily challenge.
- Distance of 10 m or less: 5,000 points. 1,500 m or more: 0 points.
- In between: exponential decay. Starting formula: `round(5000 * exp(-(d - 10) / 300))`, where `d` is in meters. Tune after playtesting.
- Scoring lives in one function in `backend/app/services/scoring.py`, with unit tests.

### Accounts: guest-first
- **No sign-in popup, ever.** Opening the site drops you straight into round 1 of today's challenge.
- On the first visit, the server issues an anonymous `guest_id` in an httpOnly cookie, and all of that player's games are saved under it.
- **Google sign-in is optional** and unlocks a name on the leaderboard, streaks that sync across devices, and photo submissions.
- On sign-in, the player's existing guest games are claimed by their account, so no progress is lost.
- Sign-in is encouraged with **inline banners at good moments**, never blocking modals:
  - Final results: "You scored 12,400, which would be #37 today. Sign in to put your name on the leaderboard."
  - Leaderboard: a placeholder row for them, "You (guest): would be #37."
  - Streaks: "3-day streak! Sign in so you don't lose it if you switch devices."
- The leaderboard only shows signed-in players.

### Photo submissions (launch feature)
- Signed-in users only, which cuts down on spam.
- Flow: upload a photo, drop a pin at the true location, add an optional note.
- The server runs automatic checks, then an admin approves or rejects it and sets its difficulty.
- **Submission rules:** on the Tampa campus; outdoors or public indoor spaces only; no identifiable people as the subject; no restricted areas.

### Admin
- **Review queue:** shows the photo, the submitter's pin, the location from the photo's GPS metadata if present, and automatic flags (duplicate, blurry, GPS mismatch, missing GPS, outside campus). Actions: approve with a difficulty (easy, medium, or hard), or reject with a reason.
- Nice to have: manually choose a day's daily challenge photos.

---

## 3. Architecture

```
Player's browser
      │
  CloudFront (CDN + HTTPS, one domain)
   ├── S3: frontend build + processed photos
   └── /api/* → EC2 instance (Docker Compose)
                 ├── api      (FastAPI + uvicorn)
                 ├── worker   (RQ: photo processing, nightly jobs)
                 ├── redis    (job queue)
                 └── db       (Postgres + PostGIS)

GitHub Actions: lint, type-check, test, build, deploy
Terraform:      creates and manages all AWS resources
```

The same containers run locally (Docker Compose), in CI, and in production.

---

## 4. Tech stack

| Area | Choice |
|---|---|
| Frontend | React + TypeScript (Vite `react-ts` template), Tailwind CSS, React Router, react-leaflet |
| Map tiles | Hosted provider with a free tier (MapTiler, Stadia Maps, or Carto). Attribution required. Don't use OpenStreetMap's public tile servers. |
| Backend | Python 3.11, FastAPI, Pydantic, SQLAlchemy 2, Alembic, GeoAlchemy2, psycopg, pydantic-settings |
| Database | PostgreSQL + PostGIS |
| Jobs | Redis + RQ |
| Images | Pillow + pillow-heif (iPhone HEIC support) |
| Auth | Google sign-in via Authlib; session in an httpOnly cookie |
| Storage | S3 (presigned uploads), CloudFront |
| Domains and DNS | Cloudflare Registrar and DNS: usfguessr.com (main), usfguesser.com (301 redirect) |
| Hosting | EC2 running Docker Compose (v1) |
| Infra as code | Terraform (state in S3 with native locking) |
| CI/CD | GitHub Actions; AWS access through OIDC (no stored keys) |
| Monitoring | Sentry (errors), CloudWatch (logs) |
| Python tooling | uv (`uv sync --locked`), Ruff, mypy (strict, Pydantic plugin), pytest, httpx2 |
| JS tooling | npm, ESLint |

---

## 5. Data model

All locations use PostGIS `geography(Point, 4326)` (longitude/latitude), with GiST indexes. Distances use `ST_Distance` on geography, which returns meters.

**campuses**
- `id`, `slug`, `name`, `boundary` (geography polygon), `created_at`
- Only USF Tampa in v1, but `campus_id` is on everything so multiple campuses are easy later.

**users**
- `id`, `google_sub` (unique), `email`, `display_name`, `is_admin`, `created_at`

**photos**
- `id`, `campus_id`, `s3_key`, `location` (point, the true spot)
- `difficulty`: `easy` / `medium` / `hard` (null until approved)
- `status`: `pending` / `approved` / `rejected`
- `source`: `admin` / `submission`
- `submitted_by` (user, nullable), `exif_location` (point, nullable), `flags` (jsonb), `reject_reason`
- `created_at`, `reviewed_at`, `reviewed_by`

**daily_challenges**
- `id`, `campus_id`, `date` (unique per campus)

**daily_challenge_photos**
- `daily_challenge_id`, `round_number` (1–3), `photo_id`

**games**
- `id`, `campus_id`, `mode` (`daily` / `practice`), `daily_challenge_id` (nullable)
- `user_id` (nullable), `guest_id` (nullable). At least one is required.
- `total_score`, `started_at`, `completed_at`
- Unique: one daily game per `(daily_challenge_id, user_id)` and per `(daily_challenge_id, guest_id)`

**guesses**
- `id`, `game_id`, `photo_id`, `round_number`, `guess_location` (point), `distance_m`, `score`, `created_at`
- Log every guess. That data enables automatic difficulty calibration later.

---

## 6. API

All routes are under `/api`, return JSON, and use lowercase, plural, hyphenated paths.

**Core rule: never send a photo's true location to the client before that round's guess is submitted.**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | API and database status |
| POST | `/api/games` | Start a game. Body: `{ "mode": "daily" \| "practice" }`. Returns the game ID and the first round's photo URL. Resumes today's daily if one already exists. |
| GET | `/api/games/{game_id}` | Current game state |
| POST | `/api/games/{game_id}/guesses` | Submit a guess: `{ "round_number", "lat", "lng" }`. Returns distance, score, true location, and the next photo. |
| GET | `/api/leaderboard/daily?date=` | Daily leaderboard (signed-in players only), plus the current player's would-be rank |
| GET | `/api/auth/google/login` | Start Google sign-in |
| GET | `/api/auth/google/callback` | Finish sign-in, create a session, claim guest games |
| POST | `/api/auth/logout` | End the session |
| GET | `/api/me` | Current player: signed-in user or guest, plus stats and streak |
| POST | `/api/submissions/upload-url` | Get a presigned S3 upload URL (signed-in users only) |
| POST | `/api/submissions` | Create a submission: `{ "s3_key", "lat", "lng", "note" }` |
| GET | `/api/submissions/mine` | The player's own submissions and their status |
| GET | `/api/admin/submissions?status=pending` | Review queue (admins only) |
| POST | `/api/admin/submissions/{id}/approve` | Approve: `{ "difficulty" }` |
| POST | `/api/admin/submissions/{id}/reject` | Reject: `{ "reason" }` |

The daily challenge resets at **midnight America/New_York**.

---

## 7. Background jobs (worker)

**process_submission** (queued when a submission is created)
1. Download the original from S3.
2. Decode it, including HEIC.
3. Read GPS metadata if present, then **strip all metadata**.
4. Resize (about 1600 px on the long edge) and make a thumbnail. Save the processed versions.
5. Compute a perceptual hash, and flag near-duplicates of existing photos.
6. Compute a blur score, and flag blurry photos.
7. Compare the GPS location to the submitter's pin. Flag a mismatch over about 75 m.
8. Check that the pin is inside the campus boundary.
9. Save the flags. **Missing GPS is a flag for manual review, not a rejection.**

**pick_daily_challenge** (nightly, before midnight ET)
- Pick one approved photo per difficulty that hasn't been used in the last N days.

**backup_db** (nightly)
- `pg_dump` to S3.

---

## 8. Frontend

### Routes
- `/`: today's daily challenge, playable immediately
- `/practice`
- `/leaderboard`
- `/submit`: shows a sign-in prompt inline if signed out
- `/admin`: admins only
- How-to-play and other links live in a small menu

### Main components
`PhotoViewer`, `GuessMap` (react-leaflet), `RoundResult`, `FinalResult` (with share), `SignInBanner`, `Leaderboard`, `SubmitForm`, `AdminQueue`

### Layout and design
- **Footer on every page:** "Not affiliated with the University of South Florida." Never use USF logos or official marks.
- **Mobile-first:** photo on top, map below, with a toggle to expand the map. Most players will arrive from a link on their phone.
- First visit: a one-line hint above the map ("Tap where you think this photo was taken"), not a popup.
- **Design rules:**
  - USF green and gold (check the USF brand guide for exact colors), plus neutrals
  - One display font and one body font
  - Tailwind's spacing scale, used consistently
  - No purple gradients, glassy cards, or emoji headings
  - Copy with local personality
- All API calls go through one module, `src/api/`.

---

## 9. Security and privacy

- Strip all metadata from photos before serving them.
- All scoring happens on the server. Rate-limit guesses and uploads.
- Cookies are httpOnly, Secure, and SameSite.
- Presigned uploads have a size limit, allowed content types, and a short expiry.
- Secrets come from environment variables locally and from AWS in production. **Never commit `.env`.**
- Store only the minimum user data: Google ID, email, display name.

---

## 10. Infrastructure and deployment

**Local**
- `docker compose up` runs the API, worker, Postgres with PostGIS, and Redis.
- The `postgis/postgis` image is amd64-only, so Compose sets `platform: linux/amd64` (emulated on Apple Silicon). Postgres 18 images mount data at `/var/lib/postgresql`.
- The frontend runs with `npm run dev`, which proxies `/api` to the backend.
- Photo storage goes through an interface: local disk in development, S3 in production.

**Production v1**
- One EC2 instance running Docker Compose. Use an x86 type (e.g. `t3`), not ARM `t4g`, because the PostGIS image is amd64-only.
- S3 and CloudFront for the frontend and photos
- Cloudflare DNS for both domains. Records pointing at CloudFront are **DNS only** (gray cloud), never proxied, to avoid two CDNs.
- ACM certificate in us-east-1 for CloudFront, validated with a DNS record added in Cloudflare
- Nightly database backups to S3
- CloudWatch logs and Sentry

**CI** (GitHub Actions, on every push and pull request, with no `paths` filters so required checks always report)
- `backend.yml`: `ruff check`, `ruff format --check`, `mypy`, `pytest`
- `frontend.yml`: `npm ci`, `npm run lint`, `npm run build`

**CD** (added in phase 4, on merge to main)
- Build images, push them to ECR, then deploy through SSM: run `alembic upgrade head`, then `docker compose pull && docker compose up -d`.
- Frontend: build, sync to S3, invalidate the CloudFront cache.

**AWS account:** create it in **late December**. New accounts on the Free plan get up to $200 in credits but expire after 6 months, so a late-December start covers launch and the whole spring semester. Turn on MFA and set a $10 budget alert right away.

**Later:** move to RDS and ECS once traffic justifies it, and move photo processing to an S3-triggered Lambda function.

---

## 11. Repo layout

```
USF-Guesser/
├── README.md
├── DESIGN.md
├── LICENSE
├── .env.example
├── docker-compose.yaml
├── .github/workflows/
│   ├── backend.yml
│   └── frontend.yml
├── backend/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── Dockerfile
│   ├── alembic/
│   ├── app/
│   │   ├── main.py        # creates the app and includes routers
│   │   ├── config.py      # settings from environment variables
│   │   ├── db.py          # engine and sessions
│   │   ├── routers/       # thin HTTP endpoints
│   │   ├── services/      # game logic: scoring, photo selection
│   │   ├── models/        # SQLAlchemy tables
│   │   ├── schemas/       # Pydantic request/response shapes
│   │   └── worker/        # background jobs
│   └── tests/
├── frontend/
│   ├── package.json
│   └── src/
│       ├── api/           # all calls to the backend
│       ├── components/
│       ├── pages/
│       └── types/
└── infra/                 # Terraform (phase 4)
```

---

## 12. Conventions

**Git and GitHub**
- One GitHub Issue per task, tracked on the GitHub Projects board.
- One branch per issue: `feature/short-name` or `fix/short-name`.
- Pull requests link their issue, need 1 review plus green CI, and are squash-merged.
- Commit messages follow Conventional Commits: `feat:`, `fix:`, `chore:`, `ci:`, `docs:`, `test:`.

**Python**
- Ruff with rules `E, F, I, B, UP`; Black-style formatting with `ruff format`.
- mypy strict mode, with type hints everywhere, tests included.
- Routers stay thin; logic goes in `services/`.
- Tests run against a real Postgres database, not mocks.

**TypeScript**
- Strict TypeScript and ESLint.

**API**
- Lowercase, plural, hyphenated paths. Use HTTP methods for actions, not verbs in the path.

**Dependencies**
- Add with `uv add` or `npm install`, and commit the lockfiles.
- Explain any new dependency in the pull request.

---

## 13. Dev setup

**Backend** (from `backend/`)
```
uv sync
uv run uvicorn app.main:app --reload    # http://localhost:8000, docs at /docs
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy app tests
```

**Frontend** (from `frontend/`)
```
npm install
npm run dev        # http://localhost:5173
npm run lint && npm run build
```

**Everything** (from the repo root)
```
cp .env.example .env    # then fill in your own values
docker compose up --build
curl localhost:8000/api/health
```
To run uvicorn outside Docker, set `DATABASE_URL` with `localhost` instead of `db` as the host.

---

## 14. Working with AI assistants

**This is a learning project.** If you're an AI assistant reading this doc:

- **Teach, don't just do.** Explain concepts, give hints and skeletons with blanks, and review code the contributor wrote. Only write complete features when explicitly asked.
- **Follow this doc.** Use the stack, data model, API shape, and conventions above. If you think a design decision is wrong, say so and explain why. Don't silently change it.
- **Don't add dependencies or change the architecture** without flagging it for discussion first.
- **Keep changes small** and scoped to one issue, so each pull request is easy to review.
- Remind contributors to run lint, type checks, and tests before pushing.

---

## 15. Tasks

Tags: **[BE]** backend, **[FE]** frontend, **[INFRA]** infrastructure, **[CONTENT]** photos and copy. Each task should become a GitHub Issue.

### Phase 0: Foundation (now through mid-December)
- [x] [INFRA] Repo, license, `.gitignore`
- [x] [BE] Backend project with uv
- [x] [BE] `/health` endpoint and test
- [x] [BE] Ruff and mypy configured
- [x] [INFRA] Backend CI workflow
- [x] [FE] Frontend scaffold (Vite React + TypeScript)
- [x] [INFRA] Frontend CI workflow running green
- [x] [INFRA] Remove `paths` filters from both workflows; make both checks required in the ruleset
- [x] [BE] Swap `httpx` for `httpx2` in dev dependencies
- [x] [BE] mypy strict mode; type-check `tests/` in CI
- [ ] [FE] Install Tailwind, React Router, and react-leaflet
- [x] [BE] Backend Dockerfile
- [x] [INFRA] `docker-compose.yaml` with API, PostGIS database, and Redis
- [x] [BE] Settings with pydantic-settings and a database session; `/api/health` checks the database
- [ ] [BE] Alembic setup and first migration (all tables in section 5)
- [ ] [BE] Seed script: USF Tampa campus with its boundary polygon
- [ ] [BE] PostGIS distance query with a database-backed test; PostGIS service container in CI
- [ ] [CONTENT] Take 100–200 campus photos with locations, tagged easy, medium, or hard
- [ ] [FE] Choose a map tile provider and get an API key
- [x] [CONTENT] Pick the final name and buy domains (usfguessr.com, usfguesser.com)

### Phase 1: Core game (winter break, weeks 1–2)
- [ ] [BE] Scoring function with unit tests (perfect, close, far, and cutoff cases)
- [ ] [BE] Storage interface: local disk in development, S3 in production
- [ ] [BE] Photo import script: local photo folder to storage plus database rows
- [ ] [BE] Guest ID cookie middleware
- [ ] [BE] Daily challenge model and selection logic
- [ ] [BE] Game and guess endpoints, keeping true locations hidden until each guess
- [ ] [FE] `GuessMap` component: campus map with click-to-place pin
- [ ] [FE] `PhotoViewer` component
- [ ] [FE] Play page connected to the API
- [ ] [FE] `RoundResult`: both pins, the line between them, distance, and score
- [ ] [FE] `FinalResult` with share text
- [ ] [FE] Mobile layout, plus the first-visit hint
- [ ] [FE] Site footer with non-affiliation disclaimer
- [ ] [BE] Practice mode

### Phase 2: Accounts and leaderboard (weeks 2–3)
- [ ] [BE] Google sign-in with Authlib, the users table, and session cookies
- [ ] [BE] Claim guest games on sign-in
- [ ] [BE] `/api/me` with stats and streak
- [ ] [BE] Daily leaderboard endpoint, including the player's would-be rank
- [ ] [FE] Leaderboard page with the guest placeholder row
- [ ] [FE] `SignInBanner` on the final results, leaderboard, and streak screens
- [ ] [BE] Streak calculation

### Phase 3: Submissions and moderation (week 3)
- [ ] [BE] Presigned upload endpoint with size and type limits
- [ ] [FE] Submit page: upload a photo and drop a pin
- [ ] [BE] Redis and RQ worker in Docker Compose
- [ ] [BE] `process_submission` job: HEIC decoding, metadata read and strip, resizing, duplicate and blur checks, GPS and boundary checks
- [ ] [BE] Admin approve and reject endpoints
- [ ] [FE] Admin review queue page
- [ ] [BE] Nightly `pick_daily_challenge` job
- [ ] [BE] Rate limiting on guesses and uploads

### Phase 4: Deploy (week 4)
- [ ] [INFRA] Create the AWS account (late December): MFA, a $10 budget alert, and an IAM user for daily use
- [ ] [INFRA] Terraform: state bucket, photo and frontend buckets, CloudFront, EC2, security groups, IAM roles, ACM
- [ ] [INFRA] Production Docker Compose file and secrets
- [ ] [INFRA] CD workflow with OIDC
- [ ] [INFRA] Nightly database backups to S3
- [ ] [INFRA] Sentry and CloudWatch logs
- [ ] [INFRA] Domain and HTTPS: Cloudflare DNS records (DNS only) to CloudFront, ACM validation record
- [ ] [INFRA] Redirect usfguesser.com to usfguessr.com (proxied placeholder records plus a 301 Redirect Rule)

### Phase 5: Launch (first week of spring semester)
- [ ] [CONTENT] Playtest with friends; tune the scoring curve
- [ ] [CONTENT] README with a demo GIF and architecture diagram
- [ ] [CONTENT] Submission rules and privacy page
- [ ] [CONTENT] Launch posts: r/USF, club Discords, International Student Services
- [ ] [INFRA] Monitor errors and AWS costs

### Backlog (after launch)
- Multiple campuses, then a USF vs. UCF rivalry mode
- Indoor rounds with floor guessing
- Automatic difficulty from player data
- Place recognition embeddings for duplicate and difficulty detection
- Move photo processing to an S3-triggered Lambda
- Move to RDS and ECS
- Archive of past daily challenges
- Microsoft sign-in

---

## 16. Ownership

Not assigned yet. Areas to split:
1. **Frontend game UI:** phase 1 and 2 frontend tasks
2. **Backend game API:** phase 1 and 2 backend tasks
3. **Submissions and worker:** phase 3
4. **Infrastructure and deployment:** phase 4

Jordan owns infrastructure, reviews all pull requests, and covers any area left unassigned.

## 17. Open decisions
- Map tile provider
- Scoring curve constants (after playtesting)
- How many photos to launch with
