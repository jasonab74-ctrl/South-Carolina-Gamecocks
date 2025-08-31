#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
from datetime import datetime, timezone
from flask import Flask, render_template, send_file, jsonify, request, abort
from threading import Thread

from feeds import FEEDS, STATIC_LINKS
import collect as collector  # collector.collect(items_path) -> {"updated", "items": [...]}

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ITEMS_PATH = os.environ.get("ITEMS_PATH", os.path.join(APP_DIR, "items.json"))
COLLECT_TOKEN = os.environ.get("COLLECT_TOKEN", "")  # optional

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
    # No synchronous collect here (prevents proxy timeouts / “cycling”)
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

def _collect_in_thread():
    try:
        collector.collect(ITEMS_PATH)
    except Exception as e:
        print("[collect thread error]", e)


@app.route("/collect-now")
def collect_now_public():
    """Public, non-blocking collect (used by homepage JS)."""
    Thread(target=_collect_in_thread, daemon=True).start()
    return jsonify({"ok": True, "started": True})


@app.route("/collect", methods=["POST"])
def collect_protected():
    """Protected (tokened) collect, if you want to hit from CI."""
    token = request.headers.get("X-Collect-Token", "")
    if COLLECT_TOKEN and token != COLLECT_TOKEN:
        abort(401, "unauthorized")
    Thread(target=_collect_in_thread, daemon=True).start()
    return jsonify({"ok": True, "started": True})


# ----- Fight song -----
@app.route("/fight-song")
def fight_song():
    return render_template("fight_song.html", team_title="South Carolina Gamecocks — Fight Song")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
