#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
South Carolina Gamecocks — Football Feed
Adds /fight-song page. Place your MP3 at static/fight-song.mp3
"""

import os
import json
from flask import Flask, render_template, send_file, jsonify, request, abort
from datetime import datetime, timezone

from feeds import FEEDS, STATIC_LINKS
import collect as collector  # uses collect.collect() to rebuild items.json

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ITEMS_PATH = os.environ.get("ITEMS_PATH", os.path.join(APP_DIR, "items.json"))
COLLECT_TOKEN = os.environ.get("COLLECT_TOKEN", "")  # optional; if set, require header on /collect

app = Flask(__name__, template_folder="templates", static_folder="static")


def load_items():
    if not os.path.exists(ITEMS_PATH):
        return {"updated": None, "items": []}
    with open(ITEMS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    data = load_items()
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
    # Always serve a valid JSON file
    if not os.path.exists(ITEMS_PATH):
        with open(ITEMS_PATH, "w", encoding="utf-8") as f:
            json.dump({"updated": None, "items": []}, f)
    return send_file(ITEMS_PATH, mimetype="application/json", conditional=True)


@app.route("/health")
def health():
    return jsonify({"ok": True, "updated": load_items().get("updated")})


@app.route("/collect", methods=["POST"])
def run_collect():
    token = request.headers.get("X-Collect-Token", "")
    if COLLECT_TOKEN and token != COLLECT_TOKEN:
        abort(401, "unauthorized")
    out = collector.collect(ITEMS_PATH)
    return jsonify({"ok": True, "count": len(out.get("items", [])), "updated": out.get("updated")})


# ----- Fight song page (requires templates/fight_song.html) -----
@app.route("/fight-song")
def fight_song():
    # This route never 500s due to a missing MP3 — it just renders the page.
    return render_template("fight_song.html", team_title="South Carolina Gamecocks — Fight Song")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
