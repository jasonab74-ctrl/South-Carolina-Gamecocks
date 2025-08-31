#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Collector for South Carolina Gamecocks.
- Uses requests with a real User-Agent (some feeds block default fetchers)
- Relaxed but targeted filters (keeps Gamecocks, excludes other sports)
- Fallback: if <10 items after filtering, do a second pass to make sure the feed isn't empty
- Writes items.json consumed by the Flask app
"""

import os
import re
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import requests

from feeds import FEEDS

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TIMEOUT = 20

TEAM_PATTERNS = {
    # What we positively look for (any of these):
    "must_any": [
        r"\b(south\s*carolina)\b",
        r"\b(gamecocks?)\b",
        r"\b(shane\s+beamer)\b",
        r"\bwilliams[- ]brice\b",
        r"\bcolumbia,\s*sc\b",
        r"\bspurs\s*up\b",
        r"\bgamecock\s*central\b",
    ],
    # Sports we do NOT want:
    "exclude": [
        r"\bwomen'?s\b", r"\bwbb\b",
        r"\bbasketball\b", r"\bbaseball\b",
        r"\bsoftball\b", r"\bvolleyball\b", r"\bsoccer\b",
    ],
}

TRUSTED_DOMAINS = {
    "gamecocksonline.com",
    "thestate.com",
    "garnetandblackattack.com",
    "247sports.com",
    "on3.com",
    "espn.com",
    "cbssports.com",
    "yahoo.com",
    "news.google.com",
    "reddit.com",
}

def _domain(u: str) -> str:
    try:
        return urlparse(u).netloc.lower().replace("www.", "")
    except Exception:
        return ""

def _strip_html(s: str) -> str:
    return re.sub(r"<.*?>", "", s or "")

def _fetch_and_parse(url: str):
    """Fetch with requests (real UA), then parse with feedparser."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception:
        # Fallback to feedparser's own fetch if requests fails
        return feedparser.parse(url)

def _pass_filter(title: str, summary: str) -> bool:
    """Return True if item matches our keep rules."""
    text = f"{title} {summary}".lower()

    # Exclude obvious other sports
    for pat in TEAM_PATTERNS["exclude"]:
        if re.search(pat, text, flags=re.I):
            return False

    # Keep if ANY team affinity appears
    for pat in TEAM_PATTERNS["must_any"]:
        if re.search(pat, text, flags=re.I):
            return True

    return False

def _normalize(feed_name: str, feed_url: str, e) -> dict:
    title = (e.get("title") or "").strip()
    link = e.get("link") or e.get("id") or ""
    summary = (e.get("summary") or e.get("description") or "").strip()
    published = e.get("published") or e.get("updated") or ""
    return {
        "source": feed_name,
        "source_url": feed_url,
        "title": title,
        "link": link,
        "summary": _strip_html(summary)[:400],
        "published": published,
    }

def collect(items_path: str) -> dict:
    items = []
    raw_items = []

    for f in FEEDS:
        name, url = f.get("name", "Unknown"), f.get("url", "")
        parsed = _fetch_and_parse(url)
        for e in parsed.get("entries", []):
            it = _normalize(name, url, e)
            raw_items.append(it)
            if _pass_filter(it["title"], it["summary"]):
                items.append(it)

    # Dedupe by link (or title+source as fallback)
    def _dedupe(lst):
        seen, out = set(), []
        for it in lst:
            k = it["link"] or (it["title"], it["source"])
            if k in seen:
                continue
            seen.add(k)
            out.append(it)
        return out

    items = _dedupe(items)

    # Fallback: if we got too few, try to keep at least something relevant
    if len(items) < 10:
        fallback = []
        for it in raw_items:
            text = f"{it['title']} {it['summary']}".lower()
            if any(re.search(p, text, flags=re.I) for p in TEAM_PATTERNS["must_any"]):
                # still respect exclusions
                if not any(re.search(p, text, flags=re.I) for p in TEAM_PATTERNS["exclude"]):
                    fallback.append(it)
        items = _dedupe(items + fallback)

    # Sort newest-ish first
    items.sort(key=lambda x: x.get("published", ""), reverse=True)

    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "items": items[:250],
    }
    with open(items_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload

if __name__ == "__main__":
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    ITEMS_PATH = os.path.join(APP_DIR, "items.json")
    out = collect(ITEMS_PATH)
    print(f"Wrote {len(out.get('items', []))} items to {ITEMS_PATH}")
