from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "device_canvas" / "index.html").as_uri()


def evaluate_in_page(script, viewport=None):
    viewport = viewport or {"width": 1280, "height": 820}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        page = browser.new_page(viewport=viewport)
        page.goto(HTML, wait_until="load")
        values = page.evaluate(script)
        browser.close()
    return values
