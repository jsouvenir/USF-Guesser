#!/usr/bin/env python3
"""Turn the DESIGN.md task list into GitHub labels, milestones, and issues.

Safe by default: without --create it only prints what it would do.

Usage (from the repo root, after `gh auth login`):
    python3 scripts/create_issues.py                 # preview everything
    python3 scripts/create_issues.py --phase 0       # preview Phase 0 only
    python3 scripts/create_issues.py --phase 0 --create
    python3 scripts/create_issues.py --create        # create all phases

Re-running is safe: issues whose title already exists (open or closed) are
skipped, and labels/milestones are only created if missing.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

LABELS = {
    "backend": ("1D76DB", "FastAPI, database, worker"),
    "frontend": ("0E8A16", "React app"),
    "infra": ("5319E7", "CI/CD, Docker, AWS, Terraform"),
    "content": ("FBCA04", "Photos, copy, launch"),
}

MILESTONES = {
    0: "Phase 0: Foundation",
    1: "Phase 1: Core game",
    2: "Phase 2: Accounts and leaderboard",
    3: "Phase 3: Submissions and moderation",
    4: "Phase 4: Deploy",
    5: "Phase 5: Launch",
}

REVIEWED = "CI is green and the pull request is reviewed"

# (phase, label, title, design-doc sections, done-when items, needs_pr)
TASKS: list[tuple[int, str, str, str, list[str], bool]] = [
    # ---------------- Phase 0 ----------------
    (0, "infra", "Remove CI paths filters and require both checks", "10, 12", [
        "Both workflows run on every push and pull request (no `paths` filters)",
        "Jobs have unique names, e.g. `backend` and `frontend`",
        "The `main` ruleset requires both checks before merging",
    ], True),
    (0, "frontend", "Install Tailwind, React Router, and react-leaflet", "4, 8", [
        "Tailwind is configured and visibly styles a test element",
        "React Router has placeholder pages for `/`, `/practice`, `/leaderboard`, `/submit`, `/admin`",
        "`leaflet` and `react-leaflet` are installed and Leaflet's CSS is imported",
        "`npm run lint` and `npm run build` pass",
    ], True),
    (0, "backend", "Backend Dockerfile", "10, 11", [
        "`docker build` succeeds and the container serves the health endpoint",
        "Installs with `uv sync --no-dev` (no dev tools in the image)",
        "Runs as a non-root user",
    ], True),
    (0, "infra", "docker-compose.yml with API, PostGIS database, and Redis", "10", [
        "`docker compose up` starts `api`, `db` (PostGIS image), and `redis`",
        "Database data persists in a named volume",
        "The API reaches the database by service name",
        "`.env.example` documents every variable (fake values only)",
    ], True),
    (0, "backend", "Settings, database session, and /api/health database check", "6, 10", [
        "`app/config.py` loads settings from environment variables with pydantic-settings",
        "`app/db.py` provides the engine and a session dependency",
        "All routes are mounted under `/api`; health lives at `/api/health`",
        "Health returns 503 when the database is unreachable, with tests",
    ], True),
    (0, "backend", "Alembic setup and first migration", "5", [
        "SQLAlchemy models for every table in section 5 live in `app/models/`",
        "Location columns are `geography(Point, 4326)` with GiST indexes",
        "`alembic upgrade head` works on a fresh database, and `downgrade` works too",
    ], True),
    (0, "backend", "Seed script for the USF Tampa campus", "5", [
        "Inserts the `usf-tampa` campus with its boundary polygon",
        "Safe to run more than once (no duplicates)",
        "How to run it is documented in the README",
    ], True),
    (0, "backend", "PostGIS distance query with a database test in CI", "5, 10", [
        "A function returns the distance in meters between two points using `ST_Distance` on geography",
        "A test checks a known pair of campus points against a real database",
        "The backend CI job runs a PostGIS service container and applies migrations before tests",
    ], True),
    (0, "content", "Take 100-200 campus photos", "2, 17", [
        "Each photo has its true location (lat/lng) and a difficulty: easy, medium, or hard",
        "Difficulties are roughly balanced",
        "A CSV lists filename, lat, lng, difficulty, and notes",
        "Photos are stored outside the repo, never committed",
    ], False),
    (0, "frontend", "Choose a map tile provider and get an API key", "4, 17", [
        "Compare free tiers of MapTiler, Stadia Maps, and Carto",
        "Record the choice in DESIGN.md section 17",
        "Key lives in `frontend/.env.local` and is documented in `.env.example`",
        "Map shows the required attribution",
    ], True),
    (0, "content", "Pick the final name and check domain availability", "17", [
        "Shortlist a few names and check `.com` availability",
        "Check the GitHub Student Developer Pack domain offer",
        "Update the name in DESIGN.md",
    ], False),
    # ---------------- Phase 1 ----------------
    (1, "backend", "Scoring function with unit tests", "2", [
        "`score_for_distance(meters) -> int` lives in `app/services/scoring.py`",
        "Tests: 0 m and 10 m give 5,000; 1,500 m and beyond give 0",
        "Tests: score never increases as distance grows; negative distance is rejected",
    ], True),
    (1, "backend", "Storage interface: local disk in development, S3 in production", "10", [
        "One interface for saving files and getting their URLs",
        "Local-disk version works in Docker Compose",
        "S3 version is selected by a setting",
    ], True),
    (1, "backend", "Photo import script", "5, 7", [
        "Reads a photo folder plus the CSV from the photo-taking task",
        "Strips metadata and resizes before storing",
        "Inserts approved photos with location and difficulty; skips ones already imported",
    ], True),
    (1, "backend", "Guest ID cookie middleware", "2, 9", [
        "New visitors get a random `guest_id` cookie (httpOnly, SameSite=Lax, Secure in production)",
        "Returning visitors keep the same ID",
        "Routes can read the current guest through a dependency, with tests",
    ], True),
    (1, "backend", "Daily challenge model and selection logic", "2, 5, 6", [
        "Picks one approved easy, medium, and hard photo not used in the last N days",
        "Dates are in America/New_York; one challenge per campus per date",
        "Clear error when there aren't enough approved photos, with tests",
    ], True),
    (1, "backend", "Game and guess endpoints", "6", [
        "`POST /api/games`, `GET /api/games/{id}`, and `POST /api/games/{id}/guesses` match section 6",
        "A test proves no response reveals a photo's location before its guess",
        "Rounds must be guessed in order, once each",
        "One daily game per player per day; starting again resumes it",
    ], True),
    (1, "frontend", "GuessMap component", "8", [
        "Map is centered on USF Tampa and limited to the campus area",
        "Tap or click places one pin; tapping again moves it",
        "The selected lat/lng is passed to the parent; works with touch",
    ], True),
    (1, "frontend", "PhotoViewer component", "8", [
        "Shows the photo with a loading state",
        "Tap to view full screen on mobile",
    ], True),
    (1, "frontend", "Play page connected to the API", "2, 8", [
        "`/` starts or resumes today's daily challenge",
        "Flow: photo, guess, result, next round, final result",
        "Shows a friendly message if the API is down",
    ], True),
    (1, "frontend", "RoundResult screen", "2, 8", [
        "Shows both pins and the line between them",
        "Shows distance (m or km) and score",
        "Next-round button",
    ], True),
    (1, "frontend", "FinalResult screen with share text", "2, 8", [
        "Total out of 15,000 plus a per-round breakdown",
        "Share uses the Web Share API on mobile, with a copy-to-clipboard fallback",
    ], True),
    (1, "frontend", "Mobile layout and first-visit hint", "8", [
        "Photo on top, map below, with an expand-map toggle",
        "Usable at 375 px wide",
        "One-line hint shows until the first guess, never a popup",
    ], True),
    (1, "backend", "Practice mode", "2, 6", [
        "`mode: practice` serves random approved photos without repeats in a session",
        "Practice games never count toward the leaderboard",
        "`/practice` page reuses the game components",
    ], True),
    # ---------------- Phase 2 ----------------
    (2, "backend", "Google sign-in with Authlib and session cookies", "2, 6, 9", [
        "Google OAuth client set up with local and production redirect URLs",
        "Login and callback routes create or update the user by Google ID",
        "Signed httpOnly session cookie; secrets only in `.env`",
    ], True),
    (2, "backend", "Claim guest games on sign-in", "2", [
        "Games under the current `guest_id` move to the user on sign-in",
        "If both have today's daily, keep the user's existing one",
        "Tests cover both cases",
    ], True),
    (2, "backend", "/api/me with stats and streak", "6", [
        "Returns guest or user info, games played, average score, current and best streak",
        "Tests for both guests and signed-in users",
    ], True),
    (2, "backend", "Daily leaderboard endpoint", "2, 6", [
        "Top players for a date, signed-in players only",
        "Ties go to whoever finished first",
        "Includes the current player's would-be rank, including for guests",
    ], True),
    (2, "frontend", "Leaderboard page with guest placeholder row", "2, 8", [
        "Table of today's top players, highlighting the current user",
        "Guests see a placeholder row: \"You (guest): would be #N\"",
    ], True),
    (2, "frontend", "SignInBanner on results, leaderboard, and streak screens", "2", [
        "Inline banner, never a modal; dismissible",
        "Shows on final results, the leaderboard, and streak notices",
        "Hidden when signed in",
    ], True),
    (2, "backend", "Streak calculation", "2", [
        "Counts consecutive completed daily challenges in America/New_York",
        "Tests cover the midnight boundary and a missed day",
    ], True),
    # ---------------- Phase 3 ----------------
    (3, "backend", "Presigned upload endpoint with size and type limits", "6, 9", [
        "Signed-in users only",
        "Allows JPEG, PNG, and HEIC; enforces a max size with a presigned POST",
        "Short expiry; works with local storage in development",
    ], True),
    (3, "frontend", "Submit page: upload a photo and drop a pin", "2, 8", [
        "Signed-out users see an inline sign-in prompt",
        "Pick or take a photo, drop a pin, add an optional note",
        "Submission rules are visible; past submissions show their status",
    ], True),
    (3, "backend", "Redis and RQ worker in Docker Compose", "3, 7", [
        "`worker` service runs alongside `api` and `redis`",
        "The API can enqueue a job and the worker runs it",
    ], True),
    (3, "backend", "process_submission job", "7", [
        "Implements every step in section 7, including HEIC support and stripping metadata",
        "Flags: duplicate, blurry, GPS mismatch, missing GPS, outside campus",
        "Tests with sample images (with and without GPS, duplicate, blurry)",
    ], True),
    (3, "backend", "Admin approve and reject endpoints", "6", [
        "Admins only; others get 403",
        "Approve sets status, difficulty, reviewer, and time; reject stores a reason",
        "Tests for both",
    ], True),
    (3, "frontend", "Admin review queue page", "2, 8", [
        "Lists pending submissions with the photo, both pins on a map, and flags",
        "Approve with a difficulty, or reject with a reason",
        "Only reachable by admins",
    ], True),
    (3, "backend", "Nightly pick_daily_challenge job", "7", [
        "Runs automatically before midnight America/New_York",
        "Reuses the daily selection logic; logs clearly if photos run short",
    ], True),
    (3, "backend", "Rate limiting on guesses and uploads", "9", [
        "Per player and per IP limits; returns 429 when exceeded",
        "Tests; any new dependency is discussed in the pull request",
    ], True),
    # ---------------- Phase 4 ----------------
    (4, "infra", "Create the AWS account", "10", [
        "Created in late December",
        "Root account has MFA; a $10 budget alert is set",
        "A separate login (IAM Identity Center or IAM user with MFA) for daily use",
    ], False),
    (4, "infra", "Terraform for AWS resources", "10", [
        "Code in `infra/` with state in S3 and locking",
        "Covers buckets, CloudFront, EC2, security groups, IAM roles, Route 53, and ACM",
        "`terraform plan` shows no unexpected changes",
    ], True),
    (4, "infra", "Production Docker Compose file and secrets", "9, 10", [
        "Separate production compose file with restart policies",
        "Secrets come from AWS (SSM or Secrets Manager), never the repo or images",
    ], True),
    (4, "infra", "CD workflow with OIDC", "10", [
        "Merging to `main` builds and pushes images to ECR, runs migrations, and restarts containers via SSM",
        "Frontend builds, syncs to S3, and invalidates CloudFront",
        "No long-lived AWS keys stored in GitHub",
    ], True),
    (4, "infra", "Nightly database backups to S3", "7, 10", [
        "Nightly `pg_dump` to S3, kept for 30 days",
        "A restore has been tested once",
    ], True),
    (4, "infra", "Sentry and CloudWatch logs", "10", [
        "Sentry on backend and frontend, with the DSN from environment variables",
        "Container logs go to CloudWatch",
        "A test error shows up in Sentry",
    ], True),
    (4, "infra", "Domain and HTTPS", "10", [
        "Domain registered with Route 53 records",
        "ACM certificate (in us-east-1 for CloudFront); HTTP redirects to HTTPS",
    ], False),
    # ---------------- Phase 5 ----------------
    (5, "content", "Playtest and tune the scoring curve", "2", [
        "At least 5 testers play several dailies and give feedback",
        "Scoring constants tuned and recorded in DESIGN.md",
    ], False),
    (5, "content", "README with demo GIF and architecture diagram", "1", [
        "What it is, live link, demo GIF, architecture diagram, tech stack, local setup",
    ], True),
    (5, "content", "Submission rules and privacy page", "2, 9", [
        "Explains submission rules, what data is stored, and how to request deletion",
        "Linked from the submit page and the footer",
    ], True),
    (5, "content", "Launch posts", "1", [
        "Drafts for r/USF, club Discords, and International Student Services",
        "Posted in the first week of the spring semester",
    ], False),
    (5, "infra", "Monitor errors and AWS costs after launch", "10", [
        "Check Sentry, CloudWatch, and AWS billing daily during launch week",
        "Budget alert confirmed working",
    ], False),
]


def gh(*args: str, capture: bool = True) -> str:
    result = subprocess.run(["gh", *args], capture_output=capture, text=True)
    if result.returncode != 0:
        sys.exit(f"gh {' '.join(args[:3])} failed:\n{result.stderr}")
    return result.stdout if capture else ""


def body_for(phase: int, label: str, sections: str, done: list[str],
             needs_pr: bool, repo: str) -> str:
    items = done + ([REVIEWED] if needs_pr else [])
    checklist = "\n".join(f"- [ ] {item}" for item in items)
    link = f"https://github.com/{repo}/blob/main/DESIGN.md"
    return (
        f"Part of **{MILESTONES[phase]}** in [DESIGN.md]({link}). "
        f"Relevant sections: {sections}.\n\n"
        f"**Area:** {label}\n\n"
        f"### Done when\n{checklist}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--phase", type=int, action="append",
                        help="Only this phase (repeatable). Default: all phases.")
    parser.add_argument("--create", action="store_true",
                        help="Actually create things. Without this, just preview.")
    parser.add_argument("--repo", help="owner/name. Default: the current repo.")
    args = parser.parse_args()

    phases = set(args.phase) if args.phase else set(MILESTONES)
    tasks = [t for t in TASKS if t[0] in phases]
    if args.create or not args.repo:
        repo = args.repo or gh("repo", "view", "--json", "nameWithOwner",
                               "-q", ".nameWithOwner").strip()
    else:
        repo = args.repo

    if not args.create:
        print(f"PREVIEW for {repo}: {len(tasks)} issues. Nothing will be created.\n")
        for phase, label, title, sections, done, needs_pr in tasks:
            print(f"[{MILESTONES[phase]}] [{label}] {title}")
            print("    " + body_for(phase, label, sections, done, needs_pr, repo)
                  .replace("\n", "\n    "))
        print("Run again with --create to make these.")
        return

    # Labels (--force updates color/description if the label exists).
    for name, (color, desc) in LABELS.items():
        gh("label", "create", name, "--color", color, "--description", desc,
           "--force", "--repo", repo)

    # Milestones.
    existing_ms = {m["title"] for m in json.loads(
        gh("api", f"repos/{repo}/milestones?state=all&per_page=100"))}
    for phase in sorted(phases):
        title = MILESTONES[phase]
        if title not in existing_ms:
            gh("api", f"repos/{repo}/milestones", "-f", f"title={title}")
            print(f"Created milestone: {title}")

    # Issues, skipping titles that already exist.
    existing = {i["title"] for i in json.loads(gh(
        "issue", "list", "--repo", repo, "--state", "all",
        "--limit", "1000", "--json", "title"))}
    made = 0
    for phase, label, title, sections, done, needs_pr in tasks:
        if title in existing:
            print(f"Skip (exists): {title}")
            continue
        url = gh("issue", "create", "--repo", repo, "--title", title,
                 "--label", label, "--milestone", MILESTONES[phase],
                 "--body", body_for(phase, label, sections, done, needs_pr, repo))
        print(f"Created: {title} -> {url.strip()}")
        made += 1
        time.sleep(1)  # stay well under GitHub's abuse rate limits
    print(f"\nDone. Created {made} issue(s).")


if __name__ == "__main__":
    main()
