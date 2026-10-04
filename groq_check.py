"""Report why Groq may be refusing calls, without leaking the key."""
from __future__ import annotations

import os


def main() -> int:
    k = os.environ.get("GROQ_API_KEY", "")
    print("key present:", bool(k), "length:", len(k),
          "prefix:", (k[:8] + "...") if k else "none")
    if not k:
        return 1
    import ai
    print("transport: requests (browser headers)")
    try:
        ids = ai.models()
        print("models endpoint: HTTP 200,", len(ids), "available")
        for i in ids:
            print("   -", i)
    except Exception as e:  # noqa: BLE001
        print("models endpoint FAILED:", str(e)[:300])
        return 1
    for m in ("openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"):
        if m not in ids:
            print(f"chat {m}: not offered")
            continue
        try:
            out = ai.chat(m, "be brief", "say ok", temperature=0.0, max_tokens=8)
            print(f"chat {m}: HTTP 200 -> {out.strip()[:40]!r}")
        except Exception as e:  # noqa: BLE001
            print(f"chat {m} FAILED: {str(e)[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
