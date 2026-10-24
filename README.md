# USF Guessr

A GeoGuessr-style game for the USF Tampa campus. You see a photo taken somewhere on campus, drop a pin where you think it was taken, and score points based on how close you were.

**Status:** in early development. Launching at [usfguessr.com](https://usfguessr.com) in spring 2027.

## Planned features

- **Daily challenge:** the same 3 photos for everyone each day, from easy to hard, with a shareable score
- **Practice mode:** unlimited random rounds
- **Play instantly:** no sign-up needed. Sign in with Google to join the leaderboard and keep streaks across devices.
- **Photo submissions:** players add their own campus spots, checked automatically and reviewed before going live

## Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL + PostGIS
- **Frontend:** React, TypeScript, Vite, Leaflet
- **Infrastructure:** Docker, GitHub Actions, AWS (EC2, S3, CloudFront), Terraform

## Progress

- [x] FastAPI backend with a database-backed health check
- [x] Docker Compose stack: API, Postgres with PostGIS, Redis
- [x] CI on every pull request: linting, strict type checking, tests
- [ ] Database schema and migrations
- [ ] Core game: photos, guessing, scoring
- [ ] Accounts and leaderboard
- [ ] Photo submissions
- [ ] Deploy to AWS

## Running it locally

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup. The short version:

```bash
cp .env.example .env    # fill in your own values
docker compose up --build
curl localhost:8000/api/health
```

## Docs

- [DESIGN.md](DESIGN.md): the full design, data model, API, and roadmap
- [CONTRIBUTING.md](CONTRIBUTING.md): setup and workflow

---

Not affiliated with the University of South Florida.