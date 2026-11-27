"""Read the real itch.io forms, and try to log in without a browser.

itch.io has no API for creating a project, so the pipeline has to submit the
same form a person submits. Two things had never been written down:

  1. what those forms actually contain (field names, hidden tokens, pricing)
  2. whether a plain HTTP login works, or whether the Cloudflare challenge
     only ever appears in a browser

Nothing here writes. It prints field names and non-secret values only.

    python itch_probe.py
"""
from __future__ import annotations

import html as htmllib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

SECRET_BITS = ("password", "token", "secret", "csrf", "session", "cookie")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")


def log(msg: str) -> None:
    print(f"[probe] {msg}", flush=True)


def env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


class Fields(HTMLParser):
    """Every form control on a page, plus the forms themselves."""

    def __init__(self) -> None:
        super().__init__()
        self.controls: list[dict] = []
        self.forms: list[dict] = []
        self._form: dict | None = None
        self._select: dict | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        if tag == "form":
            self._form = {"action": a.get("action", ""),
                          "method": a.get("method", "get"), "fields": []}
            self.forms.append(self._form)
        elif tag == "input":
            ctl = {"kind": "input", "type": a.get("type", "text"),
                   "name": a.get("name", ""), "id": a.get("id", ""),
                   "value": a.get("value", "")}
            self.controls.append(ctl)
            if self._form is not None:
                self._form["fields"].append(ctl)
        elif tag == "select":
            self._select = {"kind": "select", "name": a.get("name", ""),
                            "id": a.get("id", ""), "options": []}
            self.controls.append(self._select)
            if self._form is not None:
                self._form["fields"].append(self._select)
        elif tag == "option" and self._select is not None:
            self._select.setdefault("_pending", []).append(
                {"value": a.get("value", ""), "label": ""})
        elif tag == "textarea":
            ctl = {"kind": "textarea", "name": a.get("name", ""),
                   "id": a.get("id", "")}
            self.controls.append(ctl)
            if self._form is not None:
                self._form["fields"].append(ctl)

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


