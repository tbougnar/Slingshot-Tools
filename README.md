# Slingshot Tools

Small, fast, free apps for everyday problems — plus a fuller edition of each one
for anyone who wants the unlimited version.

## What you get

Every month we release one new tool in two editions:

| | Basic | Full |
|---|---|---|
| Price | Free | Paid |
| What it does | The whole job, with sensible limits | Nothing capped |

Same app, same look. The Full edition removes the caps and adds export/import,
extra themes, bulk actions and history.

## Getting the apps

- The **free Basic** edition downloads free.
- The **Full** edition is purchased on our itch.io page and paid files are delivered there — that is the only place they are hosted.
- Windows users get a real installer with Start Menu and Desktop shortcuts.

## For the curious

The site is plain HTML, CSS and JavaScript. Each app is a single file that runs
offline, stores everything in your own browser, and never sends your data
anywhere. No accounts, no tracking, no network calls.

## Repository layout

```
site/       the public website (what GitHub Pages serves)
apps/       builds, one folder per app and edition
dist/       Windows installers, built locally, never published
data/       pricing state and the sales history used to tune prices
```

Everything that runs on a schedule lives in `.github/workflows/`:

| When | Workflow | What it does |
|------|----------|--------------|
| Monthly, 1st 07:00 | `monday-build.yml` | picks a daily-life problem, builds the Basic and Full editions, sets prices |
| Twice a month | `friday-learn.yml` | adjusts prices from real sales, reviews the catalogue |

## Repository setup

1. **Settings → Pages → Build and deployment → Source: GitHub Actions**, then Save.
2. **Settings → Secrets and variables → Actions**:
   - *Secrets*: `GROQ_API_KEY`, `ITCH_API_KEY`
   - *Variables*: `SITE_URL`, `ITCH_PAGE`, `ITCH_PAGE_URL`

Nothing sensitive is stored in this repository. Credentials live only in GitHub
Secrets, and anything matching a credential filename is ignored by git.

## Running a build locally

```bash
export GROQ_API_KEY=...
export ITCH_API_KEY=...      # optional, enables upload
python make_app.py           # build the next app
python pricing.py            # recalculate prices from sales
```

## Pricing rules

- Floor **$1.00** — below that, fees exceed the margin.
- Ceiling **$9.00**.
- Prices only move after **5 or more** real sales.
- Weak conversion cuts the price; strong conversion raises it.
- Every change is written to `data/price_log.json` with its reason, and can be undone.