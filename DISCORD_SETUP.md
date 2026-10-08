# Discord announcements

When a new tool goes live, the pipeline posts it to a Discord channel as a rich
embed: title, description, free download link, full-edition price, and a link
back to the site.

The announcement only fires **after** the Windows installer publishes the paid
edition, so nothing is ever advertised before it is actually buyable. The step
is also `continue-on-error`, so Discord trouble can never block a publish.

## One-time setup

1. In Discord, create the server and a channel for releases, e.g. `#releases`.
2. Open the channel settings -> **Integrations** -> **Webhooks** -> **New Webhook**.
3. Copy the webhook URL. It looks like:
   `https://discord.com/api/webhooks/<id>/<token>`
4. Add it to the repository as a secret:
   `DISCORD_WEBHOOK_URL`

Add it as a **secret**, not a variable. Webhook tokens are credentials: anyone
holding the URL can post to the channel, and the URL is not safe to commit.

Secrets can be set with:

```
gh secret set DISCORD_WEBHOOK_URL --repo tbougnar/Slingshot-Tools
```

or under **Settings -> Secrets and variables -> Actions -> New repository secret**.

## Preview the message

Without posting anything:

```
python discord_announce.py --dry-run
```

This prints the exact JSON that would be sent.

## Behaviour

- Missing webhook: logs and exits 0, the pipeline carries on.
- Already announced: skipped, so a retried run cannot double-post.
- Paid tier not yet live: skipped, so nothing unsellable is promoted.
- `allowed_mentions.parse` is empty, so product text can never ping a role or
  a user, whatever the generator produced.