def request(url: str, cookie: str = "", data: dict | None = None,
            extra: dict | None = None):
    """``cookie`` is the whole Cookie header, e.g. ``itchio_token=abc``."""
    body = None
    headers = {"User-Agent": UA,
               "Accept": "text/html,application/xhtml+xml"}
    if cookie:
        headers["Cookie"] = cookie
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Referer"] = url
    if extra:
        headers.update(extra)
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, r.geturl(), dict(r.headers), \
                r.read(400000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, dict(e.headers), \
            e.read(400000).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return 0, url, {}, str(e)


def show_fields(label: str, status: int, landed: str, body: str) -> None:
    log(f"--- {label}: HTTP {status} landed on {landed}")
    if "just a moment" in body.lower() or "cf-turnstile" in body.lower():
        log("    CLOUDFLARE CHALLENGE present in the page")
    title = re.search(r"<title>(.*?)</title>", body, re.S | re.I)
    log(f"    title: {htmllib.unescape(title.group(1)).strip() if title else '(none)'}")
    p = Fields()
    p.feed(body)
    for f in p.forms:
        log(f"    FORM action={f['action']!r} method={f['method']!r}")
        for ctl in f["fields"]:
            name = str(ctl.get("name") or "")
            secret = any(b in (name + str(ctl.get("id") or "")).lower()
                         for b in SECRET_BITS)
            if ctl["kind"] == "select":
                opts = ctl.get("options") or []
                log("      select " + repr(name) + ": "
                    + ", ".join(f"{o['value']}={o['label']}" for o in opts[:8]))
            elif ctl["kind"] == "textarea":
                log(f"      textarea {name!r}")
            else:
                val = "" if secret else str(ctl.get("value") or "")[:70]
                log(f"      {ctl['type']:10s} {name!r} value={val!r}")
    texts = re.findall(r">([^<>]{2,40})<", body)
    hits = [t.strip() for t in texts
            if re.search(r"publish|save|view page|draft|price|minimum|log in|sign in",
                         t, re.I)]
    log("    visible actions: " + ", ".join(sorted(set(hits))[:14]))


def cookies_from(headers: dict) -> dict:
    raw = headers.get("Set-Cookie") or headers.get("set-cookie") or ""
    out = {}
    for part in re.split(r",(?=[^;]+=)", raw):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.split(";", 1)[0].strip()
    return out


def try_login() -> str:
    """Log in over plain HTTP and return the session cookie, or ''."""
    user, pw = env("ITCH_LOGIN"), env("ITCH_PASSWORD")
    if not user or not pw:
        log("ITCH_LOGIN / ITCH_PASSWORD not set; cannot try a login")
        return ""
    status, landed, headers, body = request("https://itch.io/login")
    log(f"--- login page: HTTP {status} landed on {landed}")
    if "just a moment" in body.lower() or "cf-turnstile" in body.lower():
        log("    the login page itself carries a Cloudflare challenge")
    p = Fields()
    p.feed(body)
    form = next((f for f in p.forms
                 if "login" in (f["action"] or "").lower()), None)
    if form is None and p.forms:
        form = p.forms[0]
    if form is None:
        log("    no form found on the login page")
        return ""
    fields = {}
    for ctl in form["fields"]:
        name = str(ctl.get("name") or "")
        if not name or ctl["kind"] == "select":
            continue
        if ctl.get("type") in ("submit", "button", "file"):
            continue
        fields[name] = str(ctl.get("value") or "")
    log("    form fields: " + ", ".join(sorted(fields)))
    # fill the two boxes by shape, exactly like a person would
    pw_names = [n for n in fields if "pass" in n.lower()]
    user_names = [n for n in fields
                  if n not in pw_names
                  and any(k in n.lower() for k in ("user", "login", "email"))]
    if not pw_names:
        log("    no password field found")
        return ""
    if not user_names:
        user_names = [n for n in fields if n not in pw_names][:1]
    fields[pw_names[0]] = pw
    fields[user_names[0]] = user
    turnstile = [n for n in fields if "turnstile" in n.lower()]
    if turnstile:
        log(f"    the form needs a Turnstile answer ({turnstile[0]}) that "
            "cannot be produced here")
        return ""
    action = form["action"] or "https://itch.io/login"
    if action.startswith("/"):
        action = "https://itch.io" + action
    status, landed, headers, body = request(action, data=fields)
    got = cookies_from(headers)
    token = got.get("itchio_token", "")
    log(f"--- login POST -> HTTP {status} landed on {landed}")
    log(f"    cookies returned: {', '.join(sorted(got)) or '(none)'}")
    if "just a moment" in body.lower() or "cf-turnstile" in body.lower():
        log("    CHALLENGE served in answer to the login")
    err = re.search(r"(class=\"[^\"]*(error|warning)[^\"]*\"[^>]*>)\s*"
                    r"([^<]{5,120})", body, re.I)
    if err:
        log(f"    page says: {err.group(3).strip()}")
    if token:
        log("    got a fresh itchio_token session")
    return f"itchio_token={token}" if token else ""


def api_login() -> str:
    """Log in the way the itch.io desktop app does, and test the cookie.

    The web form at itch.io/login sits behind a Cloudflare challenge, so a
    plain client never sees it. api.itch.io is the API host the desktop app
    talks to, and it answers with a session cookie plus an API key. Whether
    that cookie is the same one the web forms accept is exactly what this
    checks rather than assumes.
    """
    user, pw = env("ITCH_LOGIN"), env("ITCH_PASSWORD")
    if not user or not pw:
        log("ITCH_LOGIN / ITCH_PASSWORD not set; cannot try api.itch.io/login")
        return ""
    status, landed, _, body = request(
        "https://api.itch.io/login",
        data={"username": user, "password": pw, "source": "desktop"})
    log(f"--- api.itch.io/login -> HTTP {status} landed on {landed}")
    try:
        d = json.loads(body)
    except (ValueError, TypeError):
        log(f"    not JSON: {body[:160]}")
        return ""
    if d.get("totp_needed"):
        log("    this account needs a TOTP code for API login, so an "
            "unattended run cannot mint a session this way")
        return ""
    if not d.get("success"):
        # The body can carry a one-time login token, which must never reach a
        # log, so its value is blanked before anything is printed.
        safe = re.sub(r'("(?:token|cookie|key)"\s*:\s*")[^"]*(")',
                      r"\1***\2", body)
        log(f"    refused: {safe[:300]}")
        return ""
    log(f"    success; keys returned: {', '.join(sorted(d))}")
    cookies = d.get("cookie") or {}
    log(f"    cookie names: {', '.join(sorted(cookies)) or '(none)'}")
    key = ((d.get("key") or {}).get("key") or "")
    log(f"    api key returned: {'yes, ' + str(len(key)) + ' chars' if key else 'no'}")
    for name, value in cookies.items():
        header = f"{name}={value}"
        status, landed, _, body = request(
            "https://itch.io/settings/mine/new/game", cookie=header)
        ok = status == 200 and "/login" not in landed \
            and "cf-turnstile" not in body.lower() \
            and re.search(r"<form", body, re.I) is not None
        log(f"    cookie {name!r} on the create form: "
            f"HTTP {status} {'WORKS' if ok else 'does not work'}")
        if ok:
            return header
    return ""


def main() -> int:
    cookie = env("ITCH_SESSION_COOKIE")
    log(f"stored session cookie: {'present' if cookie else 'absent'}")
    if cookie:
        status, landed, _, body = request(
            "https://itch.io/settings/mine/new/game",
            cookie=f"itchio_token={cookie}")
        if status == 200 and "/login" not in landed and "search" not in body[:4000]:
            log("the stored session still works")
            cookie = f"itchio_token={cookie}"
        else:
            log(f"the stored session is dead (HTTP {status} on {landed}); "
                "trying to log in fresh")
            cookie = ""
    if not cookie:
        cookie = api_login()
    if not cookie:
        cookie = try_login()
    if not cookie:
        log("no session, so the forms cannot be read")
        return 1

    for label, url in (
        ("create form", "https://itch.io/settings/mine/new/game"),
        ("projects list", "https://itch.io/settings/mine"),
        ("unit-converter edit", "https://slingshot-tools.itch.io/unit-converter/edit"),
    ):
        status, landed, _, body = request(url, cookie=cookie)
        show_fields(label, status, landed, body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
