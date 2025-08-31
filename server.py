#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
South Carolina Gamecocks — Football Feed
- Includes /fight-song page
- Will auto-collect once on first request if items.json is empty
"""

import os
import json
from datetime import datetime, timezone
from flask import Flask, render_template, send_file, jsonify, request, abort

from feeds import FEEDS, STATIC_LINKS
import collect as collector  # uses collect.collect() to rebuild items.json

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ITEMS_PATH = os.environ.get("ITEMS_PATH", os.path.join(APP_DIR, "items.json"))
COLLECT_TOKEN = os.environ.get("COLLECT_TOKEN", "")  # optional; if set, require header on /collect
AUTO_COLLECT_ON_EMPTY = os.environ.get("AUTO_COLLECT_ON_EMPTY", "1") == "1"

app = Flask(__name__, template_folder="templates", static_folder="static")


def load_items():
    if not os.path.exists(ITEMS_PATH):
        return {"updated": None, "items": []}
    with open(ITEMS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def index():
    data = load_items()

    # 👇 Safety net: if empty, do a synchronous collect once
    if AUTO_COLLECT_ON_EMPTY and (not data.get("items")):
        try:
            out = collector.collect(ITEMS_PATH)
            data = out
        except Exception:
            pass  # don't 500 the page if a feed hiccups

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


@app.route("/fight-song")
def fight_song():
    return render_template("fight_song.html", team_title="South Carolina Gamecocks — Fight Song")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
