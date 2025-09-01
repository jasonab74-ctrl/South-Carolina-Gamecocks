#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
South Carolina Gamecocks — Football Feed (failsafe + nice UI)
- Single file; no templates or disk writes (everything in-memory).
- Quick-links row, Sources dropdown, on-page Fight Song.
- Endpoints: /  /items.json  /collect-open  /debug-collect  /health
- Auto-update every 3 minutes (live refresh without page reload).
"""

import time
import threading
from datetime import datetime, timezone
from typing import List, Dict

import requests
import feedparser
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# ---------- config ----------
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HTTP_TIMEOUT = 20

# Feeds (used both for fetching and for the Sources dropdown)
FEEDS: List[Dict] = [
    # Google News
    {"name": "Google News — Gamecocks Football", "url": "https://news.google.com/rss/search?q=%22South+Carolina%22+Gamecocks+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google News — South Carolina Football", "url": "https://news.google.com/rss/search?q=%22South+Carolina%22+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google News — Gamecocks", "url": "https://news.google.com/rss/search?q=Gamecocks+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google News — Shane Beamer", "url": "https://news.google.com/rss/search?q=%22Shane+Beamer%22&hl=en-US&gl=US&ceid=US:en"},
    # Bing News
    {"name": "Bing News — Gamecocks Football", "url": "https://www.bing.com/news/search?q=South+Carolina+Gamecocks+football&format=rss"},
    {"name": "Bing News — Shane Beamer", "url": "https://www.bing.com/news/search?q=Shane+Beamer&format=rss"},
    # Local / Blogs
    {"name": "Garnet & Black Attack (RSS)", "url": "https://www.garnetandblackattack.com/rss/index.xml"},
    {"name": "The State — USC Football (RSS)", "url": "https://www.thestate.com/sports/college/university-of-south-carolina/usc-football/?outputType=amp&type=rss"},
    # National (collector filters by relevance naturally)
    {"name": "ESPN — CFB News", "url": "https://www.espn.com/espn/rss/ncf/news"},
]

# ---------- in-memory store ----------
ITEMS: List[Dict] = []
UPDATED: str | None = None
_LAST_FETCH_TS = 0.0
_LOCK = threading.Lock()

# ---------- helpers ----------
def _http_get(url: str) -> bytes:
    r = requests.get(
        url,
        headers={"User-Agent": USER_AGENT,
                 "Accept": "application/rss+xml,application/xml,*/*;q=0.8"},
        timeout=HTTP_TIMEOUT,
        allow_redirects=True,
    )
    r.raise_for_status()
    return r.content

def _strip_html(s: str) -> str:
    import re
    return re.sub(r"<.*?>", "", s or "")

def _norm(feed_name: str, feed_url: str, e) -> Dict:
    title = (e.get("title") or "").strip()
    link = e.get("link") or e.get("id") or ""
    summary = (e.get("summary") or e.get("description") or "").strip()
    published = e.get("published") or e.get("updated") or ""
    ts = 0
    try:
        if e.get("published_parsed"): ts = time.mktime(e.published_parsed)
        elif e.get("updated_parsed"): ts = time.mktime(e.updated_parsed)
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

def _dedupe(lst: List[Dict]) -> List[Dict]:
    seen, out = set(), []
    for it in lst:
        k = it["link"] or (it["title"], it["source"])
        if k in seen: continue
        seen.add(k); out.append(it)
    return out

def fetch_now() -> Dict:
    """Fetch all feeds (best-effort). Sorted newest first."""
    global ITEMS, UPDATED, _LAST_FETCH_TS
    with _LOCK:
        collected: List[Dict] = []
        for f in FEEDS:
            url = f["url"]
            try:
                content = _http_get(url)
                parsed = feedparser.parse(content)
                name = parsed.feed.get("title", f["name"])
                for e in parsed.get("entries", []):
                    collected.append(_norm(name, url, e))
            except Exception:
                continue

        if not collected:
            # last-resort: try ESPN directly
            try:
                parsed = feedparser.parse("https://www.espn.com/espn/rss/ncf/news")
                name = parsed.feed.get("title", "ESPN CFB")
                for e in parsed.get("entries", []):
                    collected.append(_norm(name, "https://www.espn.com/espn/rss/ncf/news", e))
            except Exception:
                pass

        collected = _dedupe(collected)
        # newest at top: first by parsed timestamp, then by published text
        collected.sort(key=lambda x: (x.get("_ts", 0), x.get("published", "")), reverse=True)
        ITEMS = collected[:250]
        UPDATED = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        _LAST_FETCH_TS = time.time()
        return {"updated": UPDATED, "count": len(ITEMS)}

# ---------- routes ----------
PAGE = """
<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>South Carolina Gamecocks — Football Feed</title>
<link rel="icon" href="/static/logo.png">
<style>
:root{--garnet:#73000A;--g700:#4f0007;--bg:#fafafa;--card:#fff;--muted:#666;--bd:#e6e6e6;--sh:0 1px 2px rgba(0,0,0,.06)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
.header{background:linear-gradient(90deg,var(--garnet),var(--g700));color:#fff;padding:14px 16px}
.brand{display:flex;gap:12px;align-items:center}.logo{width:44px;height:44px;border-radius:10px;background:#fff}
h1{margin:0;font-size:20px}.sub{opacity:.95;font-size:12px}
.quick{display:flex;gap:8px;flex-wrap:wrap;padding:10px 12px}
.pill{display:inline-block;padding:7px 14px;border-radius:999px;background:#fff;border:1px solid var(--bd);font-weight:700;text-decoration:none;color:#000;box-shadow:var(--sh)}
.pill-primary{background:var(--garnet);color:#fff;border-color:var(--garnet)}
.pill-primary.on{background:#a30012}
.sdropdown{position:relative}
.sdropdown summary{list-style:none;cursor:pointer}
.sdropdown[open] .menu{display:block}
.menu{display:none;position:absolute;z-index:10;top:38px;left:0;background:#fff;border:1px solid var(--bd);border-radius:10px;box-shadow:var(--sh);min-width:260px;max-height:260px;overflow:auto;padding:6px}
.menu a{display:block;padding:6px 10px;border-radius:8px;color:#000;text-decoration:none}
.menu a:hover{background:#f3f3f3}
main{max-width:900px;margin:14px auto;padding:0 12px}
.notice{background:#fff3cd;border:1px solid #ffe08a;padding:10px 12px;border-radius:8px;margin-bottom:10px;display:none}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:12px 14px;margin:12px 0;box-shadow:var(--sh)}
.title{font-size:18px;font-weight:800;text-decoration:none;color:#000}
.summary{margin:6px 0 0}
.meta{margin-top:8px;color:var(--muted);font-size:13px}
.empty{padding:28px 12px;text-align:center;color:var(--muted)}
footer{max-width:900px;margin:20px auto 30px;padding:0 12px;color:var(--muted)}
footer a{color:var(--muted);text-decoration:none}
footer a:hover{text-decoration:underline}
</style>
<header class="header"><div class="brand">
  <img src="/static/logo.png" class="logo" alt="SC">
  <div><h1>South Carolina Gamecocks — Football Feed</h1>
  <div class="sub">Updated: <span id="updated">{{ updated or "—" }}</span></div></div>
</div></header>

<audio id="fightAudio" src="/static/fight-song.mp3" preload="auto"></audio>
<nav class="quick">
  <button id="fightBtn" class="pill pill-primary" aria-pressed="false">Play Fight Song</button>
  <a class="pill" href="https://www.espn.com/chalk/" target="_blank" rel="noopener">Betting</a>
  <a class="pill" href="https://gamecocksonline.com/sports/football/" target="_blank" rel="noopener">South Carolina — Official</a>
  <a class="pill" href="https://gamecocksonline.com/sports/football/schedule/" target="_blank" rel="noopener">Schedule</a>
  <a class="pill" href="https://gamecocksonline.com/sports/football/roster/" target="_blank" rel="noopener">Roster</a>
  <a class="pill" href="https://www.espn.com/college-football/team/_/id/2579/south-carolina-gamecocks" target="_blank" rel="noopener">ESPN</a>
  <a class="pill" href="https://www.cbssports.com/college-football/teams/SC/south-carolina-gamecocks/" target="_blank" rel="noopener">CBS Sports</a>
  <a class="pill" href="https://sports.yahoo.com/ncaaf/teams/south-carolina/" target="_blank" rel="noopener">Yahoo Sports</a>
  <a class="pill" href="https://247sports.com/college/south-carolina/" target="_blank" rel="noopener">247Sports</a>
  <a class="pill" href="https://www.on3.com/teams/south-carolina-gamecocks/" target="_blank" rel="noopener">GamecockCentral</a>
  <a class="pill" href="https://www.garnetandblackattack.com/" target="_blank" rel="noopener">Garnet & Black Attack</a>
  <a class="pill" href="https://www.thestate.com/sports/college/university-of-south-carolina/usc-football/" target="_blank" rel="noopener">The State (Columbia)</a>
  <a class="pill" href="https://www.reddit.com/r/Gamecocks/" target="_blank" rel="noopener">Reddit — r/Gamecocks</a>
  <a class="pill" href="https://www.youtube.com/@GamecockCentral" target="_blank" rel="noopener">YouTube — GamecockCentral</a>
  <a class="pill" href="https://www.youtube.com/@247Sports" target="_blank" rel="noopener">YouTube — 247Sports</a>
  <a class="pill" href="https://www.youtube.com/@ESPNCFB" target="_blank" rel="noopener">YouTube — ESPN CFB</a>

  <!-- Sources dropdown -->
  <details class="sdropdown">
    <summary class="pill">Sources ▾</summary>
    <div class="menu">
      {% for f in feeds %}
        <a href="{{ f.url }}" target="_blank" rel="noopener">{{ f.name }}</a>
      {% endfor %}
    </div>
  </details>

  <!-- Utilities -->
  <a class="pill" href="/items.json" target="_blank" rel="noopener">items.json</a>
</nav>

<main>
  <div id="notice" class="notice">New items available — <button id="applyBtn" class="pill">Refresh</button></div>
  <section id="feed">
    {% if not items %}
      <div class="empty">No articles yet. Tap “Refresh” or wait a moment.</div>
    {% else %}
      {% for it in items %}
      <article class="card">
        <a class="title" href="{{ it.link }}" target="_blank" rel="noopener">{{ it.title }}</a>
        {% if it.summary %}<p class="summary">{{ it.summary }}</p>{% endif %}
        <div class="meta">{{ it.source }}{% if it.published %} • {{ it.published }}{% endif %}</div>
      </article>
      {% endfor %}
    {% endif %}
  </section>
</main>

<footer>
  <small>Feeds:
    {% for f in feeds %}
      <a href="{{ f.url }}" target="_blank" rel="noopener">{{ f.name }}</a>{% if not loop.last %} · {% endif %}
    {% endfor %}
  </small>
</footer>

<script>
(function(){
  // Fight song
  const audio = document.getElementById('fightAudio');
  const fbtn = document.getElementById('fightBtn');
  if (audio && fbtn){
    const set = on=>{ fbtn.textContent = on?'Pause Fight Song':'Play Fight Song';
                      fbtn.classList.toggle('on',on);
                      fbtn.setAttribute('aria-pressed', on?'true':'false'); };
    set(false);
    fbtn.onclick = async ()=>{ try{
      if (audio.paused){ await audio.play(); set(true); } else { audio.pause(); set(false); }
    }catch(e){} };
    audio.addEventListener('ended', ()=>set(false));
    audio.addEventListener('pause', ()=>set(false));
    audio.addEventListener('play', ()=>set(true));
  }

  // Live auto-update every 3 minutes (no page reload)
  let lastUpdated = "{{ updated or '' }}";
  const updatedEl = document.getElementById('updated');
  const feedEl = document.getElementById('feed');
  const notice = document.getElementById('notice');
  const applyBtn = document.getElementById('applyBtn');

  async function fetchAndMaybeApply(applyNow){
    try{
      // Ask server to fetch latest
      await fetch('/collect-open', {cache:'no-store'});
      const res = await fetch('/items.json', {cache:'no-store'});
      const j = await res.json();
      if (j.updated && j.updated !== lastUpdated){
        if (applyNow){
          lastUpdated = j.updated;
          updatedEl.textContent = lastUpdated;
          // rebuild list
          feedEl.innerHTML = (j.items||[]).map(it => `
            <article class="card">
              <a class="title" href="${it.link}" target="_blank" rel="noopener">${it.title}</a>
              ${it.summary ? `<p class="summary">${it.summary}</p>` : ''}
              <div class="meta">${it.source}${it.published ? ` • ${it.published}` : ''}</div>
            </article>
          `).join('') || '<div class="empty">No articles.</div>';
          notice.style.display = 'none';
        }else{
          notice.style.display = 'block';
          applyBtn.onclick = ()=>fetchAndMaybeApply(true);
        }
      }
    }catch(e){}
  }

  // poll every 3 minutes; show notice if newer items exist
  setInterval(()=>fetchAndMaybeApply(false), 180000);
})();
</script>
"""

@app.route("/")
def home():
    return render_template_string(PAGE, items=ITEMS, updated=UPDATED, feeds=FEEDS)

@app.route("/items.json")
def items_json():
    return jsonify({"updated": UPDATED, "items": ITEMS})

@app.route("/collect-open")
def collect_open():
    out = fetch_now()
    return jsonify({"ok": True, **out})

@app.route("/debug-collect")
def debug_collect():
    out = fetch_now()
    return jsonify({"ok": True, **out})

@app.route("/health")
def health():
    return jsonify({"ok": True, "updated": UPDATED})

# Warm in background on boot (non-blocking)
def _warm_start():
    try: fetch_now()
    except Exception: pass

threading.Thread(target=_warm_start, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(8080), debug=True)
