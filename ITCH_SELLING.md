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
2. Open the developer tools (<kbd>F12</kbd>) and go to
   **Application** → **Cookies** → `https://itch.io`
3. Find the cookie named `itchio_token` and copy its **Value**

The cookie is `itchio_token`, and it is HttpOnly, so
`document.cookie` cannot see it. The old instructions here told you to read a
cookie called `itch.io` from JavaScript, which does not exist; following them
stored nothing and project creation kept failing.

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
| The page lets a buyer pay $0 | `the page does not ask for $3.00` | stops, product stays hidden; set the minimum price on itch.io |

Never a partial state where the site sells something that cannot be bought.

## The project has to charge

The publish path refuses to advertise a product whose itch.io page lets a buyer
pay less than the price the site shows. This is not theoretical: the store
project was created as **pay-what-you-want with no minimum**, so two products
advertised at $3.00 were behind a button that read *Download Now* and took
nothing.

One project holds every product, so a purchase covers the builds listed on it.

Set it once, in the itch.io page, not in the code:

1. Open <https://slingshot-tools.itch.io/slingshot-tools/edit>
2. **Pricing** → *Paid* (not *No payment required*, not a $0 minimum)
3. Price **$3.00** (or "pay what you want" with a $3.00 minimum, which is also
   accepted: the gate reads the floor)
4. Save, then reload the public page: the button must read **Buy Now $3.00**,
   not **Download Now**

Check it without publishing anything:

```bash
python -c "import itch_publish as ip; print(ip.price_is_asked('https://slingshot-tools.itch.io/slingshot-tools', 3.0))"
```

`True` means the page asks for the money. `False` means the product stays
hidden, because the site will not advertise a price the store does not charge.

## Running it by hand

```bash
python itch_publish.py                    # this week's tool
python itch_publish.py password-manager   # a specific one
```

## Replacing a paid build that already shipped

The Friday lane only builds the week's new app, and `paid/` is never committed,
so a product whose installer is stale or wrong cannot be fixed there. Both
editions are the same file with one constant flipped and the free edition is
committed, so the paid one can be rebuilt exactly:

```bash
gh workflow run rebuild-paid.yml -f slug=file-renamer
```

That replaces the store build and leaves the price and the catalogue alone. It
does not put anything on sale — `publish_paid.py` still has to see the store
charging the advertised price first.

## Keep the paid file out of the repository

`paid/` is gitignored and `check_repo_hygiene.py` fails the build if it is ever
tracked. `check_exposure.py` fails if a paid edition appears under `site/`.

## Payouts

Selling is immediate. Getting the money out is separate: itch.io's own payout
system needs a tax interview, and payouts go to PayPal or Payoneer. You can
sell before either is set up. See <https://itch.io/docs/creators/payments>.