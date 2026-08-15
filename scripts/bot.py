#!/usr/bin/env python3
"""Lunch Train: daily lunch call, relayed to Slack by the GitHub app.

Opens a GitHub issue at 11am CT; the workspace's already-installed GitHub
Slack app (subscribed via `/github subscribe <owner>/<repo> issues
+label:"lunch"`) mirrors it into the lunch channel as a card. No Slack app,
no bot tokens, no secrets of any kind.

Usage:
  python scripts/bot.py post     # 11:00am CT: open today's lunch issue
  python scripts/bot.py cleanup  # weekly: unlabel then close old lunch issues
                                 # (unlabeling first keeps the closes out of
                                 # Slack, since the subscription filters on
                                 # the "lunch" label)

Environment:
  GITHUB_TOKEN       set automatically in Actions (github.token)
  GITHUB_REPOSITORY  owner/repo, set automatically in Actions
  DRY_RUN=1          print API writes instead of performing them
  FORCE=1            skip the 11am/weekday/skip-date guards (manual runs)

No third-party dependencies — Python 3.9+ stdlib only.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text())
TZ = ZoneInfo(CONFIG["timezone"])
API = "https://api.github.com"
LABEL = "lunch"


def repo():
    slug = os.environ.get("GITHUB_REPOSITORY")
    if not slug:
        if os.environ.get("DRY_RUN") == "1":
            return "OWNER/cslunch"
        sys.exit("GITHUB_REPOSITORY is not set.")
    return slug


def github(method, path, payload=None, ok_statuses=()):
    """Call the GitHub REST API. Writes are printed instead under DRY_RUN."""
    if os.environ.get("DRY_RUN") == "1" and method != "GET":
        body = json.dumps(payload, indent=2, ensure_ascii=False) if payload else ""
        print(f"[dry-run] {method} {path}\n{body}\n")
        return {}
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif method != "GET":
        sys.exit("GITHUB_TOKEN is not set.")
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        if err.code in ok_statuses:
            return {}
        sys.exit(f"GitHub API {method} {path} failed: {err.code} {err.read().decode()}")


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


def ensure_label(slug):
    github(
        "POST",
        f"/repos/{slug}/labels",
        {"name": LABEL, "color": "d97706", "description": "Daily lunch call"},
        ok_statuses=(422,),  # already exists
    )


def post(now):
    weather = noon_weather()
    bad = weather is not None and (
        weather["precip"] >= CONFIG["bad_weather"]["max_precip_percent"]
        or weather["feels"] <= CONFIG["bad_weather"]["min_feels_like_f"]
    )
    r = pick_restaurant(now.date(), bad)
    title = f"{r['emoji']} Lunch today: {r['name']} — {CONFIG['meet_time']} at {CONFIG['meet_spot']}"
    body_lines = ["React 🙋 on this message in Slack if you're in!"]
    if weather:
        note = (
            f"Noon weather: feels like {round(weather['feels'])}°F, "
            f"{round(weather['precip'])}% chance of rain."
        )
        if bad:
            note += " (Picked somewhere close by.)"
        body_lines.append(note)
    slug = repo()
    ensure_label(slug)
    issue = github(
        "POST",
        f"/repos/{slug}/issues",
        {"title": title, "body": "\n\n".join(body_lines), "labels": [LABEL]},
    )
    print(f"Opened lunch issue: {issue.get('html_url', title)}")


def cleanup(now):
    """Close lunch issues from previous days without pinging Slack.

    Removing the "lunch" label first means the subsequent close event no
    longer matches the channel's +label:"lunch" subscription filter.
    """
    slug = repo()
    issues = github(
        "GET", f"/repos/{slug}/issues?labels={LABEL}&state=open&per_page=100"
    )
    today = now.date().isoformat()
    closed = 0
    for issue in issues:
        if issue["created_at"][:10] >= today:
            continue  # leave today's lunch call up
        num = issue["number"]
        github("DELETE", f"/repos/{slug}/issues/{num}/labels/{LABEL}")
        github("PATCH", f"/repos/{slug}/issues/{num}", {"state": "closed"})
        closed += 1
    print(f"Closed {closed} old lunch issue(s).")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("post", "cleanup"):
        sys.exit(__doc__)
    now = datetime.now(TZ)
    if sys.argv[1] == "post":
        guard(now)
        post(now)
    else:
        cleanup(now)


if __name__ == "__main__":
    main()
