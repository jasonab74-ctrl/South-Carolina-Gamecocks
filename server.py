#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
South Carolina Gamecocks — Football Feed (failsafe, single-file)
- No templates, no feeds.py, no file writes: everything in-memory.
- Always attempts to fetch on first request so the page shows items.
- Fight Song plays/pauses on-page from /static/fight-song.mp3 (optional).
"""

import time
import threading
from datetime import datetime, timezone
from typing import List, Dict
import feedparser
import requests

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# -------------------- Config --------------------
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HTTP_TIMEOUT = 20

FEED_URLS = [
    # Google News
    "https://news.google.com/rss/search?q=%22South+Carolina%22+Gamecocks+football&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22South+Carolina%22+football&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Gamecocks+football&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22Shane+Beamer%22&hl=en-US&gl=US&ceid=US:en",
    # Bing News
    "https://www.bing.com/news/search?q=South+Carolina+Gamecocks+football&format=rss",
    "https://www.bing.com/news/search?q=Shane+Beamer&format=rss",
    # Local / blogs
    "https://www.garnetandblackattack.com/rss/index.xml",
    "https://www.thestate.com/sports/college/university-of-south-carolina/usc-football/?outputType=amp&type=rss",
    # National CFB
    "https://www.espn.com/espn/rss/ncf/news",
]

# -------------------- In-memory store --------------------
ITEMS: List[Dict] = []
UPDATED: str = None
_LAST_FETCH_TS = 0.0
_FETCH_LOCK = threading.Lock()

def _http_get(url: str) -> bytes:
    r = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml,*/*;q=0.8"},
        timeout=HTTP_TIMEOUT,
        allow_redirects=True,
    )
    r.raise_for_status()
    return r.content

def _normalize_entry(feed_name: str, feed_url: str, e) -> Dict:
    title = (e.get("title") or "").strip()
    link = e.get("link") or e.get("id") or ""
    summary = (e.get("summary") or e.get("description") or "").strip()
    published = e.get("published") or e.get("updated") or ""
    ts = 0
    try:
        if e.get("published_parsed"):
            ts = time.mktime(e.published_parsed)
        elif e.get("updated_parsed"):
            ts = time.mktime(e.updated_parsed)
    except Exception:
        ts = 0
    return {
        "source": feed_name,
        "source_url": feed_url,
        "title": title,
        "link": link,
        "summary": _strip_html(summary)[:400],
        "published": published,
        "_ts": ts,
    }

def _strip_html(s: str) -> str:
    import re
    return re.sub(r"<.*?>", "", s or "")

def _dedupe(items: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for it in items:
        k = it["link"] or (it["title"], it["source"])
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out

def fetch_now() -> Dict:
    """Fetch all feeds (best-effort). Always returns some items if possible."""
    global ITEMS, UPDATED, _LAST_FETCH_TS
    with _FETCH_LOCK:
        collected = []
        for url in FEED_URLS:
            try:
                content = _http_get(url)
                parsed = feedparser.parse(content)
                name = parsed.feed.get("title", "Feed")
                for e in parsed.get("entries", []):
                    collected.append(_normalize_entry(name, url, e))
            except Exception:
                continue

        if not collected:
            # last-resort: try ESPN one more time via feedparser direct
            try:
                parsed = feedparser.parse("https://www.espn.com/espn/rss/ncf/news")
                name = parsed.feed.get("title", "ESPN CFB")
                for e in parsed.get("entries", []):
                    collected.append(_normalize_entry(name, "https://www.espn.com/espn/rss/ncf/news", e))
            except Exception:
                pass

        collected = _dedupe(collected)
        collected.sort(key=lambda x: (x.get("_ts", 0), x.get("published", "")), reverse=True)
        ITEMS = collected[:250]
        UPDATED = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        _LAST_FETCH_TS = time.time()
        return {"updated": UPDATED, "count": len(ITEMS)}

def ensure_items_ready():
    """Fetch on first visit or if data is older than 30 minutes."""
    global _LAST_FETCH_TS
    if not ITEMS or (time.time() - _LAST_FETCH_TS) > 1800:
        fetch_now()

# -------------------- Routes --------------------
PAGE_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>South Carolina Gamecocks — Football Feed</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="/static/logo.png">
  <style>
  :root{--garnet:#73000A;--garnet-700:#4f0007;--black:#121212;--bg:#fafafa;--card:#fff;--muted:#666;--border:#e6e6e6;--shadow:0 1px 2px rgba(0,0,0,.06)}
  *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--black);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
  .header{background:linear-gradient(90deg,var(--garnet),var(--garnet-700));color:#fff;padding:14px 16px}
  .brand{display:flex;gap:12px;align-items:center}.logo{width:44px;height:44px;border-radius:10px;background:#fff}
  h1{margin:0;font-size:20px}.sub{opacity:.95;font-size:12px}
  .quick{display:flex;gap:8px;flex-wrap:wrap;padding:10px 12px}
  .pill{display:inline-block;padding:7px 14px;border-radius:999px;background:#fff;color:#000;font-weight:700;border:1px solid var(--border);text-decoration:none;box-shadow:var(--shadow)}
  .pill-primary{background:var(--garnet);color:#fff;border-color:var(--garnet)}
  .pill-primary.on{background:#a30012}
  main{max-width:900px;margin:14px auto;padding:0 12px}
  .card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px 14px;margin:12px 0;box-shadow:var(--shadow)}
  .title{font-size:18px;font-weight:800;text-decoration:none;color:var(--black)}
  .summary{margin:6px 0 0;color:var(--black)}
  .meta{margin-top:8px;color:var(--muted);font-size:13px}
  .empty{padding:28px 12px;text-align:center;color:var(--muted)}
  </style>
</head>
<body>
  <header class="header">
    <div class="brand">
      <img src="/static/logo.png" alt="SC" class="logo">
      <div>
        <h1>South Carolina Gamecocks — Football Feed</h1>
        <div class="sub">Updated: <span id="updated">{{ updated or "—" }}</span></div>
      </div>
    </div>
  </header>

  <audio id="fightAudio" src="/static/fight-song.mp3" preload="auto"></audio>

  <nav class="quick">
    <button id="fightBtn" class="pill pill-primary" aria-pressed="false">Play Fight Song</button>
    <a class="pill" href="https://gamecocksonline.com/sports/football/" target="_blank" rel="noopener">South Carolina — Official</a>
    <a class="pill" href="https://www.espn.com/college-football/team/_/id/2579/south-carolina-gamecocks" target="_blank" rel="noopener">ESPN</a>
    <a class="pill" href="https://www.garnetandblackattack.com/" target="_blank" rel="noopener">Garnet & Black Attack</a>
    <a class="pill" href="https://www.thestate.com/sports/college/university-of-south-carolina/usc-football/" target="_blank" rel="noopener">The State</a>
  </nav>

  <main>
    {% if not items %}
      <div class="empty" id="warming">Warming up the feed…</div>
    {% else %}
      {% for it in items %}
      <article class="card">
        <a class="title" href="{{ it.link }}" target="_blank" rel="noopener">{{ it.title }}</a>
        {% if it.summary %}<p class="summary">{{ it.summary }}</p>{% endif %}
        <div class="meta">{{ it.source }}{% if it.published %} • {{ it.published }}{% endif %}</div>
      </article>
      {% endfor %}
    {% endif %}
  </main>

<script>
(function(){
  const audio = document.getElementById('fightAudio');
  const btn = document.getElementById('fightBtn');
  if (btn && audio){
    const setBtn = (on)=>{ btn.textContent = on ? 'Pause Fight Song' : 'Play Fight Song';
                           btn.classList.toggle('on', on);
                           btn.setAttribute('aria-pressed', on ? 'true':'false'); };
    setBtn(false);
    btn.addEventListener('click', async ()=>{ try{
      if (audio.paused){ await audio.play(); setBtn(true); } else { audio.pause(); setBtn(false); }
    }catch(e){} });
    audio.addEventListener('ended', ()=>setBtn(false));
    audio.addEventListener('pause', ()=>setBtn(false));
    audio.addEventListener('play', ()=>setBtn(true));
  }

  // If feed empty, force a fetch then reload once
  const warming = document.getElementById('warming');
  if (warming){
    fetch('/collect-open').then(r=>r.json()).then(_=>setTimeout(()=>location.reload(), 700)).catch(_=>{});
  }
})();
</script>
</body>
</html>
"""

@app.route("/")
def home():
    ensure_items_ready()
    return render_template_string(PAGE_HTML, items=ITEMS, updated=UPDATED)

@app.route("/items.json")
def items_json():
    ensure_items_ready()
    return jsonify({"updated": UPDATED, "items": ITEMS})

@app.route("/collect-open")
def collect_open():
    out = fetch_now()
    return jsonify({"ok": True, **out})

@app.route("/health")
def health():
    return jsonify({"ok": True, "updated": UPDATED})

# Warm the cache as the process starts (non-blocking)
def _warm_start():
    try:
        fetch_now()
    except Exception:
        pass

threading.Thread(target=_warm_start, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(8080), debug=True)
