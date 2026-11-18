# Kerit Cloud + GitHub Actions hybrid setup (step by step)

This project uses **Kerit Cloud** for what GitHub Actions cannot do well (24/7 always-on service/endpoint, instant manifest serving, persistent background worker) and **GitHub Actions** for repo-driven CI and heavy builds (especially Windows installers).

## What runs where

| Responsibility | Kerit Cloud (always-on) | GitHub Actions (CI/builds) |
|---|---|---|
| Serve `update.json` / `votes.json` / `events.json` instantly | ✅ `kerit_service.py` HTTP endpoints | Fallback via GitHub Pages (`site/*`) |
| Persistent background sync/scheduling | ✅ periodic git pull, vote sync, optional learning-day scheduler | ✅ cron workflows (existing schedules) |
| Learning-day scan + same-day manifest publish | ✅ possible if enabled (`SLINGSHOT_LEARNING_DAY=1`) | ✅ `wednesday-review.yml` / `weekly_cycle.py` |
| Discord vote/tally live sync & always-on bot hooks | ✅ best place (24/7 process) | Limited/awkward for always-on |
| Windows app builds/installers (PyInstaller/NSIS) | ⚠️ not recommended on 256 MB Linux container | ✅ preferred (Windows runners/tooling) |
| Source of truth (code/history) | git clone/pull | ✅ canonical repo + PRs/commits |

## Step 1 — Prepare the repository (done in codebase)
Ensure these files exist in your repo (already added/configured):
- `kerit_service.py` — always-on HTTP service + background scheduler
- `sync_votes_site.py` — keeps `site/votes.json` in sync with poll data
- `app_update.py` — supports `SLINGSHOT_UPDATE_URL` (Kerit primary) with GitHub Pages fallback
- `learning_day_scan.py` — same-day scan + per-app update manifest publishing
- `kerit.env.example` — environment variable template

Commit and push to GitHub so Kerit can deploy/pull the latest code.

## Step 2 — Create and deploy on Kerit Cloud
1. **Create a Kerit Cloud account/project** (no credit card) and create a new app/service for this repo.
2. **Deploy from Git**: connect your GitHub repo/branch (or clone URL) so Kerit runs the code from this repository.
3. **Set runtime/start command** (in Kerit app settings):
   - Start command: `python kerit_service.py`
   - Runtime: Python 3.12+ (match project needs)
4. **Set environment variables** (see `kerit.env.example`):
   - `PORT` — use Kerit’s provided port if required (service defaults to `8080`)
   - `SLINGSHOT_GIT_PULL=1`, `SLINGSHOT_PULL_INTERVAL=300`
   - `SLINGSHOT_SYNC_INTERVAL=60`
   - `SLINGSHOT_LEARNING_DAY=0` (recommended initially; keep learning-day scheduling in GitHub Actions) or `1` to let Kerit run it on schedule
   - Add provider/Discord secrets only if Kerit will run AI scans or live Discord sync: `OPENROUTER_API_KEY`/`GROQ_API_KEY`, `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, etc.
5. **Deploy/start** the service and confirm it stays running.
6. **Renew weekly**: Kerit free tier requires periodic free renewal — set a reminder/automation so the 24/7 endpoint never lapses.

## Step 3 — Verify Kerit endpoints
Once deployed, note your public Kerit app URL (e.g. `https://<your-app>.kerit...`) and verify:
- `GET /health` → service status JSON
- `GET /update.json` → same-day app update manifest (served from `site/update.json`)
- `GET /votes.json` → current vote/poll data
- `GET /events.json` → events data

These endpoints are the always-on, instant sources for clients.

## Step 4 — Point installed apps to Kerit (instant updates, with fallback)
- Set `SLINGSHOT_UPDATE_URL` to your Kerit manifest URL, e.g.:
  - `SLINGSHOT_UPDATE_URL=https://<your-kerit-app>/update.json`
- For **newly built/shipped apps**, provide this at build/runtime environment so `app_update.py` prefers Kerit and falls back to GitHub Pages (`https://tbougnar.github.io/Slingshot-Tools/update.json`) if Kerit is unreachable.
- For **already installed apps**, they must receive an updated build (with the new updater/launcher logic) to take advantage of configurable/instant update sourcing and the red update UI.

## Step 5 — Keep GitHub Actions as CI/build backbone
- Keep existing workflows enabled (e.g. `wednesday-review.yml`, `friday-build.yml`, Pages deploy). GitHub Actions remains responsible for:
  - scheduled learning/review/build pipelines and repo commits
  - heavy **Windows** packaging/builds (PyInstaller/NSIS) and release publishing
  - GitHub Pages fallback hosting of `site/*`
- Kerit will `git pull` periodically to serve the latest manifests/data committed by Actions.
- Recommended split: **Kerit = always-on serving/sync/instant availability**, **Actions = builds/CI/releases/source-of-truth automation**.

## Step 6 — Same-day update flow (hybrid)
1. Learning day runs (GitHub Actions by default, or Kerit if enabled) → `learning_day_scan.py` scans system, generates AI update notes, bumps per-app versions, publishes `site/update.json`.
2. Changes are committed/pushed by Actions (or synced) so repo/Pages stay current; Kerit serves the manifest immediately from disk.
3. Installed apps check `SLINGSHOT_UPDATE_URL` (Kerit, instant) with GitHub Pages fallback, show the red **Update available** button with AI description, and can download/restart to apply.

## Step 7 — Operational checks (256 MB, 24/7)
- Monitor `/health` and service logs on Kerit.
- Keep scans/sync lightweight to fit 256 MB RAM; offload Windows builds to GitHub Actions.
- Ensure git pull works in Kerit’s environment (repo access/credentials if private; read-only pull is enough for serving public manifests).
- Do not miss Kerit’s **weekly free renewal**; consider external uptime monitoring/reminders.
- Keep GitHub Pages publishing intact as a fallback update source for worldwide reliability.

## Useful local commands
- Run service locally: `python kerit_service.py`
- One-shot vote sync: `python sync_votes_site.py`
- One-shot learning-day scan/publish: `python learning_day_scan.py`