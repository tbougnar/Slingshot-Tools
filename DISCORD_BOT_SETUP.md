# Discord bot and server setup

Two parts, and only the first one is optional:

| Part | Needs | What it does |
|---|---|---|
| **Webhook** | a webhook URL | Posts announcements, articles and ballots with nothing running |
| **Bot** | a bot token + `discord.py` | Adds `/tools`, `/article`, `/vote` with vote buttons |

Start with the webhook. It gets announcements working immediately. Add the bot
later for interactive voting.

---

## 1. Create the server

Create the server in Discord, then let the script in step 2 build the channels
for you. You do not need to create any channel by hand.

The one thing you must do: turn on **Settings -> Advanced -> Developer Mode**,
or "Copy Server ID" will not be available.

---

## 2. Build the channel structure automatically

You do not have to create 15 channels by hand. The script builds the whole
layout in `DISCORD_SERVER.md`, sets the permissions, and registers the slash
commands.

Preview it first, which changes nothing:

```bash
python discord_setup_server.py --dry-run
```

Then apply it:

```bash
DISCORD_BOT_TOKEN=<your bot token> DISCORD_GUILD_ID=<your server id> \
  python discord_setup_server.py
```

It is idempotent, so running it again repairs permissions or picks up new
channels instead of creating duplicates.

The bot needs **Manage Channels** and **Use Application Commands**. On the Bot
page, either tick those in the permissions link, or give the bot's role
Administrator and then narrow it afterwards.

To let moderators post in the bot channels, create a role called `Moderator`
and pass `DISCORD_MOD_ROLE_ID`.

---

## 3. Webhook (announcements, no bot needed)

1. Right-click `#announcements` -> **Edit Channel** -> **Integrations** ->
   **Webhooks** -> **New Webhook**. Name it `Slingshot Tools`.
2. Copy the URL.
3. Add it as a repository **secret** named `DISCORD_WEBHOOK_URL`.

Repeat for `#polls` and `#results` if you want them separate, using
`DISCORD_POLL_WEBHOOK_URL` and `DISCORD_RESULTS_WEBHOOK_URL`. Without those,
they fall back to `DISCORD_WEBHOOK_URL`.

```bash
gh secret set DISCORD_WEBHOOK_URL --repo tbougnar/Slingshot-Tools
```

Use **secrets**, never variables. The webhook token is a credential: anyone
holding the URL can post to the channel.

Preview before sending anything:

```bash
python discord_announce.py --dry-run
```

---

## 4. Bot (interactive voting)

### Create the application

1. Go to <https://discord.com/developers/applications> -> **New Application**.
2. Name it `Slingshot Tools`.
3. Open **Bot** in the sidebar -> **Reset Token**. Copy it once.

### Enable the intents it needs

On the **Bot** page, under **Privileged Gateway Intents**, leave
**MESSAGE CONTENT INTENT** switched **off**. The bot never reads messages, so
it does not need that permission, and leaving it off keeps the bot compliant
with Discord's policy.

### Invite it to your server

**OAuth2 -> URL Generator**:

| Setting | Value |
|---|---|
| Scopes | `bot`, `applications.commands` |
| Bot permissions | `Send Messages`, `Embed Links`, `Use Application Commands`, `Manage Channels`, `Manage Roles` |

Manage Channels is what lets the setup script build the layout. Copy the URL,
open it, and pick your server.

Copy the **Server ID** (right-click the server name with Developer Mode on)
and the **bot token**, then run the setup script from step 2.

### Add the secrets

| Secret | Value |
|---|---|
| `DISCORD_BOT_TOKEN` | the bot token you just copied |
| `DISCORD_GUILD_ID` | right-click your server name -> **Copy Server ID** |
| `DISCORD_ANNOUNCEMENTS_CHANNEL_ID` | right-click `#announcements` -> **Copy Channel ID** |

> Turn on **Settings -> Advanced -> Developer Mode** in Discord first, or
> "Copy ID" will not appear.

### Run it

The bot must be running to answer slash commands, unlike the webhook.

```bash
pip install "discord.py>=2.3"
DISCORD_BOT_TOKEN=... DISCORD_GUILD_ID=... python discord_bot.py
```

For a server that never sleeps, run it as a service (a VPS, a systemd unit, or
Docker). GitHub Actions cannot host it: runners are torn down when the job ends.

### Keep the ballots moving

Voting is stateful, and the state must live somewhere that survives, so the
**bot host owns the poll lifecycle** rather than CI:

```bash
DISCORD_BOT_TOKEN=... python discord_polls.py
```

This closes any ballot older than 21 days, posts the result, and opens a fresh
one. Run it daily with cron or a systemd timer:

```cron
17 9 * * * cd /srv/slingshot && DISCORD_BOT_TOKEN=... /usr/bin/python3 discord_polls.py >> /var/log/slingshot-polls.log 2>&1
```

Once running, the commands appear in Discord:

- `/tools` — every live tool with prices and links
- `/article password-manager` — the write-up
- `/vote` — the open ballot as buttons
- `/vote results` — closed-poll history
- `/ping` — liveness

---

## 5. What the pipeline does on its own

After each monthly build, automatically:

1. `discord_article.py` writes the article for the new tool.
2. `discord_announce.py` posts it to `#announcements`.
3. The bot host's daily `discord_polls.py` closes any aged ballot, posts the
   result to `#results`, and opens a fresh ballot in `#polls`.
4. `make_app.py` reads the last ballot winner and builds **that** tool next.

Both Discord steps in CI are `continue-on-error`, so an outage or a missing
webhook can never block a release.

Nothing is announced unless the paid tier is genuinely on sale, and no vote is
ever counted twice.

### State files

| File | Committed? | Purpose |
|---|---|---|
| `discord_articles.json` | yes | the article per tool, public marketing copy |
| `data/polls.json` | **no** | ballots, options and voters |
| `data/discord_sent.json` | **no** | what has already been announced |

`data/` is gitignored on purpose. Polls hold Discord user ids, so they must
never land in a public repository, and they are only meaningful on the host
that runs the bot. If you move the bot to another machine, copy `polls.json`
across or the open ballot will be forgotten.

---

## Troubleshooting

**`/vote` shows nothing** - the bot is offline, or the ballot is closed. Run
`python discord_polls.py` to check the state.

**Commands do not appear** - global command sync can take an hour. With
`DISCORD_GUILD_ID` set, sync is per-server and takes seconds. Restart the bot
to force it.

**Announcements stopped** - check the installer job log for
`[discord] discord rejected the message`. A `429` means rate limited; a `401`
means the webhook URL changed.

**Poll says "tie"** - deliberate. A tied ballot is not a mandate, so the
winner is ignored and the next build proceeds without it.
