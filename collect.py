#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
collect.py — South Carolina Gamecocks (Football-focused) feed collector

- Pulls from FEEDS in feeds.py
- Filters for Gamecocks content (no longer requires the literal word "football")
- Excludes other sports (basketball, baseball, etc.)
- Writes items.json with {updated, items[]} for the web app to render
"""

import os
import re
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser

# Import FEEDS list from local module
from feeds import FEEDS

# ------------------------------
# Filtering rules (Gamecocks)
# ------------------------------
TEAM_WORDS = {
    # Relaxed: only requires team affinity mention
    "must": [
        r"\b(south\s*carolina|gamecocks?)\b",
    ],
    "allow_names": [
        r"\bshane\s+beamer\b",
        r"\bwilliams[- ]brice\b",
        r"\bcolumbia,?\s*sc\b",
        r"\bspurs\s*up\b",
        r"\bcocky\b",
        r"\bgamecock\s*central\b",
    ],
    "exclude": [
        r"\bbasketball\b",
        r"\bwomen'?s\b",
        r"\bwbb\b",
        r"\bbaseball\b",
        r"\bsoftball\b",
        r"\bvolleyball\b",
        r"\bsoccer\b",
        r"\bsoftball\b",
    ],
}

# Trusted domains (skip "football" requirement, but still must be Gamecocks-related)
TRUSTED_SOURCES = set([
    "gamecocksonline.com",
    "247sports.com",
    "on3.com",
    "espn.com",
    "cbssports.com",
    "yahoo.com",
    "thestate.com",
    "gamecockcentral.com",
    "garnetandblackattack.com",
    "reddit.com",
    "youtube.com",
    "news.google.com",
])

def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""

def _strip_html(s: str) -> str:
    # quick-n-dirty HTML tag stripper
    return re.sub(r"<.*?>", "", s or "")

def allow_item(title: str, summary: str, link: str, source_url: str) -> bool:
    """
    Returns True iff the item should be kept.
    """
    text = f"{title} {summary}".lower()

    # Exclude non-football sports/topics first
    for pat in TEAM_WORDS["exclude"]:
        if re.search(pat, text, flags=re.I):
            return False

    src_dom = _domain(source_url or link)
    is_trusted = src_dom in TRUSTED_SOURCES

    # Trusted sources: only require Gamecocks affinity
    if is_trusted and re.search(TEAM_WORDS["must"][0], text, flags=re.I):
        return True

    # Non-trusted: must match team affinity pattern(s)
    if all(re.search(pat, text, flags=re.I) for pat in TEAM_WORDS["must"]):
        return True

    # Or match any allow-listed names/terms
    for pat in TEAM_WORDS["allow_names"]:
        if re.search(pat, text, flags=re.I):
            return True

    return False

def _normalize(feed_name: str, src_url: str, entry) -> dict:
    title = (entry.get("title") or "").strip()
    link = entry.get("link") or entry.get("id") or ""
    summary = (entry.get("summary") or entry.get("description") or "").strip()
    published = entry.get("published") or entry.get("updated") or ""
    return {
        "source": feed_name,
        "source_url": src_url,
        "title": title,
        "link": link,
        "summary": _strip_html(summary)[:400],
        "published": published,
    }

def collect(items_path: str) -> dict:
    """
    Parse all FEEDS, filter, dedupe, sort, and write items.json.
    """
    items = []

    for f in FEEDS:
        name = f.get("name", "Unknown")
        url = f.get("url", "")
        try:
            parsed = feedparser.parse(url)
            for e in parsed.get("entries", []):
                it = _normalize(name, url, e)
                if allow_item(it["title"], it["summary"], it["link"], url):
                    items.append(it)
        except Exception as ex:
            # keep going; include an error item for visibility
            items.append({
                "source": name,
                "source_url": url,
                "title": f"[Error reading feed: {name}]",
                "link": url,
                "summary": str(ex),
                "published": "",
            })

    # Deduplicate by link (fallback: title+source)
    seen = set()
    deduped = []
    for it in items:
        key = it["link"] or (it["title"], it["source"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    # Sort "newest-ish" first (string compare is fine for most feeds)
    deduped.sort(key=lambda x: x.get("published", ""), reverse=True)

    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "items": deduped[:250],
    }

    # Write items.json
    with open(items_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload

if __name__ == "__main__":
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    ITEMS_PATH = os.environ.get("ITEMS_PATH", os.path.join(APP_DIR, "items.json"))
    print(f"[collect] Writing to: {ITEMS_PATH}")
    out = collect(ITEMS_PATH)
    print(f"[collect] Total items: {len(out.get('items', []))}")
