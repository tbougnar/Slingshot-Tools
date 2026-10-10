# Internal notes for the AI pipeline

This repository is **public**, and it must stay public: GitHub Pages serves the
website from the `site/` folder in `main`, and a private repository would take
the shop offline.

That means the rule is not "keep everything private". It is:

> The website is public. The paid product is not. The company's internal
> numbers are not. Everything else is either needed to run or harmless.

## What is public on purpose

| Path | Why it is public |
|---|---|
| `site/**` | the website itself. GitHub Pages deploys exactly this folder |
| `README.md` | what a visitor sees first |
| `LICENSE`, `PRIVACY.md` | required, and reassuring |
| `*.md` docs | how the project works; nothing secret in them |

## What must never be public

| Path | What it is |
|---|---|
| `paid/**` | the paid edition's source and the built installer |
| `data/polls.json` | holds voters' Discord user ids |
| `data/discord_sent.json` | local send state |
| `.env*`, `*.pem`, `*.key`, `*_token.json` | credentials |
| `dist/`, `build/` | built installers |

`check_exposure.py` fails the build if a paid edition ever appears under
`site/`, and it runs in every workflow.

## What is deliberately not tracked

| Path | Why |
|---|---|
| `apps/` | the full source of nine **paid** products. Dead products, not for sale, not deployed, and the full-edition native source. Deleting it from tracking keeps the paid source out of the public repository forever |
| `data/earnings.json`, `prices.json`, `price_log.json`, `budget.json`, `reputation.json` | revenue, margins and cost. Useful to a competitor, worthless to a customer |
| `*.bak*` | stale copies of the generator from earlier runs |
| `PATTERN_CARD.txt`, `debug_team*.py`, `seed_fixbook.py`, `mark_verified.py`, `groq_check.py`, `itch_login.py`, `paypal_check.py` | one-off scratch scripts kept during development |

Those live on the machine that builds. They are in `.gitignore`, and
`check_repo_hygiene.py` fails the build if any of them is ever tracked again.

## The two secrets that matter

Only two, and neither is in this repository:

- the PayPal **Live** client id and secret, set with `wrangler secret put`
- the Discord **bot token**, set with `gh secret set`

Both have been pasted into a chat session, so both are treated as burned and
must be rotated. See `PAYPAL_LIVE.md`.

## Adding a file, honestly

Before committing anything new, ask which of these it is:

1. part of the website → `site/`, safe
2. needed to run the pipeline → repository root, safe
3. about money, customers, or internal decisions → do not track it
4. anything from a paid product → never track it

`python check_repo_hygiene.py` answers the same question automatically.