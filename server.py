#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
South Carolina Gamecocks — Football Feed (friendly time labels)
- Single file; in-memory; endpoints: /  /items.json  /collect-open  /debug-collect  /health
- Strong SC/Gamecocks football filter
- Light-garnet pills, compact/clean cards, search with suggestions
- Auto-update every 3 minutes (newest first)
- CHANGE: Human-friendly time labels ("Today • 3:45 PM", "Yesterday • 8:12 AM", "Sep 1 • 10:31 AM")
- ADD-IN: static_ts() cache-buster for static assets (logo, MP3) to avoid stale caching
"""

import time
import threading
from datetime import datetime, timezone, timedelta
from typing import List, Dict
import html as _html
import re
from urllib.parse import urlparse
from email.utils import parsedate_to_datetime

import requests
import feedparser
from flask import Flask, jsonify, render_template_string, url_for

app = Flask(__name__)

# ---------- cache-busting helper ----------
import os

@app.context_processor
def inject_static_ts():
    """Adds static_ts() to Jinja: {{ static_ts('fight-song.mp3') }} -> /static/fight-song.mp3?v=<mtime>"""
    def static_ts(filename: str) -> str:
        path = os.path.join(app.static_folder or "static", filename)
        try:
            ts = int(os.stat(path).st_mtime)
        except Exception:
            ts = 0
        return url_for('static', filename=filename) + (f'?v={ts}' if ts else '')
    return dict(static_ts=static_ts)

# ---------- config ----------
USER_AGENT = ("Mozilla/5.0 (X11, Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HTTP_TIMEOUT = 20

# Expanded feeds
FEEDS: List[Dict] = [
    {"name": "Google News — Gamecocks Football", "url": "https://news.google.com/rss/search?q=%22South+Carolina%22+Gamecocks+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google News — South Carolina Football", "url": "https://news.google.com/rss/search?q=%22South+Carolina%22+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google News — Gamecocks", "url": "https://news.google.com/rss/search?q=Gamecocks+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google News — Shane Beamer", "url": "https://news.google.com/rss/search?q=%22Shane+Beamer%22&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Bing News — Gamecocks Football", "url": "https://www.bing.com/news/search?q=South+Carolina+Gamecocks+football&format=rss"},
    {"name": "Bing News — South Carolina Football", "url": "https://www.bing.com/news/search?q=%22South+Carolina%22+football&format=rss"},
    {"name": "Bing News — Shane Beamer", "url": "https://www.bing.com/news/search?q=Shane+Beamer&format=rss"},

    {"name": "Google — ESPN (SC Football)", "url": "https://news.google.com/rss/search?q=site:espn.com+%22South+Carolina%22+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google — Yahoo Sports (SC Football)", "url": "https://news.google.com/rss/search?q=site:sports.yahoo.com+%22South+Carolina%22+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google — CBS Sports (SC Football)", "url": "https://news.google.com/rss/search?q=site:cbssports.com+%22South+Carolina%22+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google — 247Sports (SC)", "url": "https://news.google.com/rss/search?q=site:247sports.com+%22South+Carolina%22+Gamecocks&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google — On3/GamecockCentral (SC)", "url": "https://news.google.com/rss/search?q=site:on3.com+%22South+Carolina%22+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google — The State (Columbia)", "url": "https://news.google.com/rss/search?q=site:thestate.com+%22South+Carolina%22+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google — Greenville News (SC Football)", "url": "https://news.google.com/rss/search?q=site:greenvilleonline.com+%22South+Carolina%22+football&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Google — Garnet & Black Attack", "url": "https://news.google.com/rss/search?q=site:garnetandblackattack.com+South+Carolina&hl=en-US&gl=US&ceid=US:en"},

    {"name": "Garnet & Black Attack (RSS)", "url": "https://www.garnetandblackattack.com/rss/index.xml"},
    {"name": "The State — USC Football (RSS)", "url": "https://www.thestate.com/sports/college/university-of-south-carolina/usc-football/?outputType=amp&type=rss"},
    {"name": "Reddit — r/Gamecocks (RSS)", "url": "https://www.reddit.com/r/Gamecocks/.rss"},

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
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml,application/xml,*/*;q=0.8"
        },
        timeout=HTTP_TIMEOUT,
        allow_redirects=True,
    )
    r.raise_for_status()
    return r.content

def _clean_text(s: str) -> str:
    s = _html.unescape(s or "")
    s = re.sub(r"<.*?>", "", s)
    s = s.replace("\xa0", " ").strip()
    return s

def _domain_from(link: str) -> str:
    try:
        host = urlparse(link).netloc.lower()
        return re.sub(r"^www\.", "", host)
    except Exception:
        return ""

def _fmt_clock(dt: datetime) -> str:
    h = dt.strftime("%I").lstrip("0") or "0"
    return f"{h}:{dt.strftime('%M')} {dt.strftime('%p')}"

def _nice_when(ts: int, raw: str) -> str:
    """Return 'Today • 3:45 PM', 'Yesterday • 8:12 AM', or 'Sep 1 • 10:31 AM' (UTC-based)."""
    dt = None
    if ts and ts > 0:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    else:
        try:
            dtp = parsedate_to_datetime(raw)
            if dtp is not None:
                dt = dtp.astimezone(timezone.utc) if dtp.tzinfo else dtp.replace(tzinfo=timezone.utc)
        except Exception:
            dt = None
    if not dt:
        return raw or ""
    today = datetime.now(timezone.utc).date()
    d = dt.date()
    if d == today:
        prefix = "Today"
    elif (today - d) == timedelta(days=1):
        prefix = "Yesterday"
    else:
        prefix = dt.strftime("%b ") + str(int(dt.strftime("%d")))  # drop leading zero
    return f"{prefix} • {_fmt_clock(dt)}"

def _norm(feed_name: str, feed_url: str, e) -> Dict:
    title = _clean_text(e.get("title") or "")
    link = e.get("link") or e.get("id") or ""
    summary = _clean_text(e.get("summary") or e.get("description") or "")
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
        "domain": _domain_from(link),
        "title": title,
        "link": link,
        "summary": summary[:400],
        "published": published,
        "when": _nice_when(ts, published),  # <— friendly time
        "_ts": ts,
        "_txt": f"{title} {summary}".lower(),
    }

# filter: SC/Gamecocks football only
POS_STRONG = ["gamecocks", "shane beamer", "williams-brice", "gamecockcentral", "spurs up"]
POS_FB = ["football","cfb","sec","depth chart","spring game","recruit","commit",
          "transfer portal","qb","quarterback","wide receiver","defense","offense","coach","coaching","gameday"]
NEG_UNC = ["north carolina","tar heels","unc "]
NEG_TROJANS = ["usc trojans","lincoln riley","southern cal","so cal"]
NEG_OTHER_SPORTS = ["women's","wbb","basketball","baseball","softball","volleyball","soccer","track","golf"]

def _is_sc_football(txt: str) -> bool:
    if any(n in txt for n in NEG_OTHER_SPORTS): return False
    if "usc" in txt and any(t in txt for t in NEG_TROJANS): return False
    if any(n in txt for n in NEG_UNC) and ("south carolina" not in txt and "gamecocks" not in txt): return False
    if any(p in txt for p in POS_STRONG): return True
    if "south carolina" in txt or "gamecocks" in txt: return (any(p in txt for p in POS_FB) or "football" in txt)
    if "usc" in txt: return any(p in txt for p in POS_FB) and not any(t in txt for t in NEG_TROJANS)
    return False

def _dedupe(lst: List[Dict]) -> List[Dict]:
    seen, out = set(), []
    for it in lst:
        k = it["link"] or (it["title"], it["source"])
        if k in seen: continue
        seen.add(k); out.append(it)
    return out

def fetch_now() -> Dict:
    global ITEMS, UPDATED, _LAST_FETCH_TS
    with _LOCK:
        raw: List[Dict] = []
        for f in FEEDS:
            try:
                content = _http_get(f["url"])
                parsed = feedparser.parse(content)
                name = parsed.feed.get("title", f["name"])
                for e in parsed.get("entries", []):
                    raw.append(_norm(name, f["url"], e))
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

        kept = _dedupe([it for it in raw if _is_sc_football(it["_txt"])])
        kept.sort(key=lambda x: (x.get("_ts", 0), x.get("published", "")), reverse=True)
        ITEMS = kept[:250]
        UPDATED = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        _LAST_FETCH_TS = time.time()
        return {"updated": UPDATED, "count": len(ITEMS)}

# ---------- page ----------
PAGE = """
<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>South Carolina Gamecocks — Football Feed</title>
<link rel="icon" href="{{ static_ts('logo.png') }}">
<style>
:root{
  --garnet:#73000A; --g700:#4f0007;
  --bg:#fafafa; --card:#fff; --muted:#555; --bd:#eaeaea; --shadow:0 10px 20px rgba(0,0,0,.06);
  --pill-bg:#ffe9ed; --pill-bd:#f3c6cf; --pill-bg-hover:#ffe2e7;
  --accent:#c48a92;
}
*{box-sizing:border-box} body{margin:0;background:var(--bg);font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111}
.header{background:linear-gradient(90deg,var(--garnet),var(--g700));color:#fff;padding:14px 16px}
.brand{display:flex;gap:12px;align-items:center}.logo{width:44px;height:44px;border-radius:10px;background:#fff}
h1{margin:0;font-size:20px}.sub{opacity:.95;font-size:12px}

.quick{display:flex;gap:10px;flex-wrap:wrap;padding:10px 12px}
.pill{display:inline-block;padding:7px 14px;border-radius:999px;background:var(--pill-bg);border:1px solid var(--pill-bd);font-weight:800;text-decoration:none;color:#111;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.pill:hover{background:var(--pill-bg-hover)}
.pill-primary{background:var(--garnet);color:#fff;border-color:var(--garnet)}
.pill-primary.on{background:#a30012}

.sbar{padding:0 12px;margin-top:6px}
.sbar input{width:100%;font:600 16px/1.25 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;padding:12px 14px;border-radius:12px;border:1px solid var(--bd);box-shadow:0 1px 2px rgba(0,0,0,.04);background:#fff}

.suggest{position:relative}
.suggest ul{position:absolute;z-index:5;left:0;right:0;list-style:none;margin:6px 0 0;padding:6px;background:#fff;border:1px solid var(--bd);border-radius:12px;box-shadow:0 8px 20px rgba(0,0,0,.08);max-height:280px;overflow:auto}
.suggest li{padding:8px 10px;border-radius:8px;cursor:pointer}
.suggest li:hover{background:#f4f4f4}

.sdropdown{position:relative}
.sdropdown summary{list-style:none;cursor:pointer}
.sdropdown[open] .menu{display:block}
.menu{display:none;position:absolute;z-index:10;top:38px;left:0;background:#fff;border:1px solid var(--bd);border-radius:10px;box-shadow:0 8px 20px rgba(0,0,0,.08);min-width:260px;max-height:260px;overflow:auto;padding:6px}
.menu a{display:block;padding:6px 10px;border-radius:8px;color:#000;text-decoration:none}
.menu a:hover{background:#f3f3f3}

main{max-width:900px;margin:14px auto;padding:0 12px}
.notice{background:#fff3cd;border:1px solid #ffe08a;padding:10px 12px;border-radius:10px;margin-bottom:10px;display:none}

.card{
  background:var(--card); border:1px solid var(--bd); border-radius:14px;
  padding:12px; margin:10px 0; box-shadow:var(--shadow);
  position:relative; overflow:hidden;
}
.card::before{content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
  background:linear-gradient(var(--garnet),var(--g700)); opacity:.85;}
.title{font-size:17px; font-weight:900; line-height:1.25; color:#100; text-decoration:none; margin:0}
.summary{margin:6px 0 0; color:#202; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden}
.meta{margin-top:10px; color:var(--muted); font-size:13px; display:flex; align-items:center; gap:8px; flex-wrap:wrap}
.chip{background:#fff; border:1px solid var(--accent); color:#333; padding:2px 8px; border-radius:999px; font-weight:700; font-size:12px; white-space:nowrap}
.time{white-space:nowrap; opacity:.9}

.empty{padding:28px 12px;text-align:center;color:var(--muted)}
footer{max-width:900px;margin:20px auto 30px;padding:0 12px;color:var(--muted)}
footer a{color:var(--muted);text-decoration:none}
footer a:hover{text-decoration:underline}
</style>

<header class="header"><div class="brand">
  <img src="{{ static_ts('logo.png') }}" class="logo" alt="SC">
  <div><h1>South Carolina Gamecocks — Football Feed</h1>
  <div class="sub">Updated: <span id="updated">{{ updated or "—" }}</span></div></div>
</div></header>

<audio id="fightAudio" src="{{ static_ts('fight-song.mp3') }}" preload="none" playsinline></audio>

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

<div class="sbar">
  <div class="suggest">
    <input id="search" type="search" placeholder="Search articles (title, summary, source)…" autocomplete="off">
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
        <div class="meta">
          <span class="chip">{{ it.domain or it.source }}</span>
          {% if it.when %}<time class="time">{{ it.when }}</time>{% endif %}
        </div>
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
        if (audio.paused){ await audio.play(); set(true); }
        else { audio.pause(); set(false); }
      }catch(e){
        console.error('Audio play error:', e);
        alert('Could not play audio: ' + (e?.message || e));
      }
    };
    audio.addEventListener('ended', ()=>set(false));
    audio.addEventListener('pause', ()=>set(false));
    audio.addEventListener('play', ()=>set(true));
  }

  const feedEl = document.getElementById('feed');
  const updatedEl = document.getElementById('updated');
  function domainFrom(u){ try{ return new URL(u).hostname.replace(/^www\\./,''); }catch(e){ return ''; } }

  function render(items, updated){
    updatedEl.textContent = updated || updatedEl.textContent;
    feedEl.innerHTML = (items||[]).map(it => `
      <article class="card">
        <a class="title" href="${it.link}" target="_blank" rel="noopener">${it.title}</a>
        ${it.summary ? `<p class="summary">${it.summary}</p>` : ''}
        <div class="meta">
          <span class="chip">${it.domain || domainFrom(it.link) || it.source || 'Source'}</span>
          ${it.when ? `<time class="time">${it.when}</time>` : ''}
        </div>
      </article>
    `).join('') || '<div class="empty">No articles.</div>';
  }

  // Auto-update every 3 minutes
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

  // Search with suggestions
  let cacheItems = {{ items|tojson }};
  const q = document.getElementById('search'), sugg = document.getElementById('sugg');
  function filterLocal(term){
    const t = term.trim().toLowerCase();
    if(!t){ sugg.hidden = true; render(cacheItems, null); return []; }
    const hits = cacheItems.filter(it =>
      (it.title||'').toLowerCase().includes(t) ||
      (it.summary||'').toLowerCase().includes(t) ||
      (it.source||'').toLowerCase().includes(t) ||
      (it.link||'').toLowerCase().includes(t)
    );
    sugg.innerHTML = hits.slice(0,8).map(it=>`<li data-link="${it.link}">${it.title}</li>`).join('') || `<li>No matches</li>`;
    sugg.hidden = false;
    sugg.querySelectorAll('li[data-link]').forEach(li=>{ li.onclick = ()=>window.open(li.dataset.link,'_blank'); });
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

def _warm_start():
    try: fetch_now()
    except Exception: pass

threading.Thread(target=_warm_start, daemon=True).start()

if __name__ == "__main__":
    # 0.0.0.0 + fixed port for Render/Railway/Fly; change as needed
    app.run(host="0.0.0.0", port=int(8080), debug=True)
