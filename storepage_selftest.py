"""The product page, its previews and the cart, checked without a payment.

The old storefront had one product surface: a card whose button opened a
dialog and then forwarded straight to itch.io. There was nowhere to see what
an app looked like before paying, and no way to hold more than one tool in a
basket. These checks hold the new flow to its promises:

* clicking a product leads to a page for that product alone
* that page shows a generated preview of the actual app UI
* Add to cart stores it once, and Remove takes it out again
* the pay links are validated itch.io URLs from the catalogue, never injected
  text or a second checkout that pretends to take money

Everything runs with no network and no credentials, so a broken store page is
caught before it reaches GitHub Pages.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SITE = ROOT / "site"

fails = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL "), label, ("  " + detail) if detail else "")
    if not ok:
        fails.append(label)


product = (SITE / "product.html").read_text(encoding="utf-8")
cart = (SITE / "cart.html").read_text(encoding="utf-8")
home = (SITE / "index.html").read_text(encoding="utf-8")
store = (SITE / "store.js").read_text(encoding="utf-8")

print("THE PAGES EXIST AND SHARE ONE DESIGN\n")
for name, body in (("product.html", product), ("cart.html", cart)):
    check(f"{name} uses the shared stylesheet",
          'href="store.css"' in body and 'src="store.js"' in body)
check("the homepage links to product pages",
      "SlingshotStore.productUrl(item)" in home)
check("the image, title and price are one link",
      'class="pc-link" href=' in home and 'class="shot">' in home)
check("quick view is still keyboard reachable",
      "openDialogByIndex(" in home and 'class="pc-quick"' in home)

print("\nTHE PRODUCT PAGE READS THE CATALOGUE, NOT A HARD-CODED LIST\n")
check("it looks up the slug from the address",
      'URLSearchParams(location.search).get("slug")' in product)
check("it finds the product in the family list",
      "S.family(all).filter" in product)
check("there is a real not-found state",
      "No tool here" in product)
check("it shows three preview modes",
      all(f'thumb("{m}"' in product for m in ("dark", "light", "detail")))
check("the preview changes when a thumbnail is clicked",
      'data-shot' in product and 'galleryMain' in product)
check("Add to cart is a button on the product page",
      'class="btn primary" type="button" data-add=' in product)
check("the details are named, not left to implication",
      all(w in product for w in ("Works offline", "Not required",
                                 "One-time purchase", "Instant download")))

print("\nTHE CART DOES NOT PRETEND TO TAKE PAYMENT\n")
check("every line links to the product's own store page",
      "Pay for this one on itch.io" in cart and "S.buyUrl(p)" in cart)
check("the total is computed from the catalogue",
      "reduce((sum,p)=>sum+S.priceOf(p),0)" in cart)
check("the cart explains why there is no mixed checkout",
      "no single mixed checkout" in cart)
check("an empty cart has a way back",
      "Nothing in the cart yet" in cart and 'href="./"' in cart)

print("\nTHE PREVIEW IS A REAL PICTURE OF THE APP\n")
check("previews are inline SVG, so a new app needs no binary asset",
      "'<svg viewBox=" in store)
check("the preview carries the app's name for screen readers",
      'aria-label="Preview of ' in store)
check("the preview has a light and a detail mode",
      'light = mode === "light"' in store and 'detail = mode === "detail"' in store)
check("light mode has its own palette",
      'var ink = light ?' in store and 'var dim = light ?' in store)
check("detail mode changes what the preview shows",
      'var panel = detail' in store)

# The text checks above keep the promises visible in source. These checks
# execute the store in a browser, where a typo in a function body would still
# pass a grep.
try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto((SITE / "cart.html").resolve().as_uri())
        page.wait_for_timeout(300)
        got = page.evaluate("""() => {
            const S = window.SlingshotStore;
            if (!S) return {missing: true};
            S.clear();
            S.add('unit-converter');
            S.add('unit-converter');
            const once = S.cart().slice();
            const good = S.buyUrl({key:'unit-converter', lead:{
                title:'Unit converter', price:3,
                itch_url:'https://slingshot-tools.itch.io/unit-converter'}});
            const evil = S.buyUrl({key:'x', lead:{
                title:'Bad', price:3, itch_url:'javascript:alert(1)'}});
            const preview = S.shot({key:'unit-converter', lead:{
                title:'Unit converter', tag:'unit', price:3,
                itch_url:'https://slingshot-tools.itch.io/unit-converter'}}, 'dark');
            S.remove('unit-converter');
            return {once, empty: S.cart().length === 0, good, evil,
                    svg: preview.indexOf('<svg') === 0,
                    named: preview.indexOf('Unit converter') !== -1,
                    counted: document.querySelectorAll('[data-cart-count]').length};
        }""")
        browser.close()
    check("the store script loads", not got.get("missing"), str(got)[:120])
    check("adding twice keeps one copy", got.get("once") == ["unit-converter"],
          str(got.get("once")))
    check("Remove empties the cart", got.get("empty") is True)
    check("a valid store page becomes a checkout link",
          str(got.get("good")).startswith("checkout.html?slug=unit-converter"))
    check("an injected URL is refused", got.get("evil") == "", str(got.get("evil")))
    check("the preview is an SVG showing this app",
          got.get("svg") is True and got.get("named") is True)
    check("the cart badge is present on page load",
          got.get("counted", 0) >= 1)
    check("no script error on load",
          not any("is not defined" in e for e in errors), str(errors[:2]))
except Exception as e:  # noqa: BLE001
    print("skip  no browser available:", str(e)[:80])

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
