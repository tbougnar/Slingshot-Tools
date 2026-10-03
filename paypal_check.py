import os, json, urllib.request, urllib.parse, base64

cid = os.environ["PAYPAL_CLIENT_ID"]
sec = os.environ["PAYPAL_SECRET"]
url = "https://api-m.paypal.com/v1/oauth2/token?grant_type=client_credentials"

req = urllib.request.Request(url, method="POST")
req.add_header("Accept", "application/json")
req.add_header("Accept-Language", "en_US")
cred = base64.b64encode(f"{cid}:{sec}".encode()).decode()
req.add_header("Authorization", f"Basic {cred}")
req.add_header("Content-Type", "application/x-www-form-urlencoded")

try:
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    print("AUTH OK")
    print("token_type:", data.get("token_type"))
    print("expires_in:", data.get("expires_in"))
    tok = data["access_token"]

    r2 = urllib.request.Request("https://api-m.paypal.com/v1/identity/oauth2/userinfo?schema=paypalv1.1")
    r2.add_header("Authorization", f"Bearer {tok}")
    r2.add_header("Accept", "application/json")
    with urllib.request.urlopen(r2, timeout=60) as r:
        me = json.loads(r.read().decode())
    print("account:", me.get("name"), "|", me.get("payer_id") or me.get("user_id"))
    print("country:", me.get("country_code"), "| email:", me.get("email"))
    print("business:", me.get("business_name"))
except urllib.error.HTTPError as e:
    print("FAILED", e.code, e.read().decode()[:400])