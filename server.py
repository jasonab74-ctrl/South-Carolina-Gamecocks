#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
South Carolina Gamecocks — Football Feed (failsafe + tightened + UX polish)
- Single file; in-memory only; same endpoints: /  /items.json  /collect-open  /debug-collect  /health
- Strong SC/Gamecocks football filter (keeps on-topic, drops UNC/Trojans/other sports)
- Quick-links with light garnet tint; Sources dropdown
- Full-width search bar with live dropdown suggestions
- Auto-update every 3 minutes (newest first), with “Refresh” banner
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

FEEDS: List[Dict] = [
    {"name": "Google News — Gamecocks Football", "url": "https://news.google.com/rss/search?q=%22South+Carolina%22+Gamecocks+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google News — South Carolina Football", "url": "https://news.google.com/rss/search?q=%22South+Carolina%22+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google News — Gamecocks", "url": "https://news.google.com/rss/search?q=Gamecocks+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google News — Shane Beamer", "url": "https://news.google.com/rss/search?q=%22Shane+Beamer%22&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Bing News — Gamecocks Football", "url": "https://www.bing.com/news/search?q=South+Carolina+Gamecocks+football&format=rss"},
    {"name": "Bing News — Shane Beamer", "url": "https://www.bing.com/news/search?q=Shane+Beamer&format=rss"},
    {"name": "Garnet & Black Attack (RSS)", "url": "https://www.garnetandblackattack.com/rss/index.xml"},
    {"name": "The State — USC Football (RSS)", "url": "https://www.thestate.com/sports/college/university-of-south-carolina/usc-football/?outputType=amp&type=rss"},
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
        "_txt": f"{title} {summary}".lower(),
    }

# filter: keep SC/Gamecocks football; drop UNC/Trojans/other sports noise
POS_STRONG = [
    "gamecocks", "shane beamer", "williams-brice", "gamecockcentral", "spurs up"
]
POS_SC = ["south carolina", "usc"]  # 'usc' allowed but guarded below
POS_FB = [
    "football", "cfb", "sec", "depth chart", "spring game", "recruit", "commit",
    "transfer portal", "qb", "quarterback", "wide receiver", "defense", "offense",
    "coach", "coaching", "gameday"
]
NEG_UNC = ["north carolina", "tar heels", "unc "]
NEG_TROJANS = ["usc trojans", "lincoln riley", "southern cal", "so cal"]
NEG_OTHER_SPORTS = [
    "women's", "wbb", "basketball", "baseball", "softball", "volleyball",
    "soccer", "track", "golf"
]

def _is_sc_football(txt: str) -> bool:
    txt = txt.lower()
    if any(neg in txt for neg in NEG_OTHER_SPORTS):
        return False
    if "usc" in txt and any(t in txt for t in NEG_TROJANS):
        return False
    if any(neg in txt for neg in NEG_UNC) and ("south carolina" not in txt and "gamecocks" not in txt):
        return False

    if any(p in txt for p in POS_STRONG):
        return True
    if "south carolina" in txt or "gamecocks" in txt:
        return True if any(p in txt for p in POS_FB) else "football" in txt
    if "usc" in txt:  # ambiguous → require football context
        return any(p in txt for p in POS_FB) and not any(t in txt for t in NEG_TROJANS)
    return False

def _dedupe(lst: List[Dict]) -> List[Dict]:
    seen, out = set(), []
    for it in lst:
        k = it["link"] or (it["title"], it["source"])
        if k in seen: continue
        seen.add(k); out.append(it)
    return out

