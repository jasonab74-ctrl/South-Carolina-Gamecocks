#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Collector for South Carolina Gamecocks.
- Requests with real User-Agent (some feeds block default fetchers)
- Two-stage filtering: strict first, then fallback to avoid empty lists
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

STRONG_ANY = [
    r"\bgamecocks?\b",
    r"\bshane\s+beamer\b",
    r"\bwilliams[- ]brice\b",
    r"\bspurs\s*up\b",
    r"\bgamecock\s*central\b",
]

SC_OR_USC = [
    r"\bsouth\s*carolina\b",
    r"\busc\b",  # guarded against USC Trojans below
]

FOOTBALL_TERMS = [
    r"\bfootball\b", r"\bcoach(es|ing)?\b", r"\bquarterback|qb\b",
    r"\bdefense|offense\b", r"\bsec\b", r"\bncaa\b",
    r"\brecruit|\bcommit|\btransfer portal\b", r"\bspring game\b", r"\bdepth chart\b",
]

EXCLUDE_OTHER_SPORTS = [
    r"\bwomen'?s\b", r"\bwbb\b",
    r"\bbasketball\b", r"\bbaseball\b",
    r"\bsoftball\b", r"\bvolleyball\b", r"\bsoccer\b",
    r"\btrack\b", r"\bgolf\b",
]

NEGATIVE_USC = [r"\btrojans\b", r"\blincoln\s+riley\b", r"\busc\s+trojans\b"]


def _strip_html(s: str) -> str:
    return re.sub(r"<.*?>", "", s or "")


def _fetch_and_parse(url: str):
    """Fetch via requests for compatibility, then parse with feedparser."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception:
        return feedparser.parse(url)


def _matches_any(patterns, text) -> bool:
    return any(re.search(p, text, flags=re.I) for p in patterns)


def _strict_keep(text: str) -> bool:
    # Exclude other sports
    if _matches_any(EXCLUDE_OTHER_SPORTS, text):
        return False
    # Very strong tokens
    if _matches_any(STRONG_ANY, text):
        return True
    # SC/USC with football context (and not Trojans)
    if _matches_any(SC_OR_USC, text):
        if _matches_any(NEGATIVE_USC, text):
            return False
        if _matches_any(FOOTBALL_TERMS, text):
            return True
    return False


def _fallback_keep(text: str) -> bool:
    if _matches_any(EXCLUDE_OTHER_SPORTS, text):
        return False
    if _matches_any(STRONG_ANY, text) or _matches_any(SC_OR_USC, text):
        if _matches_any(NEGATIVE_USC, text):
            return False
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
    items_strict = []
    items_raw = []

    for f in FEEDS:
        name, url = f.get("name", "Unknown"), f.get("url", "")
        parsed = _fetch_and_parse(url)
        for e in parsed.get("entries", []):
            it = _normalize(name, url, e)
            items_raw.append(it)
            text = f"{it['title']} {it['summary']}".lower()
            if _strict_keep(text):
                items_strict.append(it)

    # Dedupe helper
    def _dedupe(lst):
        seen, out = set(), []
        for it in lst:
            k = it["link"] or (it["title"], it["source"])
            if k in seen:
                continue
            seen.add(k)
            out.append(it)
        return out

    items = _dedupe(items_strict)

    # Fallback: if still light, add SC/GC mentions from raw
    THRESH = 12
    if len(items) < THRESH:
        extra = []
        for it in items_raw:
            t = f"{it['title']} {it['summary']}".lower()
            if _fallback_keep(t):
                extra.append(it)
        items = _dedupe(items + extra)

    # Final sort
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
