# Getting Started

How to get USF Guessr running on your machine and how we work together. For the full plan (features, data model, API), see [DESIGN.md](DESIGN.md).

## What's running

`docker compose up` starts three containers on a private network:

| Service | What it is | Reachable at |
|---|---|---|
| `api` | FastAPI backend, built from `backend/Dockerfile` | `localhost:8000` |
| `db` | Postgres 18 + PostGIS | `localhost:5432` (containers use `db:5432`) |
| `redis` | Job queue (not used until Phase 3) | Containers only |

Database data lives in a Docker volume (`pgdata`), so it survives restarts.

## Prerequisites

- **Git**, plus the **GitHub CLI** (`gh`) for issues and pull requests
- **Docker Desktop**
- **uv** (`brew install uv`) for running backend tests and checks locally
- **Node.js 26** (`brew install node`) for the frontend

## First-time setup

**1. Clone the repo**
```
git clone git@github.com:jsouvenir/USF-Guesser.git
cd USF-Guesser
```

**2. Create your `.env`**
```
cp .env.example .env
```
Open `.env` and choose your own values for `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`. They only exist on your machine.
- Stick to letters, numbers, and hyphens in the password. Characters like `@`, `:`, `/`, and `#` break the database URL.
- **Never commit `.env`.** It's already in `.gitignore`. Check `git status` before every commit.

**3. Start everything**
```
docker compose up --build
```
The first run downloads the Postgres and Redis images, which takes a few minutes. Look for `database system is ready to accept connections` and `Uvicorn running on http://0.0.0.0:8000`.

**4. Check it works.** In a second terminal:
```
curl localhost:8000/api/health
```
You should get `{"status":"ok"}`, which means the API reached the database. Interactive API docs are at `localhost:8000/docs`.

## Everyday commands

From the repo root:

| Command | What it does |
|---|---|
| `docker compose up --build` | Start everything, rebuilding the API if code changed |
| `docker compose up -d` | Start in the background (or press `d` while running) |
| `docker compose logs -f` | Follow logs from background containers |
| `docker compose down` | Stop and remove the containers. Data is kept. |
| `docker compose down -v` | Also **delete the database**, for a clean reset |
| `docker compose exec db psql -U <user> -d <db>` | Open a SQL shell, using your `.env` values (`\dt` lists tables, `\q` quits) |

## Backend checks (before every push)

From `backend/`:
```
uv sync
uv run ruff check --fix .
uv run ruff format .
uv run mypy app tests
uv run pytest
```
CI runs the same checks (without auto-fixing) on every pull request, and merging is blocked until they pass.

Tests don't need Docker: `tests/conftest.py` sets a placeholder `DATABASE_URL`, and tests swap the database for fakes using FastAPI's dependency overrides.

## Frontend

From `frontend/`:
```
npm install
npm run dev        # http://localhost:5173
npm run lint && npm run build
```

## How we work

1. **Pick an issue** on GitHub and assign yourself.
2. **Branch from an up-to-date main:**
   ```
   git switch main
   git pull
   git switch -c feature/short-name
   ```
3. **Commit small and often,** using [Conventional Commits](https://www.conventionalcommits.org): `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `ci:`, `refactor:`.
4. **Push and open a pull request** with `Closes #<issue>` in the description:
   ```
   git push -u origin feature/short-name
   gh pr create --title "feat: ..." --body "Closes #<issue>"
   ```
5. **Merge** once CI is green and it's reviewed.

Direct pushes to `main` are blocked. If you use an AI assistant, give it [DESIGN.md](DESIGN.md) first. Section 14 explains how it should help.

## Troubleshooting

- **`port is already allocated` on 5432:** a local Postgres is running on your machine. Stop it, or change the db mapping to `"5433:5432"`.
- **`no matching manifest for linux/arm64`:** the PostGIS image is amd64-only. The compose file already sets `platform: linux/amd64`; make sure you pulled the latest main.
- **`database_url Field required`:** `DATABASE_URL` isn't set. In Docker it comes from `.env` through Compose. To run uvicorn outside Docker, set it yourself with `localhost` as the host instead of `db`.
- **Changed your `.env` password but can't connect:** Postgres only reads those values the first time the volume is created. Run `docker compose down -v` to reset (this deletes local data).
