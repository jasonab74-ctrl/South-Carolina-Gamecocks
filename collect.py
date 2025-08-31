#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Collector that fetches FEEDS (RSS/Atom), filters for Gamecocks content,
and writes items.json. Filtering is relaxed to ensure population while
still excluding other sports.
"""

import os
import re
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
from feeds import FEEDS

# ------------------ Filtering ------------------
TEAM_PATTERNS = {
    # Relaxed: any clear Gamecocks affinity
    "must_any": [
        r"\b(south\s*carolina)\b",
        r"\b(gamecocks?)\b",
        r"\b(shane\s+beamer)\b",
        r"\bwilliams[- ]brice\b",
        r"\bcolumbia,\s*sc\b",
        r"\bspurs\s*up\b",
        r"\bgamecock\s*central\b",
    ],
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
    "reddit.com",
    "news.google.com",
}

def _domain(u: str) -> str:
    try:
        return urlparse(u).netloc.lower().replace("www.", "")
    except Exception:
        return ""

def _strip_html(s: str) -> str:
    return re.sub(r"<.*?>", "", s or "")

def _pass_filter(title: str, summary: str, link: str, feed_url: str) -> bool:
    text = f"{title} {summary}".lower()

    # Exclude other sports
    for pat in TEAM_PATTERNS["exclude"]:
        if re.search(pat, text, flags=re.I):
            return False

    dom = _domain(feed_url or link)
    # Trusted domains only need team affinity once
    for pat in TEAM_PATTERNS["must_any"]:
        if re.search(pat, text, flags=re.I):
            return True

    # Otherwise, allow if any team pattern appears
    return any(re.search(pat, text, flags=re.I) for pat in TEAM_PATTERNS["must_any"])

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

    for f in FEEDS:
        name, url = f.get("name", "Unknown"), f.get("url", "")
        try:
            parsed = feedparser.parse(url)
            for e in parsed.get("entries", []):
                it = _normalize(name, url, e)
                if _pass_filter(it["title"], it["summary"], it["link"], url):
                    items.append(it)
        except Exception:
            # Quietly skip bad feeds; don't pollute UI with error cards
            continue

    # Dedupe by link (or title+source as fallback)
    seen, deduped = set(), []
    for it in items:
        k = it["link"] or (it["title"], it["source"])
        if k in seen:
            continue
        seen.add(k)
        deduped.append(it)

    # Sort newest-ish first (strings are fine for most feed timestamps)
    deduped.sort(key=lambda x: x.get("published", ""), reverse=True)

    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "items": deduped[:250],
    }
    with open(items_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload

if __name__ == "__main__":
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    ITEMS_PATH = os.path.join(APP_DIR, "items.json")
    out = collect(ITEMS_PATH)
    print(f"Wrote {len(out.get('items', []))} items to {ITEMS_PATH}")
