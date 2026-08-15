#!/usr/bin/env python3
"""Lunch Train bot: posts a daily lunch call and tallies RSVPs.

Usage:
  python scripts/bot.py post   # 11:00am CT: announce today's restaurant
  python scripts/bot.py tally  # 11:45am CT: count reactions, announce headcount

Environment:
  SLACK_BOT_TOKEN  Slack bot token (xoxb-...). Required unless DRY_RUN post.
  DRY_RUN=1        Print messages instead of posting them.
  FORCE=1          Skip the 11am/weekday/skip-date guards (manual runs).

No third-party dependencies — Python 3.9+ stdlib only.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text())
TZ = ZoneInfo(CONFIG["timezone"])


def slack(method, **params):
    """Call a Slack Web API method (form-encoded, which every method accepts)."""
    if os.environ.get("DRY_RUN") == "1" and method == "chat.postMessage":
        print(f"[dry-run] {method}:\n{params.get('text', '')}\n")
        return {"ok": True, "ts": "0"}
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        sys.exit("SLACK_BOT_TOKEN is not set.")
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=urllib.parse.urlencode(params).encode(),
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    if not data.get("ok"):
        sys.exit(f"Slack API error from {method}: {data.get('error')}")
    return data


def skip_dates():
    """Parse skip_dates.txt: one YYYY-MM-DD or YYYY-MM-DD..YYYY-MM-DD per line."""
    days = set()
    path = ROOT / "skip_dates.txt"
    if not path.exists():
        return days
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if ".." in line:
            start_s, end_s = line.split("..", 1)
            d = date.fromisoformat(start_s.strip())
            end = date.fromisoformat(end_s.strip())
            while d <= end:
                days.add(d)
                d += timedelta(days=1)
        else:
            days.add(date.fromisoformat(line))
    return days


def guard(now):
    """Exit quietly unless it's a lunch day at 11am local time.

    The cron fires at both 16:xx and 17:xx UTC because GitHub Actions cron
    doesn't know about DST; exactly one of those is 11am in Chicago.
    """
    if os.environ.get("FORCE") == "1":
        return
    if now.hour != 11:
        sys.exit(0)  # the wrong-DST duplicate firing
    if now.weekday() >= 5:
        sys.exit(0)
    if now.date() in skip_dates():
        print(f"{now.date()} is in skip_dates.txt; staying quiet.")
        sys.exit(0)


def noon_weather():
    """Feels-like temp and rain chance at noon from Open-Meteo (no API key)."""
    query = urllib.parse.urlencode({
        "latitude": CONFIG["latitude"],
        "longitude": CONFIG["longitude"],
        "hourly": "precipitation_probability,apparent_temperature",
        "temperature_unit": "fahrenheit",
        "timezone": CONFIG["timezone"],
        "forecast_days": 1,
    })
    try:
        url = f"https://api.open-meteo.com/v1/forecast?{query}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp)
        hourly = data["hourly"]
        idx = next(i for i, t in enumerate(hourly["time"]) if t.endswith("T12:00"))
        return {
            "precip": hourly["precipitation_probability"][idx],
            "feels": hourly["apparent_temperature"][idx],
        }
    except Exception as exc:  # weather is a nicety; never block the lunch call
        print(f"Weather lookup failed ({exc}); posting without it.")
        return None


def pick_restaurant(today, bad_weather):
    menu = json.loads((ROOT / "restaurants.json").read_text())
    if bad_weather:
        menu = [r for r in menu if r.get("close")] or menu
    return menu[today.toordinal() % len(menu)]


def post(now):
    weather = noon_weather()
    bad = weather is not None and (
        weather["precip"] >= CONFIG["bad_weather"]["max_precip_percent"]
        or weather["feels"] <= CONFIG["bad_weather"]["min_feels_like_f"]
    )
    r = pick_restaurant(now.date(), bad)
    lines = [
        f"{r['emoji']} *Lunch today: {r['name']}* — meet {CONFIG['meet_time']} at {CONFIG['meet_spot']}.",
        f"React :raised_hand: if you're in! Headcount goes out at {CONFIG['tally_time']}.",
    ]
    if weather:
        note = (
            f"_Noon weather: feels like {round(weather['feels'])}°F, "
            f"{round(weather['precip'])}% chance of rain._"
        )
        if bad:
            note += " _(picked somewhere close by)_"
        lines.append(note)
    slack(
        "chat.postMessage",
        channel=CONFIG["channel_id"],
        text="\n".join(lines),
        unfurl_links="false",
    )
    print(f"Posted lunch call for {r['name']}.")


def tally(now):
    channel = CONFIG["channel_id"]
    bot_id = slack("auth.test")["user_id"]
    midnight = datetime.combine(now.date(), time.min, tzinfo=TZ).timestamp()
    history = slack(
        "conversations.history", channel=channel, oldest=f"{midnight:.6f}", limit="100"
    )
    lunch_post = next(
        (
            m for m in history["messages"]
            if m.get("user") == bot_id and "Lunch today" in m.get("text", "")
        ),
        None,
    )
    if lunch_post is None:
        sys.exit("No lunch post found today; nothing to tally.")

    full = slack(
        "reactions.get", channel=channel, timestamp=lunch_post["ts"], full="true"
    )
    goers = sorted({
        user
        for reaction in full["message"].get("reactions", [])
        for user in reaction.get("users", [])
        if user != bot_id
    })

    if not goers:
        print("No reactions today; staying quiet.")
        return

    mentions = ", ".join(f"<@{u}>" for u in goers)
    if len(goers) >= CONFIG["quorum"]:
        text = (
            f":steam_locomotive: *It's on!* {len(goers)} going: {mentions}\n"
            f"See you at {CONFIG['meet_time']} — {CONFIG['meet_spot']}."
        )
        broadcast = "true"  # show the good news in the channel, not just the thread
    else:
        text = (
            f"{len(goers)} in so far ({mentions}) — small crew today, "
            "coordinate here if plans shift!"
        )
        broadcast = "false"
    slack(
        "chat.postMessage",
        channel=channel,
        thread_ts=lunch_post["ts"],
        reply_broadcast=broadcast,
        text=text,
    )
    print(f"Tally posted: {len(goers)} going.")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("post", "tally"):
        sys.exit(__doc__)
    if CONFIG["channel_id"].startswith("C0XXX") and os.environ.get("DRY_RUN") != "1":
        sys.exit("Edit config.json: channel_id is still the placeholder.")
    now = datetime.now(TZ)
    guard(now)
    if sys.argv[1] == "post":
        post(now)
    else:
        tally(now)


if __name__ == "__main__":
    main()
