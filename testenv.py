"""The environment a test's child processes must get.

A test that starts a child process with the inherited environment also gives
it the runner's real credentials, and a scheduled runner has them: the model
provider key, the Discord bot token, the itch.io API key, the itch.io login.
That is how update_selftest.py came to create a real event in the production
Discord server. It called upsert() expecting it to refuse for want of a bot
token, and the token was there, so the test posted a real announcement
instead of checking that a missing token is refused safely.

The same shape lets a test spend real model tokens, push a real build to
itch.io, or write to the real account. A test must be able to do none of
those, so every child a test starts gets this environment: the same machine
and the same paths, without the credentials that would let it out.

This is a module rather than a helper copied into each test, because the
copies are what drift. The rule that a test may not start a child with the
ambient environment is checked by selftest_audit.py, which reads the source,
so a test that forgets this is caught before it runs rather than after.

    from testenv import clean_env
    subprocess.run([...], env=clean_env())

    python testenv.py
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# The names that are a key to something. They are matched by suffix, so a new
# provider that names its key FOO_API_KEY is covered without being listed.
_SECRET_SUFFIXES = (
    "_API_KEY",
    "_TOKEN",
    "_SECRET",
    "_PASSWORD",
    "_SESSION_COOKIE",
    "_COOKIE",
)

# Names that do not follow the pattern above but are still a way in.
_EXACT = (
    "DISCORD_BOT_TOKEN",
    "DISCORD_GUILD_ID",
    "DISCORD_WEBHOOK_URL",
    "ITCH_USER",
    "ITCH_LOGIN",
    "ITCH_PASSWORD",
    "ITCH_SESSION_COOKIE",
    "ITCH_API_KEY",
    "BUTLER_API_KEY",
    "ELEVENLABS_API_KEY",
    "YOUTUBE_API_KEY",
    "YOUTUBE_REFRESH_TOKEN",
    "TWITCH_ACCESS_TOKEN",
    "SLINGSHOT_BUDGET_HOURS",
)


def is_secret(name: str) -> bool:
    """Is this an environment variable that would let a test reach out?"""
    if name in _EXACT:
        return True
    return name.endswith(_SECRET_SUFFIXES)


def clean_env() -> dict:
    """A copy of the environment with the credentials taken out.

    The rest of the environment is kept, because the tests need PATH,
    SYSTEMROOT and HOME to run at all, and a test that behaves differently on
    a stripped machine is not testing what the pipeline does.
    """
    env = {k: v for k, v in os.environ.items() if not is_secret(k)}
    env.setdefault("PATH", "/usr/bin:/bin")
    env.setdefault("SYSTEMROOT", "C:\\Windows")
    env.setdefault("HOME", tempfile.gettempdir())
    return env


def main() -> int:
    """Print what a test's child would see, so the rule can be checked by eye."""
    env = clean_env()
    kept = sorted(k for k in env if k in os.environ)
    dropped = sorted(k for k in os.environ if k not in env)
    print(f"kept {len(kept)} variables, dropped {len(dropped)} secrets")
    if dropped:
        print("dropped: " + ", ".join(dropped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
