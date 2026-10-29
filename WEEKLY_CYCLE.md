# The weekly cycle

Three jobs a week, all of them on a schedule, none of them needing a person or
a computer that stays switched on.

```
Monday    open the ballot        what should we build this week?
Wednesday read and improve       what happened, and what to change
Friday    build and publish      the tool the ballot chose
```

Everything runs on GitHub Actions. If these machines are all switched off, the
week still happens.

---

## The rules the company lives by

**It may not touch the website.** The published site and the scripts that build
or serve it are off limits to every automated job. Check with:

```bash
python weekly_guard.py          # what is protected
python weekly_guard.py check    # did anything protected change?
```

**It may not change money or delete products.** Prices, the payment worker and
the catalog's commercial fields are protected too.

**It may improve itself.** The generator, the QA stack, the providers and the
tools around them are fair game. That is what `self_upgrade.py` edits.

**A product is only retired after a year of nobody wanting it.** Not on a
guess. All of this must hold:

- on sale for 365 days or more
- at most 2 sales, ever
- nothing sold in the last 365 days

Retiring *unpublishes* the product. It never deletes a file, a catalog entry, or
a paid build, so a mistake is one commit away from undone.

```bash
python retire_product.py --list              # what the evidence says
python retire_product.py password-manager   # will refuse if the bar is not met
```

**It spends 30 hours a month, plus 3 hours of emergency.** Every job asks
before it starts, so a month cannot quietly overspend and a job never begins
something it cannot finish.

```bash
python budget.py status
python weekly_cycle.py status      # budget, schedule and what is protected
```

The emergency reserve is only reachable by a job repairing something already
broken, via `SLINGSHOT_EMERGENCY=1`. It is reported separately, so it cannot be
quietly spent on new work.

---

## What each day does

### Monday

`discord_polls.py` posts a ballot in `#polls` listing the unbuilt concepts as
numbered options. Members vote by **replying to that message with the number**:

```
3
```

That is the whole vote. Change your mind by replying again — only your last
reply counts. One vote per person.

Nothing has to be running while people vote. The replies sit in the channel,
and Friday's job reads them over the REST API. That is what lets the week work
on a schedule with no server and no always-on bot.

### Wednesday

`reputation.py` reads what the outside world can see: GitHub stars, forks and
issues, itch.io if a key is configured, what is on sale, and recorded revenue.
Every source is optional, and a missing one is reported as unavailable rather
than guessed at.

`weekly_review.py` turns that into a short, honest review and files it as a
lesson, so the next build reads this week's numbers as coaching. A week with
zero sales is written down as a week with zero sales.

Then `self_upgrade.py` gets one attempt at improving the generator. It may
change one file. The patch is rolled back unless `selftest.py`,
`selftest_deep.py`, `selftest_audit.py` and `check_exposure.py` all still pass,
and `weekly_guard.py check` confirms nothing protected was touched. A patch
that changes nothing useful is discarded.

### Friday

07:00 UTC `stage_app.py` generates the tool the ballot chose, on Windows.
08:00 UTC `friday-verify.yml` opens by itself, verifies the app in a real
browser, refuses to publish anything with two or more dead controls, builds the
NSIS installer on a Windows runner, uploads it to the private store, and posts
to `#announcements`.

The ballot closes first, so the votes from that week are what steer the build.
Most votes wins. **If the top two are level, one is picked at random** rather
than refusing to build anything — seeded from the ballot id, so the same ballot
always resolves the same way and a rerun cannot quietly pick a different tool.
The result is posted either way, with the tally, so nobody has to guess why
their tool won or lost.

If any of it fails, one repair attempt runs against the emergency reserve.

---

## The model backend

All model calls go through `providers.py`. **OpenRouter is primary** and Groq is
the automatic fallback, so adding the new key cannot break a machine that still
has the old one.

| | Primary | Fallback |
|---|---|---|
| Secret | `OPENROUTER_API_KEY` | `GROQ_API_KEY` |
| Base URL | `https://openrouter.ai/api/v1` | `https://api.groq.com/openai/v1` |
| Key prefix | `sk-or-v1-` | `gsk_` |
| Model pin | `OPENROUTER_CHAT_MODEL` (variable) | `GROQ_CHAT_MODEL` |
| Get a key | <https://openrouter.ai/keys> | <https://console.groq.com/keys> |

The backend is whichever key exists; OpenRouter wins when both do. Each job has
a chain of free models in `providers.py` (builder, debug, chat), tried best
first. A 404 (an id that belongs to the other backend) or a per-day cap moves
to the next model instead of failing the run; a rejected key (401/403) stops
immediately, because walking the chain cannot fix a bad key.

Set the secret once:

```bash
gh secret set OPENROUTER_API_KEY --repo tbougnar/Slingshot-Tools
```

Prove it without storing it (`groq_live_check.py` reads the prefix and tests the
matching backend, then forgets the key):

```bash
python groq_live_check.py
```

Keep `GROQ_API_KEY` in place until an OpenRouter run has passed end to end. It
costs nothing to leave and is the rollback.

---

## Why Friday's verification is a separate workflow

It chains automatically on `workflow_run`, so verification is never a manual
step, and only a *successful* generation is verified. The paid build travels
between jobs as a private artifact, never through git, because `paid/` is
gitignored and must never become public.

Verification runs an hour after generation on purpose. The model allowance is
per minute for the whole account, so verifying in the same minute leaves the
repair step with nothing and then nothing can ever pass QA.

---

## Running it by hand

```bash
python weekly_cycle.py status        # the whole picture
python weekly_cycle.py monday        # open the ballot now
python weekly_cycle.py wednesday     # review now
python weekly_cycle.py status        # confirm nothing protected changed
```

GitHub's cron is UTC and can run a few minutes late when the platform is busy.
Nothing depends on the exact minute, and a ballot is never closed twice because
the run happened late.

---

## Turning it off

Delete the schedule from the workflow, or disable the Actions workflow in the
repository settings. Nothing else depends on it: the site, the payment worker
and the Discord bot all keep working.