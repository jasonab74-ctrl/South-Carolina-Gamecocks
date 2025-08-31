# server.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Flask server for the South Carolina Gamecocks Football feed.
Adds a /fight-song page that plays /static/fight-song.mp3.
Rename your audio file to exactly: static/fight-song.mp3
"""

import os
import json
from datetime import datetime, timezone
from flask import Flask, render_template, send_file, jsonify, request, abort

from feeds import FEEDS, STATIC_LINKS
import collect as collector  # uses collect.collect() to rebuild items.json

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ITEMS_PATH = os.environ.get("ITEMS_PATH", os.path.join(APP_DIR, "items.json"))
COLLECT_TOKEN = os.environ.get("COLLECT_TOKEN", "")  # optional: protects /collect

app = Flask(__name__, template_folder="templates", static_folder="static")


def load_items():
    if not os.path.exists(ITEMS_PATH):
        return {"updated": None, "items": []}
    with open(ITEMS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    data = load_items()
    updated = data.get("updated")
    items = data.get("items", [])
    return render_template(
        "index.html",
        items=items,
        updated=updated,
        static_links=STATIC_LINKS,
        feeds=FEEDS,
        team_title="South Carolina Gamecocks — Football Feed",
    )


@app.route("/items.json")
def items_json():
    # serve the cached items.json (used by auto-refresh in the UI)
    if not os.path.exists(ITEMS_PATH):
        # ensure valid JSON even before first collect
        with open(ITEMS_PATH, "w", encoding="utf-8") as f:
            json.dump({"updated": None, "items": []}, f)
    return send_file(ITEMS_PATH, mimetype="application/json", conditional=True)


@app.route("/health")
def health():
    return jsonify({"ok": True, "updated": load_items().get("updated")})


@app.route("/collect", methods=["POST"])
def run_collect():
    # Optional auth guard
    token = request.headers.get("X-Collect-Token", "")
    if COLLECT_TOKEN and token != COLLECT_TOKEN:
        abort(401, "unauthorized")
    result = collector.collect(ITEMS_PATH)
    return jsonify(
        {"ok": True, "wrote": ITEMS_PATH, "count": len(result.get("items", []))}
    )


# --- Fight Song page (expects audio at static/fight-song.mp3) ---
@app.route("/fight-song")
def fight_song():
    return render_template(
        "fight_song.html",
        team_title="South Carolina Gamecocks — Fight Song",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
