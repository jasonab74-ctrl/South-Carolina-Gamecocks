#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
South Carolina Gamecocks — Football Feed
- Auto-collects on first load if items.json is empty (server-side)
- Adds /collect-open (GET, no token) for first-visit bootstrap from the browser
- /collect (POST) still supports optional COLLECT_TOKEN
- /debug-collect to see count/sample quickly
- /fight-song page; audio at static/fight-song.mp3
"""

import os
import json
from datetime import datetime, timezone
from flask import Flask, render_template, send_file, jsonify, request, abort

from feeds import FEEDS, STATIC_LINKS
import collect as collector  # collector.collect() writes items.json

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ITEMS_PATH = os.environ.get("ITEMS_PATH", os.path.join(APP_DIR, "items.json"))
COLLECT_TOKEN = os.environ.get("COLLECT_TOKEN", "")
AUTO_COLLECT_ON_EMPTY = os.environ.get("AUTO_COLLECT_ON_EMPTY", "1") == "1"

app = Flask(__name__, template_folder="templates", static_folder="static")


def _ensure_items_file():
    if not os.path.exists(ITEMS_PATH):
        with open(ITEMS_PATH, "w", encoding="utf-8") as f:
            json.dump({"updated": None, "items": []}, f)


def _load_items():
    _ensure_items_file()
    with open(ITEMS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    data = _load_items()
    # Server-side safety net (best effort)
    if AUTO_COLLECT_ON_EMPTY and not data.get("items"):
        try:
            data = collector.collect(ITEMS_PATH)
        except Exception as e:
            # keep serving the page; client will call /collect-open next
            print("[collect error]", e)
    return render_template(
        "index.html",
        items=data.get("items", []),
        updated=data.get("updated"),
        static_links=STATIC_LINKS,
        feeds=FEEDS,
        team_title="South Carolina Gamecocks — Football Feed",
    )


@app.route("/items.json")
def items_json():
    _ensure_items_file()
    return send_file(ITEMS_PATH, mimetype="application/json", conditional=True)


@app.route("/health")
def health():
    return jsonify({"ok": True, "updated": _load_items().get("updated")})


# ----- Collect endpoints -----

# Open bootstrap for first visit (no token, GET allowed)
@app.route("/collect-open")
def collect_open():
    out = collector.collect(ITEMS_PATH)
    return jsonify({"ok": True, "count": len(out.get("items", [])), "updated": out.get("updated")})

# Protected collect (POST) for CI/cron
@app.route("/collect", methods=["POST"])
def run_collect():
    token = request.headers.get("X-Collect-Token", "")
    if COLLECT_TOKEN and token != COLLECT_TOKEN:
        abort(401, "unauthorized")
    out = collector.collect(ITEMS_PATH)
    return jsonify({"ok": True, "count": len(out.get("items", [])), "updated": out.get("updated")})

# Quick debug (GET)
@app.route("/debug-collect")
def debug_collect():
    t = request.args.get("token", "")
    if COLLECT_TOKEN and t != COLLECT_TOKEN:
        abort(401, "unauthorized")
    out = collector.collect(ITEMS_PATH)
    sample = [it.get("title") for it in out.get("items", [])[:10]]
    return jsonify({"ok": True, "count": len(out.get("items", [])), "sample": sample})


# ----- Fight song -----
@app.route("/fight-song")
def fight_song():
    return render_template("fight_song.html", team_title="South Carolina Gamecocks — Fight Song")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
