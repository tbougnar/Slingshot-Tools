"""Generate a private local dashboard (never published).

Writes ./dashboard.html with embedded data so it can be opened locally
without any server and without exposing anything on GitHub Pages.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def dashboard_data() -> dict:
    earn = load(ROOT / "data/earnings.json", {})
    prices = load(ROOT / "data/prices.json", {})
    reputation = load(ROOT / "data/reputation.json", {})
    goals = load(ROOT / "data/goals.json", {})
    fixbook = load(ROOT / "data/fixbook.json", [])
    wrev = load(ROOT / "data/weekly_reviews.json", {})
    apps = load(ROOT / "site/apps.json", [])
    votes = load(ROOT / "site/votes.json", {})
    events = load(ROOT / "site/events.json", {})
    weekly_state = load(ROOT / "data/weekly_state.json", {})
    latest_week = sorted(wrev.keys())[-1] if wrev else None
    latest_review = wrev.get(latest_week) if latest_week else None
    latest_fix = fixbook[-1] if fixbook else None
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "revenue": earn,
        "prices": prices,
        "reputation": reputation,
        "goals": goals,
        "products": apps,
        "votes": votes,
        "events": events,
        "weekly_state": weekly_state,
        "latest_week": latest_week,
        "latest_review": latest_review,
        "latest_fixbook_entry": latest_fix,
        "known_problems_count": len(fixbook),
        "recent_fixbook": fixbook[-10:] if fixbook else [],
    }


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Private Dashboard — Slingshot Tools</title>
  <style>
    :root{--bg:#0b0b0d;--card:#151517;--ink:#f5f5f7;--sub:#b9b9c3;--line:#2a2a31;--red:#ff4d4d;--green:#4ade80;--amber:#fbbf24;}
    *{box-sizing:border-box}
    body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:radial-gradient(1200px 800px at 20% -10%,#1a1a20,transparent),var(--bg);color:var(--ink)}
    .wrap{max-width:1200px;margin:0 auto;padding:20px}
    h1{margin:0 0 6px;font-size:28px} h2{margin:0 0 12px;font-size:18px}
    .sub{color:var(--sub);margin:0 0 20px}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-bottom:16px}
    .card{background:linear-gradient(180deg,rgba(255,255,255,.03),transparent);border:1px solid var(--line);border-radius:14px;padding:16px}
    .stat{font-size:28px;font-weight:800;margin:4px 0}
    .label{color:var(--sub);font-size:13px;text-transform:uppercase;letter-spacing:.05em}
    .muted{color:var(--sub)}
    pre{white-space:pre-wrap;word-break:break-word;background:#101014;border:1px solid var(--line);border-radius:10px;padding:12px;color:#e8e8ea;font-size:13px;line-height:1.45;margin:0}
    .list{display:grid;gap:10px}
    .item{border:1px solid var(--line);border-radius:10px;padding:12px;background:rgba(255,255,255,.02)}
    .row{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}
    .pill{font-size:12px;padding:3px 8px;border:1px solid var(--line);border-radius:999px;color:var(--sub)}
    .topbar{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:16px;flex-wrap:wrap}
    .note{border:1px solid #3a2a12;background:#1a140d;color:#ffdca8;padding:10px 12px;border-radius:10px;margin-bottom:14px}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <h1>Slingshot Private Dashboard</h1>
        <p class="sub" id="updated"></p>
      </div>
      <div class="muted">Localhost only</div>
    </div>
    <div class="note">Private dashboard. Served locally for this PC only. Not published.</div>

    <div class="grid" id="stats"></div>
    <div class="grid">
      <div class="card" style="grid-column:1/-1"><h2>Latest Learning</h2><div id="latestLearn" class="muted"></div></div>
      <div class="card"><h2>Products</h2><div id="products" class="muted"></div></div>
      <div class="card"><h2>Votes & Events</h2><div id="votesEvents" class="muted"></div></div>
      <div class="card" style="grid-column:1/-1"><h2>Recent Fixbook / Status</h2><div id="fixbook" class="muted"></div></div>
      <div class="card" style="grid-column:1/-1"><h2>Goals, Revenue & State</h2><div id="goalsState" class="muted"></div></div>
    </div>
  </div>

<script>
const d = __DASHBOARD_DATA__;
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[m]));}
function render(){
  document.getElementById('updated').textContent = 'Generated: ' + (d.generated || 'unknown') + ' · Latest week: ' + (d.latest_week || 'n/a');
  const rev = d.revenue || {};
  const orders = rev.orders ?? (rev.total_orders ?? 0);
  const total = rev.total ?? (rev.revenue ?? 0);
  const productsCount = Array.isArray(d.products) ? d.products.length : 0;
  const known = d.known_problems_count ?? 0;
  const rep = d.reputation || {};
  const stats = [
    ['Revenue', '$' + Number(total||0).toFixed(2), orders + ' order(s)'],
    ['Products', String(productsCount), 'catalog entries on site'],
    ['Latest Week', d.latest_week || 'n/a', (d.latest_review && d.latest_review.text ? 'review recorded' : 'no review text')],
    ['Known Problems', String(known), 'fixbook entries'],
    ['Stars', String(rep.stars ?? (rep.github||{}).stars ?? 'n/a'), 'public signals'],
    ['Votes', String((d.votes && d.votes.poll && d.votes.poll.options ? d.votes.poll.options.reduce((s,o)=>s+(o.votes||0),0):0)), 'current ballot total'],
  ];
  document.getElementById('stats').innerHTML = stats.map(s=>`<div class="card"><div class="label">${esc(s[0])}</div><div class="stat">${esc(s[1])}</div><div class="muted">${esc(s[2])}</div></div>`).join('');

  const lr = d.latest_review;
  if(lr && lr.text){
    document.getElementById('latestLearn').innerHTML = `<div class="row" style="margin-bottom:10px"><span class="pill">${esc(lr.week||d.latest_week||'')}</span><span class="muted">Revenue: $${Number((lr.revenue||{}).total||0).toFixed(2)} · Votes: ${esc(lr.ballot_votes||0)} · Products: ${esc((lr.products||[]).length)}</span></div><pre>${esc(lr.text)}</pre>`;
  } else if(d.latest_fixbook_entry){
    const f = d.latest_fixbook_entry;
    document.getElementById('latestLearn').innerHTML = `<div class="row" style="margin-bottom:10px"><span class="pill">${esc(f.id||'')}</span><span class="muted">${esc(f.date||'')}</span></div><div><strong>${esc(f.symptom||'')}</strong></div><div class="muted" style="margin-top:8px">${esc(f.cause||'')}</div>`;
  } else { document.getElementById('latestLearn').textContent = 'No learning data found.'; }

  const prods = Array.isArray(d.products) ? d.products : [];
  document.getElementById('products').innerHTML = prods.length ? '<div class="list">' + prods.map(p=>`<div class="item"><div class="row"><strong>${esc(p.title||p.slug||'Product')}</strong><span class="pill">${esc(p.tier||'')}</span></div><div class="muted">${esc(p.tag||'')} · $${Number(p.price||0).toFixed(2)} ${p.published===false?'· hidden':''}</div></div>`).join('') + '</div>' : '<div class="muted">No products in site/apps.json yet.</div>';

  let ve = '';
  const poll = d.votes && d.votes.poll ? d.votes.poll : null;
  if(poll){
    const totalVotes = (poll.options||[]).reduce((s,o)=>s+(o.votes||0),0);
    ve += `<div class="item"><div class="row"><strong>Current Vote</strong><span class="pill">${esc(poll.id||'')}</span></div><div class="muted" style="margin:6px 0">${esc(poll.question||'')}</div>` + (poll.options||[]).map(o=>{const pct=totalVotes?Math.round((o.votes||0)/totalVotes*100):0; return `<div style="margin:6px 0"><div class="row"><span>${esc(o.label)}</span><span class="muted">${pct}% (${o.votes||0})</span></div><div style="height:6px;background:#222;border-radius:999px;overflow:hidden"><div style="height:100%;width:${pct}%;background:#ff6b6b"></div></div></div>`;}).join('') + `</div>`;
  } else { ve += '<div class="item muted">No active vote data.</div>'; }
  const evs = (d.events && d.events.events) ? d.events.events : [];
  if(evs.length){ ve += '<div class="item"><strong>Events</strong>' + evs.map(e=>`<div style="margin-top:8px"><div>${esc(e.title||'')}</div><div class="muted">${esc(e.date||'')} — ${esc(e.description||'')}</div></div>`).join('') + '</div>'; }
  document.getElementById('votesEvents').innerHTML = ve;

  const recent = Array.isArray(d.recent_fixbook) ? d.recent_fixbook.slice().reverse() : [];
  document.getElementById('fixbook').innerHTML = recent.length ? '<div class="list">' + recent.map(f=>`<div class="item"><div class="row"><strong>${esc(f.id||'')}</strong><span class="pill">${esc(f.date||'')}</span></div><div style="margin-top:6px"><strong>${esc(f.symptom||'')}</strong></div><div class="muted" style="margin-top:6px">${esc((f.cause||'').slice(0,400))}</div><div class="muted" style="margin-top:6px">Fix: ${esc(f.fix||'')}</div><div class="muted">Status: ${esc(f.verified ? 'verified' : 'untested')}</div></div>`).join('') + '</div>' : 'No fixbook entries.';

  document.getElementById('goalsState').innerHTML = `<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr));margin:0"><div class="item"><strong>Goals</strong><pre>${esc(JSON.stringify(d.goals||{}, null, 2))}</pre></div><div class="item"><strong>Weekly State</strong><pre>${esc(JSON.stringify(d.weekly_state||{}, null, 2))}</pre></div><div class="item"><strong>Revenue Detail</strong><pre>${esc(JSON.stringify(d.revenue||{}, null, 2))}</pre></div><div class="item"><strong>Reputation</strong><pre>${esc(JSON.stringify(d.reputation||{}, null, 2))}</pre></div><div class="item" style="grid-column:1/-1"><strong>Prices</strong><pre>${esc(JSON.stringify(d.prices||{}, null, 2))}</pre></div></div>`;
}
render();
</script>
</body>
</html>"""


def build_dashboard_html() -> str:
    data_json = json.dumps(dashboard_data(), ensure_ascii=False)
    return TEMPLATE.replace("__DASHBOARD_DATA__", data_json)


def main() -> int:
    out = ROOT / "dashboard.html"
    out.write_text(build_dashboard_html(), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