def fetch_now() -> Dict:
    """Fetch all feeds (best-effort) and apply SC football filter. Newest first."""
    global ITEMS, UPDATED, _LAST_FETCH_TS
    with _LOCK:
        raw: List[Dict] = []
        for f in FEEDS:
            url = f["url"]
            try:
                content = _http_get(url)
                parsed = feedparser.parse(content)
                name = parsed.feed.get("title", f["name"])
                for e in parsed.get("entries", []):
                    raw.append(_norm(name, url, e))
            except Exception:
                continue

        if not raw:
            try:
                parsed = feedparser.parse("https://www.espn.com/espn/rss/ncf/news")
                name = parsed.feed.get("title", "ESPN CFB")
                for e in parsed.get("entries", []):
                    raw.append(_norm(name, "https://www.espn.com/espn/rss/ncf/news", e))
            except Exception:
                pass

        kept = [it for it in raw if _is_sc_football(it["_txt"])]
        kept = _dedupe(kept)
        kept.sort(key=lambda x: (x.get("_ts", 0), x.get("published", "")), reverse=True)

        ITEMS = kept[:250]
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
:root{
  --garnet:#73000A; --g700:#4f0007;
  --bg:#fafafa; --card:#fff; --muted:#555; --bd:#e6e6e6; --sh:0 1px 2px rgba(0,0,0,.06);
  --pill-bg:#fff5f6; --pill-bd:#f0ccd1;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111}
.header{background:linear-gradient(90deg,var(--garnet),var(--g700));color:#fff;padding:14px 16px}
.brand{display:flex;gap:12px;align-items:center}
.logo{width:44px;height:44px;border-radius:10px;background:#fff}
h1{margin:0;font-size:20px}
.sub{opacity:.95;font-size:12px}
.quick{display:flex;gap:10px;flex-wrap:wrap;padding:10px 12px}
.pill{display:inline-block;padding:7px 14px;border-radius:999px;background:var(--pill-bg);border:1px solid var(--pill-bd);font-weight:800;text-decoration:none;color:#111;box-shadow:var(--sh)}
.pill-primary{background:var(--garnet);color:#fff;border-color:var(--garnet)}
.pill-primary.on{background:#a30012}
.sbar{padding:0 12px;margin-top:6px}
.sbar input{width:100%; font:600 16px/1.2 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; padding:12px 14px; border-radius:12px; border:1px solid var(--bd); box-shadow:var(--sh)}
.suggest{position:relative}
.suggest ul{position:absolute;z-index:5;left:0;right:0;list-style:none;margin:6px 0 0;padding:6px;background:#fff;border:1px solid var(--bd);border-radius:12px;box-shadow:var(--sh);max-height:280px;overflow:auto}
.suggest li{padding:8px 10px;border-radius:8px;cursor:pointer}
.suggest li:hover{background:#f4f4f4}
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

  <details class="sdropdown">
    <summary class="pill">Sources ▾</summary>
    <div class="menu">
      {% for f in feeds %}
        <a href="{{ f.url }}" target="_blank" rel="noopener">{{ f.name }}</a>
      {% endfor %}
    </div>
  </details>
</nav>

<!-- full-width search bar (own line) -->
<div class="sbar">
  <div class="suggest">
    <input id="search" type="search" placeholder="Search articles (title, summary, source)…">
    <ul id="sugg" hidden></ul>
  </div>
</div>

<main>
  <div id="notice" class="notice">New items available — <button id="applyBtn" class="pill">Refresh</button></div>
  <section id="feed">
    {% if not items %}
      <div class="empty">No articles yet. Try Refresh or use the search.</div>
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

  // Render list helper
  const feedEl = document.getElementById('feed');
  const updatedEl = document.getElementById('updated');
  function render(items, updated){
    updatedEl.textContent = updated || updatedEl.textContent;
    feedEl.innerHTML = (items||[]).map(it => `
      <article class="card">
        <a class="title" href="${it.link}" target="_blank" rel="noopener">${it.title}</a>
        ${it.summary ? `<p class="summary">${it.summary}</p>` : ''}
        <div class="meta">${it.source}${it.published ? ` • ${it.published}` : ''}</div>
      </article>
    `).join('') || '<div class="empty">No articles.</div>';
  }

  // Live auto-update (every 3 minutes)
  let lastUpdated = "{{ updated or '' }}";
  const notice = document.getElementById('notice');
  const applyBtn = document.getElementById('applyBtn');

  async function refresh(expectApply){
    try{
      await fetch('/collect-open', {cache:'no-store'});
      const res = await fetch('/items.json', {cache:'no-store'});
      const j = await res.json();
      if (j.updated && j.updated !== lastUpdated){
        if (expectApply){
          lastUpdated = j.updated;
          render(j.items, j.updated);
          notice.style.display = 'none';
        }else{
          notice.style.display = 'block';
          applyBtn.onclick = ()=>refresh(true);
        }
      }
    }catch(e){}
  }
  setInterval(()=>refresh(false), 180000);

  // Search with dropdown suggestions
  let cacheItems = {{ items|tojson }};
  window.__ARTICLES = cacheItems;
  const q = document.getElementById('search'), sugg = document.getElementById('sugg');
  function filterLocal(term){
    const t = term.trim().toLowerCase();
    if(!t){ sugg.hidden = true; render(cacheItems, null); return; }
    const hits = cacheItems.filter(it =>
      (it.title||'').toLowerCase().includes(t) ||
      (it.summary||'').toLowerCase().includes(t) ||
      (it.source||'').toLowerCase().includes(t)
    );
    // dropdown
    sugg.innerHTML = hits.slice(0,8).map(it=>`<li data-link="${it.link}">${it.title}</li>`).join('') || `<li>No matches</li>`;
    sugg.hidden = false;
    sugg.querySelectorAll('li[data-link]').forEach(li=>{
      li.onclick = ()=>{ window.open(li.dataset.link,'_blank'); };
    });
    // Enter applies filter to the list
    return hits;
  }
  q.addEventListener('input', ()=>filterLocal(q.value));
  q.addEventListener('keydown', (e)=>{
    if(e.key==='Enter'){ e.preventDefault(); render(filterLocal(q.value)||[], null); sugg.hidden = true; }
    if(e.key==='Escape'){ q.value=''; sugg.hidden=true; render(cacheItems,null); }
  });

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

# Warm on boot (non-blocking)
def _warm_start():
    try: fetch_now()
    except Exception: pass

threading.Thread(target=_warm_start, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(8080), debug=True)

