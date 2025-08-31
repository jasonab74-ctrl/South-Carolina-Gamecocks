#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, re, feedparser
from datetime import datetime, timezone
from urllib.parse import urlparse

from feeds import FEEDS

TEAM_WORDS = {
    "must": [r"\b(south carolina|gamecocks?)\b", r"\bfootball\b"],
    "allow_names": [
        r"\bshane beamer\b", r"\bwilliams[- ]brice\b", r"\bcolumbia,? sc\b",
        r"\bspurs up\b", r"\bcocky\b", r"\bgamecock central\b",
    ],
    "exclude": [r"\bbasketball\b", r"\bwomen'?s\b", r"\bwbb\b", r"\bbaseball\b",
                r"\bsoftball\b", r"\bvolleyball\b", r"\bsoccer\b"],
}

TRUSTED_SOURCES = set([
    "gamecocksonline.com","247sports.com","on3.com","espn.com","cbssports.com",
    "yahoo.com","thestate.com","gamecockcentral.com","garnetandblackattack.com",
    "reddit.com","youtube.com","news.google.com",
])

def _dom(u): 
    try: return urlparse(u).netloc.lower().replace("www.","")
    except: return ""

def allow_item(title, summary, link, source_url):
    text = f"{title} {summary}".lower()
    for pat in TEAM_WORDS["exclude"]:
        if re.search(pat, text, flags=re.I): return False
    if _dom(source_url or link) in TRUSTED_SOURCES:
        if re.search(r"\b(south carolina|gamecocks?)\b", text, flags=re.I): return True
    if all(re.search(pat, text, flags=re.I) for pat in TEAM_WORDS["must"]): return True
    for pat in TEAM_WORDS["allow_names"]:
        if re.search(pat, text, flags=re.I): return True
    return False

def normalize(feed_name, src_url, e):
    title = (e.get("title") or "").strip()
    link = e.get("link") or e.get("id") or ""
    summary = (e.get("summary") or e.get("description") or "").strip()
    published = e.get("published") or e.get("updated") or ""
    return {
        "source": feed_name, "source_url": src_url, "title": title, "link": link,
        "summary": re.sub("<.*?>","", summary)[:400], "published": published,
    }

def collect(items_path):
    items = []
    for f in FEEDS:
        name, url = f["name"], f["url"]
        parsed = feedparser.parse(url)
        for e in parsed.get("entries", []):
            it = normalize(name, url, e)
            if allow_item(it["title"], it["summary"], it["link"], url):
                items.append(it)
    # dedupe by link
    seen, deduped = set(), []
    for it in items:
        k = it["link"] or (it["title"], it["source"])
        if k in seen: continue
        seen.add(k); deduped.append(it)
    deduped.sort(key=lambda x: x.get("published",""), reverse=True)
    payload = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"),
               "items": deduped[:250]}
    with open(items_path,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=2)
    return payload

if __name__ == "__main__":
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    ITEMS_PATH = os.path.join(APP_DIR,"items.json")
    out = collect(ITEMS_PATH)
    print(f"Wrote {len(out.get('items', []))} items to {ITEMS_PATH}")
