# Slingshot Tools

Tiny, fast, free apps for everyday problems. One new app every Monday, improved
every Friday from real signals.

## How it works

| When | What runs | What it does |
|------|-----------|--------------|
| **Monday 07:00 UTC** | `monday-build.yml` | Groq picks an unused everyday problem → generates a polished single-file app → packages a real Windows installer → publishes to the site catalog |
| **Friday 07:00 UTC** | `friday-learn.yml` | Reads the catalog and any available usage data → writes concrete lessons → Monday's build applies them |
| **Every push** | `pages.yml` | Publishes `site/` to GitHub Pages |

## No domain needed

- **Website:** GitHub Pages, free — `https://<user>.github.io/<repo>/`
- **Apps:** the site serves each app directly, and the itch.io page is linked
  from the header for the game-like catalogue feel.

## Repo layout

```
make_app.py            the builder: research -> generate -> installer -> publish
learn.py               the Friday coach
site/                  what gets served (index.html, logo, catalog, built apps)
apps/<slug>/app/       generated single-file app + installer script
data/lessons.txt       lessons the coach rewrites each Friday
data/already_built.json  slugs we never repeat
.github/workflows/     monday-build, friday-learn, pages
```

## Setup (one time, on the GitHub repo)

1. Create a **public** repo named `slingshot-tools` and push this folder.
2. **Settings → Pages → Source: GitHub Actions** (no branch dropdown needed).
3. Add secret `GROQ_API_KEY` (same key the video pipeline uses).
4. Optional repository **Variables**: `SITE_URL` (your Pages URL) and
   `ITCH_PAGE` (your itch.io subdomain).
5. Optional secret `ITCH_API_KEY` if you want real download counts on Fridays.

## Building one right now, without waiting for Monday

```bash
python make_app.py
```

Requires `GROQ_API_KEY` in the environment. Output lands in `apps/` and
`site/apps.json`.

## Design rules baked into the generator

- Single HTML file, inline CSS/JS, no CDN, works offline forever
- Dark red brand theme with a light mode toggle on every app
- localStorage only, plus JSON export/import
- No analytics, no tracking, no network calls
- A real empty state on first run
