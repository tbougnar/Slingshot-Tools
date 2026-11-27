# Sell on itch.io, one project per app

Every Friday, with no manual step:

1. build the tool and its Windows installer
2. upload it to **that product's own** itch.io project with butler
3. check the public page really answers and charges exactly $3.00
4. **only then** show the buy button on the site

Step 4 is last on purpose. Before this, the catalog marked a tool as sold before
anything could buy it. Now the site never advertises something itch.io has not
confirmed it is serving.

Each paid app has its own project and its own page. The old shared project
`slingshot-tools` put four installers behind one Purchase block: a buyer of one
tool could download all the others. The pipeline now refuses any catalogue URL
whose project name is not the app's own slug, and `set_itch_url.py --all` is
disabled.

## Why each page is created by hand

itch.io has **no API for creating projects**. Its server-side API can read your
games, sales and collections, but not create one, and butler refuses outright:
*"Butler does not create a new project page for you; it assumes you have already
created one."*

The web form is also behind Cloudflare Turnstile, so the browser automation in
`create_project()` cannot be trusted to finish it unattended. Create one empty
page per app once, by hand. Everything after that uses the API key and butler.

## One-time setup

### 1. Get your username

It is the part of your profile URL before `.itch.io`, for example
`slingshot-tools` in `https://slingshot-tools.itch.io`.

```bash
gh variable set ITCH_USER --body "slingshot-tools" --repo tbougnar/Slingshot-Tools
```

### 2. Get an API key

<https://itch.io/settings/user> -> **API keys** -> **Create new key**.

```bash
gh secret set ITCH_API_KEY --repo tbougnar/Slingshot-Tools
```

This is what lets the pipeline upload builds and read your projects and sales.
The `ITCH_STORE_URL` variable is deliberately no longer used: one shared URL was
the bug.

### 3. Create one project per paid app

For each slug in `site/apps.json`:

1. Open <https://itch.io/settings/mine/new/game>.
2. Set the title to the app's title and the project URL to the app's slug, e.g.
   `unit-converter` gives `https://slingshot-tools.itch.io/unit-converter`.
3. Choose **Downloadable**, **Released** and **Public**.
4. Set **Pricing** to *Paid* with a **$3.00 minimum**.
5. Save and confirm the public page says **Buy Now $3.00**.
6. Record it in the catalogue:

```bash
python set_itch_url.py unit-converter https://slingshot-tools.itch.io/unit-converter
```

An empty `itch_url` means "not for sale yet"; nothing invents a shared one.

## What happens if something fails

| Failure | What you see | What happens |
|---|---|---|
| No API key | `cannot list projects` | stops, product stays hidden |
| No page for this app | `no page of its own yet` | stops, product stays hidden |
| Page points at another app | `refusing to sell one tool as another` | stops, product stays hidden |
| Page is a draft | `the page is not publicly reachable yet` | stops, product stays hidden |
| butler missing | `butler is not installed` | stops, product stays hidden |
| Upload fails | butler's own error | stops, product stays hidden |
| Price outside $2.99-$4.99 | `outside the paid price band` | stops, product stays hidden |
| The page lets a buyer pay $0 | `the page does not ask for $3.00` | stops, product stays hidden; set the minimum price on itch.io |

Never a partial state where the site sells something that cannot be bought, or
sells one tool on another tool's page.

## The page has to charge exactly $3.00

The publish path refuses to advertise a product whose itch.io page lets a buyer
pay less than the price the site shows. This is not theoretical: the old shared
project was created as *pay-what-you-want with no minimum*, so two products
advertised at $3.00 were behind a button that read *Download Now* and took
nothing.

Check one page without publishing anything:

```bash
python -c "import itch_publish as ip; print(ip.price_is_asked('https://slingshot-tools.itch.io/unit-converter', 3.0))"
```

`True` means the page asks for the money. `False` means the product stays
hidden, because the site will not advertise a price the store does not charge.

## Running it by hand

```bash
python itch_publish.py                    # this week's tool
python itch_publish.py password-manager   # a specific one
```

## Replacing a paid build that already shipped

The Friday lane only builds the week's new app, and `paid/` is never committed.
`rebuild-paid.yml` restores the private `paid-build` artifact from the verifier
run and rebuilds from that real paid source; it never reconstructs a paid
product from a committed free edition.

```bash
gh workflow run rebuild-paid.yml -f slug=file-renamer -f source_run_id=<verify run id>
```

That replaces this product's build on **this product's own** project. The
rebuild refuses to run while the catalogue still points at the shared project.
It leaves the price alone; `publish_paid.py` still has to see the store charging
the advertised price first.

## Keep the paid file out of the repository

`paid/` is gitignored and `check_repo_hygiene.py` fails the build if it is ever
tracked. `check_exposure.py` also fails if two products share an `itch_url`, or
if a product's URL names another product's page.

## Payouts

Selling is immediate. Getting the money out is separate: itch.io's own payout
system needs a tax interview, and payouts go to PayPal or Payoneer. You can
sell before either is set up. See <https://itch.io/docs/creators/payments>.
