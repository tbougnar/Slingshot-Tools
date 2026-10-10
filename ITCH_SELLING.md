# Sell on itch.io, fully automated

Every Friday, with no manual step:

1. build the tool and its Windows installer
2. create the itch.io project, if it does not exist yet
3. upload the installer with butler
4. check the public page really answers
5. **only then** show the buy button on the site

Step 5 is last on purpose. Before this, the catalog marked a tool as sold
before anything could buy it. Now the site never advertises something itch.io
has not confirmed it is serving.

If any step cannot be proven, it stops and says why. The product stays hidden.

## Why a browser is used for step 2

itch.io has **no API for creating projects**. Its server-side API can read your
games, your sales and your collections, but not create one, and butler refuses
outright: *"Butler does not create a new project page for you; it assumes you
have already created one."*

So the project is created by driving the real page in a real browser
(Playwright), signed in with your session cookie. Everything after that uses
itch.io's own tooling.

## One-time setup

### 1. Get your username

It is the part of your profile URL before `.itch.io`, for example
`yourslug` in `https://yourslug.itch.io/`.

```bash
gh variable set ITCH_USER --body "yourslug" --repo tbougnar/Slingshot-Tools
```

### 2. Get an API key

<https://itch.io/settings/user> -> **API keys** -> **Create new key**.

```bash
gh secret set ITCH_API_KEY --repo tbougnar/Slingshot-Tools
```

This is what lets the pipeline read your projects and sales.

### 3. Get the session cookie, once

Only needed for creating a *new* project. Updating an existing one does not
use it.

1. Log in at <https://itch.io> in your browser
2. Open the developer console (<kbd>F12</kbd>)
3. Run this and copy the value:

```js
document.cookie.split('; ').find(c => c.startsWith('itch.io=')).slice(8)
```

4. Store it:

```bash
gh secret set ITCH_SESSION_COOKIE --repo tbougnar/Slingshot-Tools
```

> **This is a credential.** It is a full login session. Store it as a GitHub
> secret, never in a file. It expires after a while; when project creation
> starts failing with "the session cookie was refused", get a new one.
> Do not paste it into a chat.

### 4. Everything is set

You can delete `set_itch_url.py` and `publish_paid.py`; the pipeline does both
now. They are kept for the case where you want to do it by hand.

## What happens if something fails

| Failure | What you see | What happens |
|---|---|---|
| No API key | `cannot list projects` | tries the browser route |
| No session cookie | `the project cannot be created` | stops, product stays hidden |
| Project is a draft | `the page is not publicly reachable yet` | stops, product stays hidden |
| butler missing | `butler is not installed` | stops, product stays hidden |
| Upload fails | butler's own error | stops, product stays hidden |
| Price outside $1-$10 | `outside the $1-$10 rule` | stops, product stays hidden |

Never a partial state where the site sells something that cannot be bought.

## Running it by hand

```bash
python itch_publish.py                    # this week's tool
python itch_publish.py password-manager   # a specific one
```

## Keep the paid file out of the repository

`paid/` is gitignored and `check_repo_hygiene.py` fails the build if it is ever
tracked. `check_exposure.py` fails if a paid edition appears under `site/`.

## Payouts

Selling is immediate. Getting the money out is separate: itch.io's own payout
system needs a tax interview, and payouts go to PayPal or Payoneer. You can
sell before either is set up. See <https://itch.io/docs/creators/payments>.