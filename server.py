#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Resilient server for Gamecocks feed.
- Never crashes on bad imports/templates.
- Auto-creates/repairs items.json.
- Has open /collect-open (GET) bootstrap + protected /collect (POST).
- Inline fallback HTML if templates fail to render.
"""

import os, json, traceback
from datetime import datetime, timezone
from flask import Flask, render_template, render_template_string, send_file, jsonify, request, abort

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ITEMS_PATH = os.environ.get("ITEMS_PATH", os.path.join(APP_DIR, "items.json"))
COLLECT_TOKEN = os.environ.get("COLLECT_TOKEN", "")
AUTO_COLLECT_ON_EMPTY = os.environ.get("AUTO_COLLECT_ON_EMPTY", "1") == "1"

# --- Safe imports (won't crash app if files have errors) ----------------------
FEEDS = [
    {"name": "Google News — Gamecocks Football", "url": "https://news.google.com/rss/search?q=%22South+Carolina%22+Gamecocks+football&hl=en-US&gl=US&ceid=US:en"},
]
STATIC_LINKS = [{"label": "Fight Song", "url": "/fight-song"}]

try:
    from feeds import FEEDS as _F, STATIC_LINKS as _S
    if isinstance(_F, list) and _F: FEEDS = _F
    if isinstance(_S, list) and _S: STATIC_LINKS = _S
except Exception as e:
    print("[feeds import error]", e)
    traceback.print_exc()

# collector wrapper
def _no_collect(path):
    data = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"), "items": []}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

try:
    import collect as _collector
    def run_collector(path):  # use real collector
        try:
            return _collector.collect(path)
        except Exception as e:
            print("[collector runtime error]", e)
            traceback.print_exc()
            return _no_collect(path)
except Exception as e:
    print("[collect import error]", e)
    traceback.print_exc()
    def run_collector(path):  # safe stub
        return _no_collect(path)

# --- App ----------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")

def _ensure_items_file():
    if not os.path.exists(ITEMS_PATH):
        with open(ITEMS_PATH, "w", encoding="utf-8") as f:
            json.dump({"updated": None, "items": []}, f)

def _load_items():
    _ensure_items_file()
    try:
        with open(ITEMS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # repair corrupted JSON
        with open(ITEMS_PATH, "w", encoding="utf-8") as f:
            json.dump({"updated": None, "items": []}, f)
        return {"updated": None, "items": []}

# --- Routes -------------------------------------------------------------------
@app.route("/")
def index():
    data = _load_items()
    if AUTO_COLLECT_ON_EMPTY and not data.get("items"):
        try:
            data = run_collector(ITEMS_PATH)
        except Exception as e:
            print("[index collect error]", e)

    # Try template first
    try:
        return render_template(
            "index.html",
            items=data.get("items", []),
            updated=data.get("updated"),
            static_links=STATIC_LINKS,
            feeds=FEEDS,
            team_title="South Carolina Gamecocks — Football Feed",
        )
    except Exception as e:
        print("[template index.html error]", e)
        traceback.print_exc()
        # Fallback inline page w/ client bootstrap to /collect-open
        html = """
<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>South Carolina Gamecocks — Football Feed</title>
<link rel="stylesheet" href="/static/style.css">
<header class="header"><div class="brand">
  <img src="/static/logo.png" class="logo" alt="SC">
  <div><h1>South Carolina Gamecocks — Football Feed</h1>
  <div class="sub">Updated: <span id="updated">{{ updated or "—" }}</span></div></div>
</div></header>
<main class="container">
  <div id="warming" class="empty">Warming up the feed…</div>
</main>
<script>
(async function(){
  const el = document.getElementById('warming');
  try{
    el.textContent = 'Fetching articles…';
    const r = await fetch('/collect-open', {cache:'no-store'});
    const j = await r.json();
    if(j && j.ok){ el.textContent = 'Loading…'; setTimeout(()=>location.reload(), 600); }
    else { el.textContent = 'Still warming… tap to retry'; el.onclick = ()=>location.reload(); }
  }catch(e){ el.textContent='Network hiccup. Pull to refresh.'; }
})();
</script>
"""
        return render_template_string(html, updated=data.get("updated"))

@app.route("/items.json")
def items_json():
    _ensure_items_file()
    return send_file(ITEMS_PATH, mimetype="application/json", conditional=True)

@app.route("/health")
def health():
    return jsonify({"ok": True, "updated": _load_items().get("updated")})

# Open bootstrap (GET) – no token
@app.route("/collect-open")
def collect_open():
    out = run_collector(ITEMS_PATH)
    return jsonify({"ok": True, "count": len(out.get("items", [])), "updated": out.get("updated")})

# Protected collect (POST) – token optional
@app.route("/collect", methods=["POST"])
def collect_protected():
    token = request.headers.get("X-Collect-Token", "")
    if COLLECT_TOKEN and token != COLLECT_TOKEN:
        abort(401, "unauthorized")
    out = run_collector(ITEMS_PATH)
    return jsonify({"ok": True, "count": len(out.get("items", [])), "updated": out.get("updated")})

@app.route("/debug-collect")
def debug_collect():
    t = request.args.get("token", "")
    if COLLECT_TOKEN and t != COLLECT_TOKEN:
        abort(401, "unauthorized")
    out = run_collector(ITEMS_PATH)
    sample = [it.get("title") for it in out.get("items", [])[:10]]
    return jsonify({"ok": True, "count": len(out.get("items", [])), "sample": sample})

@app.route("/fight-song")
def fight_song():
    try:
        return render_template("fight_song.html", team_title="South Carolina Gamecocks — Fight Song")
    except Exception as e:
        print("[template fight_song.html error]", e)
        return "<h1>Fight Song</h1><audio controls src='/static/fight-song.mp3'></audio>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
