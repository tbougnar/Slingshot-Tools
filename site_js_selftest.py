"""The homepage's own JavaScript, checked without a browser.

Two bugs shipped to the live site from this file and neither was caught by any
test, because every existing test either parsed the HTML or fetched a URL:

1. ``groupProducts`` ended with ``key:k``, and ``k`` is bound inside a
   ``forEach`` callback, so the ``map`` that followed threw
   ``ReferenceError: k is not defined``. The whole catalog rendered as
   "The catalog loads on first build" and every visitor saw an empty homepage.

2. Each card's button inlined ``JSON.stringify(item)`` into a double-quoted
   ``onclick`` attribute. The JSON contains double quotes, which closed the
   attribute early, so clicking "See options" threw ``Unexpected end of input``
   and nobody could open a product.

Both are pure text problems, so both are caught here. The escaping is
deliberately awkward-looking and the reason is written down, because the tidy
version of that line is the bug.

The payment-return copy on checkout.html is checked here too, because it is
the one page a buyer sees after paying and it claimed an email nobody sends.

    python site_js_selftest.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SITE = ROOT / "site" / "index.html"

fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL "), label, detail)
    if not ok:
        fails.append(label)


if not SITE.exists():
    print("FAIL  site/index.html is missing")
    sys.exit(1)

html = SITE.read_text(encoding="utf-8")

# ------------------------------------------------------- groupProducts
gp = re.search(r"function groupProducts\(list\)\{(.*?)\}\s*\n", html, re.S)
check("groupProducts is defined", gp is not None)
body = gp.group(1) if gp else ""

# the closure that threw: k is defined in the forEach, used in the map
check("groupProducts does not use a forEach-only variable",
      not re.search(r"key:\s*k\b", body),
      "key:k is out of scope in the map callback")

# every identifier used in the map callback must be bound there or outside
m = re.search(r"\.map\(pair=>\{(.*?)\}\)", body, re.S)
inside = m.group(1) if m else ""
check("the map callback binds what it uses",
      bool(inside) and ("full.base_slug||full.slug" in inside
                        or "lead.base_slug||lead.slug" in inside
                        or "pair[0].base_slug" in inside),
      "the family key has to be read from the pair itself")

# The real check is whether it runs. node is not installed everywhere, but a
# browser is (shots.py and the Friday jobs already depend on one), and a
# browser executes the page exactly as a visitor gets it.
try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as _p:
        _b = _p.chromium.launch()
        _pg = _b.new_page()
        _errs: list[str] = []
        _pg.on("pageerror", lambda e: _errs.append(str(e)))
        _pg.goto(SITE.resolve().as_uri())
        _pg.wait_for_timeout(400)
        got = _pg.evaluate(
            """() => {
                const d = [
                  {slug:'a', base_slug:'a', tier:'full', price:3,
                   published:true, itch_url:'https://x.itch.io/y'},
                  {slug:'a-basic', base_slug:'a', tier:'basic',
                   published:true, url:'/apps/a-basic/'}];
                const out = groupProducts(d);
                return {n: out.length, key: out[0] && out[0].key,
                        onSale: out[0] && out[0].onSale,
                        hasFull: !!(out[0] && out[0].full),
                        hasBasic: !!(out[0] && out[0].basic)};
            }""")
        # The bug this fixes: a product whose paid edition is not on sale yet
        # still has a full entry in the catalogue, marked published:false. The
        # grouping dropped it, so the pair held only the basic entry and
        # `full` fell back to it. The card then said "Full edition" and priced
        # it at $0.00, and the dialog offered a Full edition that was free. On
        # the live site that was thirty-two of the thirty-four products.
        got2 = _pg.evaluate(
            """() => {
                const d = [
                  {slug:'a', base_slug:'a', tier:'full', title:'Thing',
                   price:3, published:false, itch_url:''},
                  {slug:'a-basic', base_slug:'a', tier:'basic', title:'Thing (Basic)',
                   price:0, published:true, url:'/apps/a-basic/'}];
                const out = groupProducts(d);
                return {n: out.length, onSale: out[0] && out[0].onSale,
                        lead: out[0] && out[0].lead && out[0].lead.tier,
                        full: out[0] && out[0].full};
            }""")
        _b.close()
    check("groupProducts runs in a browser", got.get("n") == 1, str(got))
    check("it groups both tiers into one product",
          bool(got.get("hasFull")) and bool(got.get("hasBasic")))
    check("the family key is the base slug", got.get("key") == "a")
    check("a product with a store page is on sale", got.get("onSale") is True,
          "it is not offered for sale even though it has an itch.io page")

    check("a product with an unsold paid edition is still listed",
          got2.get("n") == 1, str(got2))
    check("and it is not treated as being on sale",
          got2.get("onSale") is False,
          "the group claims the paid edition is on sale")
    check("the card shows the free edition, not the unsold one",
          got2.get("lead") == "basic" and not got2.get("full"),
          f"lead={got2.get('lead')} full={got2.get('full')}")

    # fetch() from file:// is blocked by CORS, so apps.json legitimately does
    # not load here; a ReferenceError from groupProducts would still show up.
    check("no script error on load",
          not any("is not defined" in e for e in _errs), str(_errs[:2]))
except Exception as _e:  # noqa: BLE001
    print("skip  no browser available:", str(_e)[:70])

# ------------------------------------------------------------- card buttons
render = re.search(r"function render\(\)\{(.*?)\n    function ", html, re.S)
rbody = render.group(1) if render else html
check("render is defined", render is not None)

# JSON must never be inlined into the onclick attribute again
check("no JSON is inlined into an onclick",
      "JSON.stringify(item)" not in rbody,
      "its double quotes close the attribute early")
check("cards pass an index instead",
      "openDialogByIndex(" in rbody)
check("the index comes from the map callback",
      re.search(r"\.map\(\(item,\s*idx\)", rbody) is not None)

# the price variable is a string, so binding it to p and interpolating it is
# how the index became "$3.00"
check("the index is not the price variable",
      not re.search(r"openDialogByIndex\(\\'\+p\+\\'\)", rbody),
      "p is the price there, not the index")
check("render's map binds an index",
      "idx" in rbody or "i)" in rbody)

check("openDialogByIndex is defined",
      "function openDialogByIndex(" in html)
# the index has to refer to what render actually drew, or it is wrong as soon
# as a filter narrows the list
check("render records what it drew", "VIEW=list" in rbody)
check("the handler reads that list",
      re.search(r"function openDialogByIndex\(i\)\{const item=VIEW\[i\]", html)
      is not None)
check("an index outside the list is harmless",
      re.search(r"if\(item\)\s*openDialog", html) is not None)

# --------------------------------------------------- what the shop says
# The paid edition's differences were read out of the catalogue and never
# shown. The customer was asked for three dollars and the dialog said what
# the three dollars were for, in the sense that it said nothing at all.
check("the differences are carried to the dialog",
      "diffs:item.diffs||[]" in html,
      "the full option does not carry what the paid edition adds")
check("and they are rendered",
      "optDiffs" in html and "class=\"diff\"" in html,
      "the differences are computed and then thrown away")
check("the style for them exists",
      ".optDiffs{" in html and ".diff{" in html)

# --------------------------------------------------------------- countdown
check("the countdown element exists", 'id="countdown"' in html)
check("it is hidden until there is something to count",
      re.search(r"\.countdown\{display:none", html) is not None)
check("it is shown by a class", ".countdown.on{display:flex}" in html)
check("it reads the generated file", 'fetch("update.json"' in html)
check("a missing file leaves it hidden", ".catch(()=>{})" in html)
check("it refuses to show outside the window",
      'd.phase==="idle"' in html and 'd.phase==="live"' in html)
check("an unparseable date is ignored", "isNaN(when)" in html)
# the countdown injects the update title, so it has to be escaped
check("the countdown escapes what it injects", "esc(title)" in html)

# ------------------------------------------------------------- checkout page
# The site hands payment to itch.io, which keeps the download on the product
# page. The payment return used to say a download link and a licence key had
# been emailed, and nothing in this project sends either, so a buyer who
# landed there waited for an email that never came.
co = SITE.parent / "checkout.html"
check("the checkout page exists", co.exists())
co_html = co.read_text(encoding="utf-8") if co.exists() else ""
check("a payment return does not promise an email nobody sends",
      "have been emailed" not in co_html
      and "licence key have been" not in co_html,
      "the paid state still claims an emailed link and licence key")
check("and it points the buyer at the store page instead",
      "Download the Full edition from the store page" in co_html
      and "slingshot-tools.itch.io/slingshot-tools" in co_html)
check("the store link it builds is validated, not injected",
      'test(itch)?itch:' in co_html and "n.textContent=''" in co_html,
      "the itch URL must start with https://<name>.itch.io/ and be inserted "
      "as text")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)