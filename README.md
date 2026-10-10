# Slingshot Tools

Small, fast, free desktop tools for everyday problems, with a fuller edition of
each one for anyone who wants the unlimited version.

**One new tool every week, chosen by the people who use them.**

---

## What you get

Every tool ships in two editions:

| | Basic | Full |
|---|---|---|
| Price | Free | Paid |
| What it does | The whole job, with sensible limits | Nothing capped |
| Runs on | Any browser | Windows, as a real app |

Same app, same look. The Full edition removes the caps and adds export/import,
extra themes, bulk actions and history.

## Getting the tools

- The **Basic** edition is free and runs straight in the browser.
- The **Full** edition is a Windows app, bought on the site.
- Windows users get a real installer with Start Menu and Desktop shortcuts.

No account, no sign-up, no tracking, no network calls. Your data stays in your
own browser and never leaves your device.

**Live catalog:** <https://tbougnar.github.io/Slingshot-Tools/>

---

## How a tool gets made

The community votes on what to build, and the winning option is the one that
ships.

| Day | What happens |
|---|---|
| **Monday** | A ballot opens with the ideas that have not been built yet |
| **Wednesday** | The week is reviewed — what sold, what people asked for, what changes. The generator also reviews itself and improves |
| **Friday** | The chosen tool is built, checked in a real browser, and released |

Everything runs on a schedule. Nothing waits for a person to press anything.

### It will not ship you something broken

Before anything is published it is opened in a real browser and every control is
clicked. A tool with **two or more dead controls is never published** — the week
closes with nothing shipped rather than something that does not work.

### It cannot cheat

The automation is allowed to rewrite its own generator and its own tests. It is
not allowed to touch:

- the website, or the scripts that build and serve it
- prices, or the payment API
- the products themselves

The price is chosen each week inside a fixed range. The range is set in the
workflow and enforced again by the payment server, so it holds even if a
request asks for something else.

A product is only taken down after **a full year** of being for sale with
essentially no demand, and even then it is only hidden, never deleted.

---

## Repository layout

```
site/          the public website, exactly what GitHub Pages serves
worker/        the payment API (a Cloudflare Worker)
data/          internal state: revenue, prices, lessons
*.py           the generator, the QA stack and the weekly cycle
```

Everything that runs on a schedule is in `.github/workflows/`:

| When | Workflow | What it does |
|---|---|---|
| Monday 09:00 | `monday-vote.yml` | opens the week's ballot |
| Wednesday 09:00 | `wednesday-review.yml` | reviews the week, and improves the generator |
| Friday 07:00 | `friday-build.yml` | generates the chosen tool |
| after that | `friday-verify.yml` | verifies it, builds the installer, publishes |
| on a push | `pages.yml` | deploys the website |

---

## Privacy

**Nothing about you is collected.** No accounts, no sign-up, no analytics, no
cookies, no network calls from the tools themselves. The Basic editions run
entirely offline in your browser.

## License

MIT — see [LICENSE](LICENSE). Every Slingshot utility, including the free Basic
edition, ships its full source in this repository.