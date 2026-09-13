#!/usr/bin/env python3
"""
Local web server for the Cannabis NB stock finder.

Serves the web/ frontend plus a tiny API:
  GET  /api/data              -> data/catalog.json
  GET  /api/status            -> scraper progress (data/status.json + running flag)
  POST /api/refresh?category=all|<slug>&rebuild=1   -> launch scraper.py

Run:  python3 server.py [port]     (default port 8765)
"""

import json
import os
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")
DATA_DIR = os.path.join(ROOT, "data")
CATALOG_PATH = os.path.join(DATA_DIR, "catalog.json")
STATUS_PATH = os.path.join(DATA_DIR, "status.json")

_proc_lock = threading.Lock()
_scraper_proc = None


def scraper_running():
    with _proc_lock:
        return _scraper_proc is not None and _scraper_proc.poll() is None


def start_scraper(category, rebuild):
    global _scraper_proc
    with _proc_lock:
        if _scraper_proc is not None and _scraper_proc.poll() is None:
            return False
        cmd = [sys.executable, os.path.join(ROOT, "scraper.py"),
               "--category", category]
        if rebuild:
            cmd.append("--rebuild")
        _scraper_proc = subprocess.Popen(cmd, cwd=ROOT)
        return True


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB_DIR, **kw)

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/data":
            if os.path.exists(CATALOG_PATH):
                with open(CATALOG_PATH, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_json({"generated": None, "stores": [],
                                "categories": [], "products": []})
            return
        if path == "/api/status":
            status = {}
            mtime_fresh = False
            if os.path.exists(STATUS_PATH):
                try:
                    with open(STATUS_PATH) as f:
                        status = json.load(f)
                    import time as _t
                    mtime_fresh = _t.time() - os.path.getmtime(STATUS_PATH) < 120
                except (json.JSONDecodeError, OSError):
                    status = {}
            # a scrape launched from the CLI still counts as running while its
            # status file is mid-phase and recently touched
            cli_running = (status.get("phase") not in (None, "done", "error", "idle")
                           and mtime_fresh)
            status["running"] = scraper_running() or cli_running
            self.send_json(status)
            return
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/refresh":
            q = urllib.parse.parse_qs(parsed.query)
            category = q.get("category", ["all"])[0]
            rebuild = q.get("rebuild", ["0"])[0] == "1"
            if start_scraper(category, rebuild):
                self.send_json({"started": True})
            else:
                self.send_json({"started": False,
                                "reason": "refresh already running"}, 409)
            return
        self.send_json({"error": "not found"}, 404)


def main():
    args = [a for a in sys.argv[1:] if a != "--open"]
    auto_open = "--open" in sys.argv[1:]
    port = int(args[0]) if args else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"CNB Stock Finder running at {url}  (Ctrl+C to stop)")
    if auto_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
