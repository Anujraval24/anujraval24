#!/usr/bin/env python3
"""Refresh data/contributions.json (and data/avatar.jpg) from GitHub.

Run by .github/workflows/cards.yml every day. Needs GH_TOKEN in the
environment; the workflow's built-in GITHUB_TOKEN is enough for public data.
If the daily calendar ever comes back empty, add a classic personal access
token as the PROFILE_TOKEN repo secret and the workflow will prefer it.

Exits non-zero on any failure so the Action goes red instead of committing
stale or half-empty data.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE = json.loads((ROOT / "data" / "profile.json").read_text())
LOGIN = PROFILE["login"]
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    avatarUrl
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def call(url, payload=None):
    headers = {"User-Agent": "profile-cards", "Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main():
    if not TOKEN:
        sys.exit("GH_TOKEN is not set")

    raw = call("https://api.github.com/graphql", {"query": QUERY, "variables": {"login": LOGIN}})
    body = json.loads(raw)
    if body.get("errors") or not body.get("data", {}).get("user"):
        sys.exit(f"GraphQL error: {body.get('errors') or 'user not found'}")
    user = body["data"]["user"]
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [
        {"date": d["date"], "count": d["contributionCount"]}
        for w in cal["weeks"]
        for d in w["contributionDays"]
    ]
    days.sort(key=lambda d: d["date"])
    if len(days) < 300:
        sys.exit(f"Calendar looks truncated ({len(days)} days); keeping previous data")

    repos = []
    for name in PROFILE["featured_repos"]:
        r = json.loads(call(f"https://api.github.com/repos/{LOGIN}/{name}"))
        repos.append(
            {
                "name": r["name"],
                "description": r.get("description") or "",
                "language": r.get("language") or "",
                "stars": r["stargazers_count"],
                "forks": r["forks_count"],
                "url": r["html_url"],
            }
        )

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sample": False,
        "login": LOGIN,
        "name": user.get("name") or PROFILE["name"],
        "total": cal["totalContributions"],
        "days": days,
        "repos": repos,
    }
    (ROOT / "data" / "contributions.json").write_text(json.dumps(out, indent=1) + "\n")

    # Portrait source, used only when profile.json sets "portrait": "data/avatar.jpg".
    try:
        (ROOT / "data" / "avatar.jpg").write_bytes(call(user["avatarUrl"] + ("&" if "?" in user["avatarUrl"] else "?") + "s=240"))
    except (urllib.error.URLError, OSError) as e:
        print(f"avatar skipped: {e}")

    print(f"{len(days)} days, {cal['totalContributions']} contributions, {len(repos)} repos")


if __name__ == "__main__":
    main()
