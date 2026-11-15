#!/usr/bin/env python3
"""Rebuild the README images from scripts/preview.html (demo data).

Usage:  pip install playwright && playwright install chromium
        python scripts/screenshots.py
"""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parents[1]
IMAGES = {"en": "card.png", "it": "card-it.png"}


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/scripts/preview.html"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=os.environ.get("BROWSER_CHANNEL"))
        for lang, name in IMAGES.items():
            page = browser.new_page(viewport={"width": 880, "height": 600}, device_scale_factor=2)
            page.goto(f"{url}?lang={lang}")
            page.wait_for_selector("body[data-ready]")
            page.wait_for_timeout(1500)  # bar and colour transitions
            page.locator("body").screenshot(path=str(ROOT / "images" / name))
            print("written", name)
        browser.close()
    server.shutdown()


if __name__ == "__main__":
    main()
