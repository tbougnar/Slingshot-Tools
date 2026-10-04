/**
 * Slingshot Tools payment API.
 *
 * POST /api/order  {slug, price, title, email} -> {approve, order}
 * GET  /api/download?token=<orderId>          -> the paid build, after payment
 *
 * No license keys: payment authorises the download directly. The paid build is
 * never in the published site, so this endpoint is the only way to obtain it,
 * and it refuses until PayPal reports the order COMPLETED.
 */
const cors = (req, env) => {
  const allow = (env.SITE_ORIGIN || "").replace(/\/+$/, "");
  const o = req.headers.get("Origin") || "";
  return {
    "Access-Control-Allow-Origin": allow && o === allow ? o : allow,
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
};
const base = (env) => `${(env.SITE_ORIGIN || "").replace(/\/+$/, "")}${env.SITE_PATH || ""}`;
const json = (body, status, req, env) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...cors(req, env) },
  });
const api = (env) =>
  (env.PAYPAL_ENV === "live" ? "https://api-m.paypal.com" : "https://api-m.sandbox.paypal.com");

async function token(env) {
  const r = await fetch(`${api(env)}/v1/oauth2/token?grant_type=client_credentials`, {
    method: "POST",
    headers: {
      Authorization: "Basic " + btoa(`${env.PAYPAL_CLIENT_ID}:${env.PAYPAL_SECRET}`),
      Accept: "application/json",
      "Content-Type": "application/x-www-form-urlencoded",
    },
  });
  const d = await r.json();
  if (!d.access_token) throw new Error("paypal auth failed");
  return d.access_token;
}

async function pp(env, path, method = "GET", body = null, tok) {
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

export default {
  async fetch(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { headers: cors(req, env) });
    const url = new URL(req.url);
    const BAD = { success: false, error: "Not found" };
    try {
      // ---------------- create the order ----------------
      if (url.pathname === "/api/order" && req.method === "POST") {
        const body = await req.json().catch(() => ({}));
        const slug = String(body.slug || "").replace(/[^a-z0-9-]/g, "").slice(0, 40);
        // The AI picks the price, but never outside $1.00 - $10.00.
        const price = Math.min(Math.max(Math.round(Number(body.price) * 100) / 100, 1.0), 10.0);
        if (!slug) return json({ error: "Missing product." }, 400, req, env);
        if (!env.BUILDS) return json({ error: "Store is not configured." }, 503, req, env);

        const tok = await token(env);
        const order = await pp(env, "/v2/checkout/orders", "POST", {
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
            return_url: `${base(env)}/full.html`,
            cancel_url: `${base(env)}/checkout.html?cancelled=1`,
          },
        }, tok);

        if (!order.id) return json({ error: "PayPal rejected the order." }, 502, req, env);
        const approve = (order.links || []).find((l) => l.rel === "approve" || l.rel === "payer-action");
        return json({ order: order.id, approve: approve ? approve.href : "", price }, 200, req, env);
      }

      // ---------------- hand over the paid build ----------------
      if (url.pathname === "/api/download" && req.method === "GET") {
        const id = url.searchParams.get("token") || "";
        if (!/^[A-Z0-9]{10,32}$/.test(id)) return json({ error: "Bad order reference." }, 400, req, env);

        const tok = await token(env);
        let order = await pp(env, `/v2/checkout/orders/${id}`, "GET", null, tok);
        if (order.status === "APPROVED") {
          order = await pp(env, `/v2/checkout/orders/${id}/capture`, "POST", {}, tok);
        }
        if (order.status !== "COMPLETED") {
          return json({ status: order.status || "PENDING" }, 202, req, env);
        }

        const unit = (order.purchase_units || [])[0] || {};
        const slug = unit.custom_id || unit.reference_id || "";
        if (!slug) return json({ error: "Order has no product reference." }, 400, req, env);

        // The build is stored in chunks because the store rejects a single large
        // value. Join them back into one complete exe before replying.
        const parts = [];
        for (let n = 1; n <= 32; n++) {
          const buf = await env.BUILDS.get(`build:${slug}:${n}`, "arrayBuffer");
          if (!buf) break;
          if (buf.byteLength === 0) break;
          parts.push(new Uint8Array(buf));
        }
        if (!parts.length) return json({ error: "Build not found for this order." }, 404, req, env);
        const total = parts.reduce((a, p) => a + p.length, 0);
        const file = new Uint8Array(total);
        let at = 0;
        for (const p of parts) { file.set(p, at); at += p.length; }

        const name = slug.toLowerCase().replace(/[^a-z0-9-]/g, "-");
        return new Response(file, {
          headers: {
            "Content-Type": "application/octet-stream",
            "Content-Disposition": `attachment; filename="SlingshotTool-${name}-Setup.exe"`,
            "Content-Length": String(file.byteLength),
            ...cors(req, env),
          },
        });
      }

      return json(BAD, 404, req, env);
    } catch (e) {
      return json({ error: String((e && e.message) || e) }, 500, req, env);
    }
  },
};