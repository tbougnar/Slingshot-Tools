/* Shared storefront behaviour: cart, previews and safe links.
 *
 * Payment is never taken here. Every product is paid for on its own itch.io
 * page, so the cart is only a list of things the visitor intends to buy; its
 * checkout button opens cart.html, which links to each product's real store
 * page. This also means a new app in apps.json appears in the store without
 * anybody editing these files.
 */
(function () {
  "use strict";

  var KEY = "slingshot-cart-v1";
  var CATALOG = [];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
               "'": "&#39;" }[c];
    });
  }

  /* Only a published paid edition with its own store page belongs on the
   * site. This mirrors groupProducts() on the homepage and is the rule that
   * stopped a free fallback from being sold beside the paid app. */
  function onSale(a) {
    return !!a && a.tier !== "basic" && a.published !== false && !!a.itch_url;
  }

  function family(list) {
    var by = {};
    (Array.isArray(list) ? list : []).forEach(function (a) {
      var k = a.base_slug || a.slug;
      (by[k] = by[k] || []).push(a);
    });
    return Object.keys(by).map(function (k) {
      var paid = by[k].filter(onSale);
      if (!paid.length) return null;
      var full = paid[0];
      return { key: k, lead: full, full: full,
               diffs: full.differences || [], onSale: true };
    }).filter(Boolean);
  }

  function slugOf(item) {
    return (item && (item.key || (item.lead && (item.lead.base_slug ||
             item.lead.slug)))) || "";
  }

  function titleOf(item) {
    return String((item && item.lead && item.lead.title) || "")
      .replace(/\s*\(basic\)\s*$/i, "");
  }

  function priceOf(item) {
    return Number((item && item.lead && item.lead.price) || 0);
  }

  function productUrl(item) {
    return "product.html?slug=" + encodeURIComponent(slugOf(item));
  }

  /* The itch URL comes from the catalogue, and is validated before it is
   * used as an href. A bad value must never become a javascript: link. */
  function buyUrl(item) {
    var a = item && item.lead;
    if (!a || !/^https:\/\/[^/\s]+\.itch\.io\/[^\s"'<>]+$/.test(a.itch_url || "")) {
      return "";
    }
    return "checkout.html?slug=" + encodeURIComponent(item.key || a.slug) +
      "&price=" + Number(a.price || 0).toFixed(2) +
      "&title=" + encodeURIComponent(titleOf(item)) +
      "&itch=" + encodeURIComponent(a.itch_url);
  }

  function load() {
    try {
      var raw = localStorage.getItem(KEY);
      var arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr.filter(function (s) {
        return typeof s === "string" && /^[a-z0-9-]{1,80}$/.test(s);
      }) : [];
    } catch (e) { return []; }
  }

  function save(items) {
    try { localStorage.setItem(KEY, JSON.stringify(items)); } catch (e) {}
    document.dispatchEvent(new CustomEvent("slingshot-cart"));
  }

  function cart() { return load(); }

  function add(slug) {
    var clean = String(slug || "");
    if (!/^[a-z0-9-]{1,80}$/.test(clean)) return false;
    var items = load();
    if (items.indexOf(clean) === -1) items.push(clean);
    save(items);
    return true;
  }

  function remove(slug) {
    save(load().filter(function (s) { return s !== slug; }));
  }

  function clear() { save([]); }

  /* A screenshot-style preview drawn from the product's own details. No
   * binary has to be shipped for every new app: the pipeline adds one entry
   * to apps.json and the product immediately has a preview and a page.
   * The three modes are the gallery views on the product page. */
  function shot(item, mode) {
    var a = (item && item.lead) || item || {};
    var title = esc(titleOf(item) || a.title || "Slingshot app");
    var tag = esc((a.tag || "tool").toUpperCase());
    var light = mode === "light";
    var detail = mode === "detail";
    var bg = light ? "#f4f2f1" : "#0d0d0d";
    var frame = light ? "#ffffff" : "#171717";
    var bar = light ? "#ece9e7" : "#101010";
    var lane = light ? "#f7f5f4" : "#131313";
    var line = light ? "#ded8d5" : "#2b2b2b";
    var ink = light ? "#1b1716" : "#ededed";
    var dim = light ? "#7d7370" : "#9a9a9a";
    var accent = "#c1272d";

    var nav = ["Overview", "Library", "Settings", "Help"];
    var sidebar = nav.map(function (n, i) {
      var active = i === 0;
      return '<rect x="112" y="' + (214 + i * 62) + '" width="164" height="42" rx="9" fill="' +
        (active ? (light ? "#f0e7e6" : "#222020") : "none") + '"/>' +
        (active ? '<rect x="112" y="' + (214 + i * 62) + '" width="3" height="42" rx="2" fill="' + accent + '"/>' : '') +
        '<circle cx="134" cy="' + (235 + i * 62) + '" r="5" fill="' + (active ? accent : dim) + '"/>' +
        '<text x="150" y="' + (240 + i * 62) + '" fill="' +
        (active ? ink : dim) + '" font-size="15">' + esc(n) + '</text>';
    }).join("");

    var rows = ["Ready to use", "Saved locally", "No account needed"];
    var list = rows.map(function (r, i) {
      var y = 486 + i * 62;
      return '<rect x="330" y="' + y + '" width="710" height="48" rx="10" fill="' + lane + '" stroke="' + line + '"/>' +
        '<circle cx="360" cy="' + (y + 24) + '" r="8" fill="none" stroke="' + dim + '" stroke-width="2"/>' +
        '<text x="384" y="' + (y + 30) + '" fill="' + ink + '" font-size="16">' + esc(r) + '</text>' +
        '<rect x="958" y="' + (y + 16) + '" width="56" height="16" rx="8" fill="' +
        (i === 2 ? line : (light ? "#f0e7e6" : "#282222")) + '"/>';
    }).join("");

    var panel = detail
      ? '<rect x="330" y="294" width="710" height="160" rx="14" fill="' + lane + '" stroke="' + line + '"/>' +
        '<text x="362" y="344" fill="' + dim + '" font-size="15">WORKSPACE</text>' +
        '<text x="362" y="392" fill="' + ink + '" font-size="34" font-weight="600">' + title + '</text>' +
        '<rect x="362" y="412" width="150" height="8" rx="4" fill="' + accent + '"/>' +
        '<rect x="524" y="412" width="96" height="8" rx="4" fill="' + line + '"/>'
      : '<rect x="330" y="294" width="344" height="160" rx="14" fill="' + lane + '" stroke="' + line + '"/>' +
        '<text x="360" y="334" fill="' + dim + '" font-size="14">BUILT FOR</text>' +
        '<text x="360" y="382" fill="' + ink + '" font-size="28" font-weight="600">' + tag + '</text>' +
        '<text x="360" y="418" fill="' + dim + '" font-size="15">Offline · Windows</text>' +
        '<rect x="694" y="294" width="346" height="160" rx="14" fill="' + lane + '" stroke="' + line + '"/>' +
        '<text x="724" y="334" fill="' + dim + '" font-size="14">LICENSE</text>' +
        '<text x="724" y="382" fill="' + ink + '" font-size="28" font-weight="600">One-time</text>' +
        '<text x="724" y="418" fill="' + dim + '" font-size="15">Yours forever</text>';

    return '<svg viewBox="0 0 1200 820" xmlns="http://www.w3.org/2000/svg" role="img" ' +
      'aria-label="Preview of ' + title + '" preserveAspectRatio="xMidYMid meet">' +
      '<rect width="1200" height="820" fill="' + bg + '"/>' +
      '<rect x="80" y="64" width="1040" height="692" rx="16" fill="' + frame + '" stroke="' + line + '"/>' +
      '<path d="M80 80a16 16 0 0 1 16-16h1008a16 16 0 0 1 16 16v40H80z" fill="' + bar + '"/>' +
      '<circle cx="112" cy="88" r="5" fill="' + accent + '"/>' +
      '<circle cx="132" cy="88" r="5" fill="' + dim + '"/>' +
      '<circle cx="152" cy="88" r="5" fill="' + dim + '"/>' +
      '<text x="182" y="94" fill="' + dim + '" font-size="14">' + title + ' — ' + tag + '</text>' +
      '<text x="1080" y="94" text-anchor="end" fill="' + dim + '" font-size="14">LOCAL</text>' +
      '<path d="M292 120v636" stroke="' + line + '"/>' + sidebar + panel + list +
      '<text x="112" y="724" fill="' + dim + '" font-size="13">Slingshot Tools · no account · no subscription</text>' +
      '</svg>';
  }

  function lineFor(item) {
    var a = item.lead;
    var buy = buyUrl(item);
    return '<div class="cart-line" data-slug="' + esc(slugOf(item)) + '">' +
      '<div class="cart-thumb">' + shot(item, "dark") + '</div>' +
      '<div class="cart-line-body"><div class="cart-line-title">' + esc(titleOf(item)) + '</div>' +
      '<div class="cart-line-sub">' + esc((a.tag || "tool")) + ' · Windows · one-time</div>' +
      '<button class="cart-remove" type="button" data-remove="' + esc(slugOf(item)) + '">Remove</button></div>' +
      '<div class="cart-line-price">$' + priceOf(item).toFixed(2) + '</div>' +
      (buy ? '<a class="cart-buy" href="' + esc(buy) + '">Buy on itch.io</a>' : '') +
      '</div>';
  }

  function renderDrawer(catalog) {
    var holder = document.getElementById("cartBody");
    var countEl = document.getElementById("cartCount");
    var totalEl = document.getElementById("cartTotal");
    var ids = cart();
    var all = family(catalog);
    var chosen = ids.map(function (id) {
      return all.filter(function (p) { return slugOf(p) === id; })[0];
    }).filter(Boolean);
    if (countEl) countEl.textContent = String(ids.length);
    document.querySelectorAll("[data-cart-count]").forEach(function (el) {
      el.textContent = String(ids.length);
    });
    if (holder) {
      holder.innerHTML = chosen.length
        ? chosen.map(lineFor).join("")
        : '<div class="cart-empty">Your cart is empty.<br><a href="./">Browse the tools</a></div>';
    }
    if (totalEl) {
      totalEl.textContent = "$" + chosen.reduce(function (s, p) {
        return s + priceOf(p);
      }, 0).toFixed(2);
    }
    var go = document.getElementById("cartGo");
    if (go) go.href = "cart.html";
  }

  function openDrawer() {
    var d = document.getElementById("cartDrawer");
    if (!d) return;
    d.classList.add("open");
    d.setAttribute("aria-hidden", "false");
    var b = d.querySelector("button");
    if (b) b.focus();
  }

  function closeDrawer() {
    var d = document.getElementById("cartDrawer");
    if (!d) return;
    d.classList.remove("open");
    d.setAttribute("aria-hidden", "true");
  }

  /* The drawer is the same on every page, so it is built here once instead of
   * being pasted into three HTML files where the copies would drift apart. */
  function injectDrawer() {
    if (document.getElementById("cartDrawer")) return;
    var d = document.createElement("div");
    d.className = "cart-overlay";
    d.id = "cartDrawer";
    d.setAttribute("role", "dialog");
    d.setAttribute("aria-modal", "true");
    d.setAttribute("aria-label", "Your cart");
    d.setAttribute("aria-hidden", "true");
    d.innerHTML = '<div class="cart-panel">' +
      '<div class="cart-head"><h2>Your cart <span data-cart-count>0</span></h2>' +
      '<button type="button" data-cart-close aria-label="Close cart">&times;</button></div>' +
      '<div id="cartBody"></div>' +
      '<div class="cart-foot"><div class="cart-total-row"><span>Total</span>' +
      '<strong id="cartTotal">$0.00</strong></div>' +
      '<a id="cartGo" class="cart-go" href="cart.html">Review cart</a>' +
      '<p>Payment is taken on each product&rsquo;s own itch.io page. ' +
      'This site never sees your card.</p></div></div>';
    document.body.appendChild(d);
  }

  /* Pages load the catalogue with fetch(), after this script has run. Keeping
   * one copy here means the cart can be drawn before and after that fetch
   * without registering its listeners twice. */
  function setCatalog(list) {
    CATALOG = Array.isArray(list) ? list : [];
    renderDrawer(CATALOG);
  }

  function init() {
    injectDrawer();
    document.addEventListener("click", function (e) {
      var t = e.target.closest ? e.target : null;
      if (!t) return;
      if (t.closest("[data-cart-open]")) { e.preventDefault(); openDrawer(); }
      if (t.closest("[data-cart-close]")) { e.preventDefault(); closeDrawer(); }
      var addBtn = t.closest("[data-add]");
      if (addBtn) {
        add(addBtn.getAttribute("data-add"));
        openDrawer();
      }
      var rm = t.closest("[data-remove]");
      if (rm) { remove(rm.getAttribute("data-remove")); renderDrawer(CATALOG); }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDrawer();
    });
    document.addEventListener("slingshot-cart", function () {
      renderDrawer(CATALOG);
    });
    window.addEventListener("storage", function () {
      renderDrawer(CATALOG);
    });
    renderDrawer(CATALOG);
  }

  window.SlingshotStore = {
    esc: esc, onSale: onSale, family: family, slugOf: slugOf,
    titleOf: titleOf, priceOf: priceOf, productUrl: productUrl,
    buyUrl: buyUrl, shot: shot, cart: cart, add: add, remove: remove,
    clear: clear, init: init, setCatalog: setCatalog,
    openDrawer: openDrawer,
    closeDrawer: closeDrawer, renderDrawer: renderDrawer
  };
})();
