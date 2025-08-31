#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Safe-mode collector for South Carolina Gamecocks.
Strategy:
  1) Fetch feeds with a real User-Agent.
  2) Keep items that clearly match Gamecocks/SC football (strict).
  3) If < 12 items, add a fallback pass (broader SC/Gamecocks, still excluding other sports).
  4) If STILL low (< 6), keep latest items from Google/Bing feeds without filtering.
This guarantees items.json is never empty while staying on-topic first.
"""

import os
import re
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import requests
from feeds import FEEDS

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/xml,text/xml,application/rss+xml,*/*;q=0.8"}
TIMEOUT = 25

# --- Patterns ---
STRONG_ANY = [
    r"\bgamecocks?\b",
    r"\bshane\s+beamer\b",
    r"\bwilliams[- ]brice\b",
    r"\bspurs\s*up\b",
    r"\bgamecock\s*central\b",
]
SC_OR_USC = [r"\bsouth\s*carolina\b", r"\busc\b"]
FOOTBALL = [
    r"\bfootball\b", r"\bcoach(?:es|ing)?\b", r"\bquarterback|qb\b",
    r"\bdefense|offense\b", r"\bsec\b", r"\bncaa\b",
    r"\brecruit|\bcommit|\btransfer portal\b", r"\bspring game\b", r"\bdepth chart\b",
]
EXCLUDE_OTHER_SPORTS = [
    r"\bwomen'?s\b", r"\bwbb\b",
    r"\bbasketball\b", r"\bbaseball\b",
    r"\bsoftball\b", r"\bvolleyball\b", r"\bsoccer\b",
    r"\btrack\b", r"\bgolf\b",
]
NEGATIVE_USC = [r"\btrojans\b", r"\blincoln\s+riley\b", r"\busc\s+trojans\b"]  # guard vs SoCal

def _strip_html(s: str) -> str:
    return re.sub(r"<.*?>", "", s or "")

def _fetch(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception:
        return feedparser.parse(url)

def _keep_strict(text: str) -> bool:
    if any(re.search(p, text, re.I) for p in EXCLUDE_OTHER_SPORTS):
        return False
    if any(re.search(p, text, re.I) for p in STRONG_ANY):
        return True
    if any(re.search(p, text, re.I) for p in SC_OR_USC):
        if any(re.search(p, text, re.I) for p in NEGATIVE_USC):
            return False
        if any(re.search(p, text, re.I) for p in FOOTBALL):
            return True
    return False

def _keep_fallback(text: str) -> bool:
    if any(re.search(p, text, re.I) for p in EXCLUDE_OTHER_SPORTS):
        return False
    if any(re.search(p, text, re.I) for p in NEGATIVE_USC):
        return False
    return any(re.search(p, text, re.I) for p in (STRONG_ANY + SC_OR_USC + FOOTBALL))

def _normalize(feed_name, feed_url, e):
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

def _dedupe(lst):
    seen, out = set(), []
    for it in lst:
        k = it["link"] or (it["title"], it["source"])
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out

def collect(items_path: str) -> dict:
    raw = []
    keep = []

    for f in FEEDS:
        name, url = f.get("name", "Unknown"), f.get("url", "")
        parsed = _fetch(url)
        for e in parsed.get("entries", []):
            it = _normalize(name, url, e)
            raw.append(it)
            txt = f"{it['title']} {it['summary']}".lower()
            if _keep_strict(txt):
                keep.append(it)

    keep = _dedupe(keep)

    # Fallback layers
    if len(keep) < 12:
        extra = []
        for it in raw:
            txt = f"{it['title']} {it['summary']}".lower()
            if _keep_fallback(txt):
                extra.append(it)
        keep = _dedupe(keep + extra)

    if len(keep) < 6:
        # Absolute safety net: take latest from Google/Bing feeds regardless of filters
        for it in raw:
            if "news.google.com" in it["source_url"] or "bing.com/news" in it["source_url"]:
                keep.append(it)
        keep = _dedupe(keep)

    keep.sort(key=lambda x: x.get("published", ""), reverse=True)

    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "items": keep[:250],
    }
    with open(items_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload

if __name__ == "__main__":
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    ITEMS_PATH = os.path.join(APP_DIR, "items.json")
    out = collect(ITEMS_PATH)
    print(f"Wrote {len(out.get('items', []))} items to {ITEMS_PATH}")
