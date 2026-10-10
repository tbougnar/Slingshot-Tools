# Sell on itch.io instead

itch.io is the merchant. It handles the payment, hosts the paid download, and
sends the buyer their files. Nothing in this repository takes money any more.

## Why

PayPal's API needs a **Business account** to switch to live mode, which needs a
tax ID and a matching bank account. Without that, the payment worker cannot
take a single real payment. itch.io does not have that requirement for
*selling*: you create a project, upload the file, set a price, and buyers pay
you. That is the whole point of moving.

## What the site does now

The storefront links straight to your itch.io project page. There is no
checkout form, no order API, and no download endpoint in this repository.

```
site/checkout.html   ->  redirects to the itch.io page for that tool
```

One URL per product lives in `site/apps.json`, and the pipeline copies the
`itch_url` into the button. Nothing else changes.

## Set it up once, by hand

You do this part, because it needs your itch.io account.

1. Go to <https://itch.io/settings/user> and confirm your email. Without it you
   cannot upload files.
2. Create a project: <https://itch.io/settings/mine/new/game>
   - Title: the tool's name
   - **Pricing**: "Set a price", the amount the pipeline picked
   - **Kind of project**: "Downloadable"
   - Cover image: the tool's `icon.png`
3. Upload the installer as a **Downloadable file**, and tick
   "This file is the primary download".
4. Copy the project URL, for example
   `https://yourslug.itch.io/offline-password-manager`
5. Put it in the catalog:

```bash
python set_itch_url.py password-manager https://yourslug.itch.io/offline-password-manager
```

That writes `itch_url` into `site/apps.json` for both editions of the family.
The buy button uses it, and without it the button still says "coming soon"
rather than sending anyone nowhere.

## Every week, for each new tool

The pipeline builds the installer and tells you where it is. You then:

1. Create the itch.io project, set the price, upload the `.exe`.
2. Run the command above with the new URL.

That is one manual step per week, and it is the only manual step in selling.

## What was removed

| Removed | Why |
|---|---|
| `worker/worker.js` | the PayPal order and download API |
| `worker/wrangler.toml` | its deployment config |
| `verify_live_paypal.py` | it only checked the PayPal worker |
| `paid_store.py` | uploaded the paid build to Cloudflare KV for the worker to serve |
| `site/full.html` | the payment-confirmation and download page |

The Cloudflare worker can stay deployed and unused, or you can delete it:

```bash
npx wrangler delete
```

Nothing calls it once the links point at itch.io.

## What was kept

- The **free** editions, still served from GitHub Pages
- The **installer build**, still produced every Friday. You upload that file to
  itch.io by hand
- The pricing logic. itch.io needs a number, so the pipeline still decides one
  inside `$1.00`-$10.00` and prints it for you to type in
- The Discord announcements, unchanged

## Payouts, honestly

Selling on itch.io works immediately. **Getting the money out** is a separate
question:

- itch.io's own payout system needs a tax interview, and a Tax ID to avoid the
  default 30% withholding
- payouts go to PayPal or Payoneer, so you need one of those accounts

You can list and sell before either is set up, and sort the payout out later.
That is a better position than now, where you cannot take a payment at all.

See <https://itch.io/docs/creators/payments> for the current rules.

## Security

itch.io hosts the paid file, so `paid/` stays out of the public repository and
`check_exposure.py` still fails the build if a paid edition ever appears under
`site/`. `check_repo_hygiene.py` still refuses to track `paid/`.