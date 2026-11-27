"""Read the real itch.io forms, so project creation can be automated.

itch.io has no API for creating a project, so the pipeline has to submit the
same form a person submits. Until now nobody had written down what that form
actually contains: every attempt guessed field names, and the guess that
mattered (a browser behind a Cloudflare challenge) never reached the form at
all.

This reads two pages with the stored session cookie and prints their fields:

  1. https://itch.io/settings/mine/new/game      - the create form
  2. <project>/edit                             - where price and publishing
                                                  are set afterwards

Only names, types and non-secret values are printed. Nothing here writes, so
it is safe to run as often as needed.

    python itch_probe.py
"""
from __future__ import annotations

import html as htmllib
import os
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

ROOT = __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0]

SECRET_BITS = ("password", "token", "secret", "csrf", "session", "cookie")


def log(msg: str) -> None:
    print(f"[probe] {msg}", flush=True)


def cookie() -> str:
    c = (os.environ.get("ITCH_SESSION_COOKIE") or "").strip()
    if not c:
        log("ITCH_SESSION_COOKIE is not set; nothing to read with")
    return c


class Fields(HTMLParser):
    """Every form control on a page, plus the form it belongs to."""

    def __init__(self) -> None:
        super().__init__()
        self.controls: list[dict] = []
        self.forms: list[dict] = []
        self._form: dict | None = None
        self._select: dict | None = None
        self._textarea: dict | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        if tag == "form":
            self._form = {"action": a.get("action", ""), "method": a.get("method", "get")}
            self.forms.append(self._form)
        elif tag == "input":
            self.controls.append({
                "kind": "input", "type": a.get("type", "text"),
                "name": a.get("name", ""), "id": a.get("id", ""),
                "value": a.get("value", ""),
            })
        elif tag == "select":
            self._select = {"kind": "select", "name": a.get("name", ""),
                            "id": a.get("id", ""), "options": []}
            self.controls.append(self._select)
        elif tag == "option" and self._select is not None:
            self._select.setdefault("_pending", []).append(
                {"value": a.get("value", ""), "label": ""})
        elif tag == "textarea":
            self._textarea = {"kind": "textarea", "name": a.get("name", ""),
                              "id": a.get("id", "")}
            self.controls.append(self._textarea)

    def handle_data(self, data: str) -> None:
        if self._select is not None and data.strip():
            pending = self._select.get("_pending") or []
            if pending:
                pending[-1]["label"] = (pending[-1].get("label", "") + data).strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._form = None
        elif tag == "select":
            if self._select is not None:
                self._select.pop("_pending", None)
            self._select = None
        elif tag == "textarea":
            self._textarea = None


def fetch(url: str, c: str) -> tuple[int, str, str]:
    req = urllib.request.Request(url, headers={
        "Cookie": f"itchio_token={c}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/154.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, r.geturl(), r.read(400000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, e.read(400000).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return 0, url, str(e)


def show(label: str, url: str, c: str) -> None:
    status, landed, body = fetch(url, c)
    log(f"--- {label}")
    log(f"    GET {url} -> {status} landed on {landed}")
    if "just a moment" in body.lower() or "cf-turnstile" in body.lower():
        log("    CLOUDFLARE CHALLENGE served instead of the page")
        return
    if "/login" in landed:
        log("    the session was refused (redirected to login)")
        return
    title = re.search(r"<title>(.*?)</title>", body, re.S | re.I)
    log(f"    title: {htmllib.unescape(title.group(1)).strip() if title else '(none)'}")

    p = Fields()
    p.feed(body)
    for f in p.forms:
        log(f"    FORM action={f['action']!r} method={f['method']!r}")
    for ctl in p.controls:
        name = ctl.get("name") or ""
        if not name and not ctl.get("options"):
            continue
        secret = any(b in (name + ctl.get("id", "")).lower() for b in SECRET_BITS)
        if ctl["kind"] == "select":
            opts = ctl.get("options") or []
            shown = ", ".join(f"{o['value']}={o['label']}" for o in opts[:8])
            log(f"      select name={name!r} options: {shown}")
        elif ctl["kind"] == "textarea":
            log(f"      textarea name={name!r}")
        else:
            val = "" if secret else str(ctl.get("value") or "")[:60]
            log(f"      {ctl['type']:10s} name={name!r} id={ctl.get('id','')!r} "
                f"value={val!r}")

    # the actions a person would click, which is what publishing needs
    for m in sorted(set(re.findall(r"<(?:button|input)[^>]*>"
                                   r"(?:value=\"([^\"]*)\")?[^>]*>", body))):
        pass
    texts = re.findall(r">([^<>]{2,40})<", body)
    hits = [t.strip() for t in texts
            if re.search(r"publish|save|view page|draft|price|minimum", t, re.I)]
    log("    visible actions: " + ", ".join(sorted(set(hits))[:14]))


def main() -> int:
    c = cookie()
    if not c:
        return 1
    show("create form", "https://itch.io/settings/mine/new/game", c)
    show("projects list", "https://itch.io/settings/mine", c)
    for slug in ("unit-converter",):
        show(f"{slug} edit page",
             f"https://slingshot-tools.itch.io/{slug}/edit", c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
