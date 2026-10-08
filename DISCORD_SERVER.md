# Slingshot Tools Discord server structure

Design goals: the AI pipeline runs the server on its own, members can see what
ships, understand what it does, buy it, and decide what gets built next.

## Categories and channels

### 1. START HERE
| Channel | Type | Purpose |
|---|---|---|
| `#welcome` | text | Rules, what this server is, how the monthly build works. Read-only to members. |
| `#rules` | text | Short rule list. Read-only. |
| `#announcements` | text | **Bot only.** Every new tool is posted here automatically. |
| `#roadmap` | text | What is being built, what is next, what shipped. |

### 2. TOOLS
| Channel | Type | Purpose |
|---|---|---|
| `#tools` | text | **Bot only.** The full catalog. `/tools` lists everything live with prices. |
| `#articles` | text | **Bot only.** A longer write-up per tool: what problem it solves, how it works. |
| `#downloads` | text | Download links for the free edition, plus the buy link for the full edition. |
| `#showcase` | text | Members post screenshots, tips, and workflows. Human conversation. |
| `#support` | text | Bugs, questions, feature requests. |

### 3. VOTING
| Channel | Type | Purpose |
|---|---|---|
| `#polls` | text | **Bot only.** The AI opens a poll here for the next product. Members vote with a button. |
| `#ideas` | text | Members suggest tools that are not on the ballot yet. |
| `#results` | text | **Bot only.** The AI posts the outcome of each closed poll. |

### 4. ABOUT
| Channel | Type | Purpose |
|---|---|---|
| `#how-it-works` | text | The generate, verify, publish pipeline explained. |
| `#changelog` | text | Every commit and pipeline change worth knowing about. |
| `#links` | text | Website, GitHub repo, support contact. |

## Who can do what

**Members**
- Read `#announcements`, `#tools`, `#articles`, `#downloads`, `#roadmap`
- Vote in `#polls`
- Post in `#showcase`, `#support`, `#ideas`

**The bot** (role `Slingshot Bot`)
- Posts in `#announcements`, `#articles`, `#downloads`, `#polls`, `#results`, `#tools`
- Cannot be silenced by members, since members cannot post in those channels

**Moderators** (you)
- Pin the current poll, delete spam, mute, and kick

## Bot commands

| Command | What it does |
|---|---|
| `/tools` | Every live tool, with the free link and the full-edition price |
| `/article slug` | The write-up for one tool |
| `/vote` | The open ballot as buttons, with live vote counts |
| `/vote results` | The closed poll history and what each one decided |
| `/ping` | Confirms the bot is alive |

## How the AI controls it

The bot is driven by the same pipeline that builds the tools. Nothing is posted
by hand, and nothing is posted before it is real.

1. **Monthly build** finishes and the paid installer is uploaded.
2. The pipeline posts to `#announcements`, `#articles` and `#downloads`.
3. The pipeline opens a **new ballot** in `#polls` with the next candidates.
4. Members vote with buttons. Votes are stored in `data/polls.json`.
5. A scheduled run closes the poll, posts the outcome to `#results`, and the
   winning category is fed back into `make_app.py` so the next build actually
   matches what people asked for.

Announcements are refused unless the paid tier is genuinely on sale, so nothing
unsellable is ever promoted.

## Why a bot token *and* a webhook

- **Bot token** powers the interactive parts: `/vote` buttons, `/tools`,
  `/article`. It needs an always-on process.
- **Webhook** posts announcements with no process running and no downtime, so a
  new tool is never silently missed because the bot was asleep.

Both are supported. See `DISCORD_BOT_SETUP.md`.
