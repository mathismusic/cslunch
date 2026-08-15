# 🚂 Lunch Train

A zero-friction daily lunch ritual for UIUC CS grad students, delivered to
Slack **without installing any Slack app** — it rides the GitHub app your
workspace already has. Every weekday at **11:00am** a GitHub Action opens an
issue in this repo titled like:

> 🍣 Lunch today: Sakanaya — 12:15 at the Siebel lobby

The GitHub Slack app mirrors it into the lunch channel as a card. Joining
lunch = reacting 🙋 on that card. Reactions are publicly visible, so the
headcount tallies itself.

No servers, no database, no secrets, no cost: GitHub Actions is the
scheduler, the repo is the config, and the issue tracker is the message bus.
Changing the restaurant list is a pull request anyone can send.

## One-time setup (~3 minutes)

1. **Push this repo to GitHub as a public repo** (it contains no secrets by
   design). Check that Actions are enabled (Actions tab).
2. **In the Slack lunch channel**, run:

   ```
   /github subscribe <owner>/cslunch issues +label:"lunch"
   ```

   The first time, the GitHub app will ask you to connect your GitHub
   account — that's a personal link, not a workspace-admin action. The
   `+label:"lunch"` filter matters: it keeps unrelated repo issues out of the
   channel *and* lets the cleanup job close old issues silently (see below).
3. **Test it**: Actions tab → *Post lunch call* → *Run workflow*. A card
   should appear in the channel within seconds.

## Making the Slack card pretty (optional, recommended)

The card's chrome (byline, issue number, footer) belongs to the GitHub app,
but the byline author is whoever's token opens the issue. To upgrade it from
`github-actions[bot]`:

1. Create a free GitHub **machine account** (e.g. `uiuc-lunch-train`) and
   upload [`assets/avatar.png`](assets/avatar.png) — a pixel-art lunch train
   in Illini colors, regenerable via `scripts/make_avatar.py` — as its
   profile picture.
2. Add it as a collaborator on this repo with **Write** access (it creates
   labels and closes issues, not just opens them).
3. As that account, create a fine-grained PAT (repo: this one; permissions:
   *Issues: Read and write*) and save it as an Actions secret named
   `LUNCH_TOKEN`. The workflows use it automatically and fall back to
   `github.token` when absent. Fine-grained PATs expire within a year; an
   expired (but still present) secret fails the workflow rather than falling
   back, so renew or delete it when the time comes.

The card text itself is deliberately minimal and identical every day — the
title carries restaurant/time/place, the body is an RSVP line plus weather
(live WMO condition code → emoji) and a map link. That's the whole surface
the GitHub app gives us: colored bars, buttons, and boxes are Slack Block
Kit features, which require posting as an installed Slack app. Preview any
date locally:

```sh
DRY_RUN=1 LUNCH_DATE=2026-08-21 python3 scripts/bot.py post
```

## How the pieces work

- [`scripts/bot.py`](scripts/bot.py) — stdlib-only Python. `post` picks the
  restaurant (deterministic rotation by date — no state), fetches noon
  weather from Open-Meteo (free, no key), and opens the labeled issue.
- [`.github/workflows/post.yml`](.github/workflows/post.yml) — weekdays at
  11:00 Chicago time. The cron fires at two UTC hours because GitHub cron
  ignores DST; the script keeps whichever run is 11am locally. GitHub cron
  can drift 5–15 minutes at busy times.
- [`.github/workflows/cleanup.yml`](.github/workflows/cleanup.yml) — Saturday
  nights, closes past lunch issues so they don't pile up. It **removes the
  `lunch` label before closing**, so the close event no longer matches the
  channel's label filter and Slack stays quiet. If you ever do see "issue
  closed" cards in the channel, that trick stopped working — just disable
  this workflow and close issues by hand occasionally.

## Changing today's plan

If the thread decides on a different spot, no tooling is required — a
comment wins. To also update the card: Actions → *Post lunch call* → *Run
workflow* → type a restaurant into the override box (matches the rotation
by substring, or takes any free-text place). It silently closes today's
issue and posts a replacement card. Requires repo write access, so add
frequent lunchers as collaborators.

## Customizing

- **Restaurants** — edit [`restaurants.json`](restaurants.json). PRs welcome!
  `"close": true` marks spots near Siebel; on rainy (≥50%) or bitter
  (feels-like ≤15°F) days the bot only picks from those.
- **Meeting time/spot, weather thresholds** — [`config.json`](config.json).
- **Breaks and holidays** — [`skip_dates.txt`](skip_dates.txt) (update each
  semester; weekends are skipped automatically).

## Testing locally

```sh
DRY_RUN=1 FORCE=1 python3 scripts/bot.py post     # prints the would-be issue
DRY_RUN=1 GITHUB_REPOSITORY=<owner>/cslunch python3 scripts/bot.py cleanup
```

`FORCE=1` bypasses the "only at 11am on a non-skipped weekday" guard, which
otherwise makes the script exit silently outside its window.

## History & plan B

The first commit of this repo contains a direct Slack-bot variant (own Slack
app, `chat.postMessage`, and an 11:45 reaction-tally with quorum logic). It's
strictly nicer — cleaner messages, automatic "It's on!" announcements — but
needs a free app slot in the workspace, which is currently full (free-plan
cap of 10). If a slot ever opens, resurrect it from git history.
