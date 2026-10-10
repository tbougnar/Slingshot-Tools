# Live PayPal: switch the worker from sandbox to live

Your PayPal account is verified, so the worker can now take real money. It is
still pointed at **sandbox**, which is why `/api/order` hands out a
`www.sandbox.paypal.com` approval link: no real money can move until this is
flipped.

## 1. Get the Live REST credentials

Developer Portal -> **Apps & Credentials** -> the **Live** tab -> **Create
app** (or pick an existing one).

Open the app and copy:

- **Client ID** (`A...`)
- **Secret** (`EO...`)

Use the **Live** tab, not Sandbox. The sandbox pair is rejected by the live
API with `401 invalid_client`, which is exactly the error seen so far.

## 2. Add them to the worker as secrets

From the repository root:

```bash
npx wrangler secret put PAYPAL_CLIENT_ID
npx wrangler secret put PAYPAL_SECRET
```

Paste the value at each prompt. Secrets are never written to a file.

## 3. Flip the environment

In `worker/wrangler.toml`:

```toml
PAYPAL_ENV = "live"
```

Commit that, then deploy:

```bash
npx wrangler deploy
```

## 4. Prove it works

```bash
python verify_live_paypal.py
```

That creates a real order and prints the approval URL. Open it, pay **$1.00 or
the real price**, then:

- `#announcements` should be the only place an announcement is posted, and
- `/api/download` should hand back the installer

Check that the money lands in your PayPal balance. Then run the pipeline's own
gate:

```bash
python selftest.py
```

## What has already been checked

- The `BUILDS` KV binding is repaired, so `/api/download` will find the build.
  See B061.
- Price is clamped server-side to $1.00-$10.00, so a bad client cannot charge
  anything else.
- `/api/download` refuses until PayPal reports the order `COMPLETED`, and it
  only serves a build whose slug matches the order's product reference.
- `check_exposure.py` confirms the paid build is never copied into the public
  site.

## Rolling back

If live charges go wrong, set `PAYPAL_ENV = "sandbox"` in `wrangler.toml`,
commit, and `npx wrangler deploy`. Orders already captured are not affected.