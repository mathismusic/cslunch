# 🚂 Lunch Train

A zero-friction daily lunch ritual for UIUC CS grad students, run entirely
inside Slack on the free plan. Every weekday:

- **11:00am** — the bot posts today's restaurant (rotating through
  [`restaurants.json`](restaurants.json)), a fixed meeting time and spot, and
  the noon weather. Joining lunch = reacting with one emoji.
- **11:45am** — the bot counts reactions. **3+ people** → it announces
  "It's on!" with everyone tagged. 1–2 people → a quiet thread reply.
  Zero → it says nothing (no visible-failure days).

No servers, no database, no cost: GitHub Actions is the scheduler, the repo is
the config. Changing the restaurant list is a pull request anyone can send.

## One-time setup (~5 minutes)

1. **Create the Slack app.** Go to <https://api.slack.com/apps> → *Create New
   App* → *From a manifest* → pick your workspace → paste the contents of
   [`manifest.yml`](manifest.yml). Then *Install to Workspace* and copy the
   **Bot User OAuth Token** (starts with `xoxb-`).
2. **Invite the bot** to your lunch channel: `/invite @lunch-train`.
3. **Set the channel ID** in [`config.json`](config.json): channel details →
   scroll to the bottom of the *About* tab for the ID (starts with `C`).
4. **Push this repo to GitHub**, then in the repo settings → *Secrets and
   variables* → *Actions*, add a secret named `SLACK_BOT_TOKEN` with the
   token from step 1.

That's it — the schedules in `.github/workflows/` take over. Trigger either
workflow manually from the Actions tab (workflow_dispatch) to test end-to-end.

> **Note:** for a *private* channel, add the `groups:history` bot scope in the
> app's OAuth settings and reinstall.

## Testing locally

```sh
DRY_RUN=1 FORCE=1 python3 scripts/bot.py post     # prints the message, no token needed
FORCE=1 SLACK_BOT_TOKEN=xoxb-... python3 scripts/bot.py post   # really posts
FORCE=1 SLACK_BOT_TOKEN=xoxb-... python3 scripts/bot.py tally  # really tallies
```

`FORCE=1` bypasses the "only at 11am on a non-skipped weekday" guard, which
otherwise makes the script exit silently outside its window.

## Customizing

- **Restaurants** — edit `restaurants.json`. `"close": true` marks spots near
  Siebel; on rainy (≥50%) or bitter (feels-like ≤15°F) days the bot only picks
  from those. The pick rotates deterministically by date, so no state is kept.
- **Meeting time/spot, quorum, weather thresholds** — `config.json`.
- **Breaks and holidays** — `skip_dates.txt` (update each semester).
- **Schedule** — the crons in `.github/workflows/` fire at two UTC hours
  because GitHub cron ignores DST; the script keeps whichever run is 11am
  Chicago time. Heads-up: GitHub cron can drift 5–15 minutes at busy times.

## Ideas for later

- A `/lunch` slash command for ad-hoc rounds (needs a small always-on endpoint,
  e.g. a free Cloudflare Worker — the current design is deliberately serverless).
- Poll mode: post 3 restaurants as emoji options, winner announced at tally time.
- Semester kickoff message asking people to PR their favorite spots.
