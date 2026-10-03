/**
 * Slingshot Tools payment API.
 *
 * POST /api/order  {slug, price, title, email} -> {approve, order}
 * GET  /api/key?token=<orderId>                -> {key, title} once paid
 *
 * Secrets: PAYPAL_CLIENT_ID, PAYPAL_SECRET, PAYPAL_ENV, LICENSE_SECRET
 */
const ALLOW = (env) => [env.SITE_ORIGIN].filter(Boolean);
const cors = (req, env) => {
  const o = req.headers.get("Origin") || "";
  const ok = ALLOW(env).includes(o) ? o : (ALLOW(env)[0] || o);
  return {
    "Access-Control-Allow-Origin": ok,
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
};
const json = (body, status, req, env) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...cors(req, env) },
  });

const b64 = (s) => btoa(s);
const api = (env) =>
  (env.PAYPAL_ENV === "live" ? "https://api-m.paypal.com" : "https://api-m.sandbox.paypal.com");

async function token(env) {
  const r = await fetch(`${api(env)}/v1/oauth2/token?grant_type=client_credentials`, {
    method: "POST",
    headers: {
      Authorization: "Basic " + b64(`${env.PAYPAL_CLIENT_ID}:${env.PAYPAL_SECRET}`),
      Accept: "application/json",
      "Content-Type": "application/x-www-form-urlencoded",
    },
  });
  const d = await r.json();
  if (!d.access_token) throw new Error("paypal auth failed");
  return d.access_token;
}

async function paypal(env, path, method = "GET", body = null, tok) {
  const r = await fetch(`${api(env)}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${tok}`,
      Accept: "application/json",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const t = await r.text();
  try { return JSON.parse(t); } catch { return { raw: t }; }
}

// ---- license keys: HMAC signed, tied to one product ----
const enc = new TextEncoder();
async function signKey(env, slug, raw) {
  const k = await crypto.subtle.importKey(
    "raw", enc.encode(env.LICENSE_SECRET || "slingshot-dev"),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(
    await crypto.subtle.sign("HMAC", k, enc.encode(`slingshot|${slug}|${raw}`)));
  return [...sig].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 8);
}
const rawKey = () => {
  const b = new Uint8Array(24);
  crypto.getRandomValues(b);
  return [...b].map((x) => x.toString(36).padStart(2, "0")).join("").slice(0, 24);
};
async function newKey(env, slug) {
  const raw = rawKey();
  return `SS-${raw.slice(0, 16)}-${raw.slice(16)}-${await signKey(env, slug, raw)}`;
}

export default {
  async fetch(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { headers: cors(req, env) });
    const url = new URL(req.url);
    try {
      if (url.pathname === "/api/order" && req.method === "POST") {
        const body = await req.json().catch(() => ({}));
        const slug = String(body.slug || "").replace(/[^a-z0-9-]/g, "").slice(0, 40);
        const price = Math.max(Math.round(Number(body.price) * 100) / 100, 0.5);
        if (!slug) return json({ error: "Missing product." }, 400, req, env);

        const tok = await token(env);
        const order = await paypal(env, "/v2/checkout/orders", "POST", {
          intent: "CAPTURE",
          purchase_units: [{
            reference_id: slug,
            custom_id: slug,
            description: String(body.title || "Full edition").slice(0, 120),
            amount: { currency_code: "USD", value: price.toFixed(2) },
          }],
          application_context: {
            brand_name: "Slingshot Tools",
            user_action: "PAY_NOW",
            shipping_preference: "NO_SHIPPING",
            return_url: `${env.SITE_ORIGIN}/full.html`,
            cancel_url: `${env.SITE_ORIGIN}/checkout.html?cancelled=1`,
          },
        }, tok);

        if (!order.id) return json({ error: "PayPal rejected the order." }, 502, req, env);
        const approve = (order.links || []).find((l) => l.rel === "approve" || l.rel === "payer-action");
        return json({ order: order.id, approve: approve ? approve.href : "", price }, 200, req, env);
      }

      if (url.pathname === "/api/key" && req.method === "GET") {
        const id = url.searchParams.get("token") || "";
        if (!/^[A-Z0-9]{10,32}$/.test(id)) return json({ error: "Bad order reference." }, 400, req, env);

        const tok = await token(env);
        const order = await paypal(env, `/v2/checkout/orders/${id}`, "GET", null, tok);
        if (order.status === "APPROVED") {
          await paypal(env, `/v2/checkout/orders/${id}/capture`, "POST", {}, tok);
        }
        const check = await paypal(env, `/v2/checkout/orders/${id}`, "GET", null, tok);
        if (check.status !== "COMPLETED") {
          return json({ status: check.status || "PENDING" }, 202, req, env);
        }

        const unit = (check.purchase_units || [])[0] || {};
        const slug = unit.custom_id || unit.reference_id || "";
        if (!slug) return json({ error: "Order is missing its product reference." }, 400, req, env);

        // one stable key per product, reused by every buyer
        const marker = `${slug}::${env.KEY_STORE_VERSION || "1"}`;
        const old = await env.KEYS.get(marker);
        const key = old || await newKey(env, slug);
        await env.KEYS.put(marker, key);

        const amount = (unit.amount && unit.amount.value) || "0.00";
        return json({ key, title: unit.description || slug, amount, email: (check.payer || {}).email_address || "" }, 200, req, env);
      }

      return json({ error: "Not found" }, 404, req, env);
    } catch (e) {
      return json({ error: String(e && e.message || e) }, 500, req, env);
    }
  },
};