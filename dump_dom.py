"""
Run this after logging in to dump the iframe HTML so we can find
the exact selectors for round state detection.
"""
from playwright.sync_api import sync_playwright
import time, json

PHONE    = input("Phone: ")
PASSWORD = input("Password: ")

with sync_playwright() as p:
    browser = p.firefox.launch(headless=False)
    page = browser.new_page()
    page.goto("https://odibets.com/aviator")
    page.wait_for_load_state("domcontentloaded")

    page.get_by_role("button", name="Login to play").click()
    page.get_by_role("textbox", name="07xxxxxxxx").fill(PHONE)
    page.get_by_role("textbox", name="• • • • • • • •").fill(PASSWORD)
    page.get_by_role("button", name="Login to Odibets").click()

    page.wait_for_selector("#app iframe", timeout=20000)
    time.sleep(4)  # let game fully load

    frame = page.locator("#app iframe").first.content_frame

    # Dump full HTML
    html = frame.content()
    with open("iframe_dom.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved iframe_dom.html")

    # Also probe key selectors
    probes = [
        # Bet button states
        "button.bet-btn",
        "button[class*='bet']",
        # Round active indicators
        ".fly-animation",
        ".game-field",
        ".multiplier",
        "[class*='multiplier']",
        "[class*='coef']",
        # History
        "[class*='history']",
        # Betting window indicator
        "[class*='waiting']",
        "[class*='place-bet']",
        "[class*='bet-control']",
        ".bet-control",
        # Cashout
        "[class*='cashout']",
        "[class*='cash-out']",
    ]

    results = {}
    for sel in probes:
        try:
            count = frame.locator(sel).count()
            if count > 0:
                first_text = frame.locator(sel).first.inner_text()[:80]
                first_class = frame.locator(sel).first.get_attribute("class") or ""
                results[sel] = {"count": count, "text": first_text, "class": first_class[:120]}
        except Exception as e:
            results[sel] = {"error": str(e)[:60]}

    print(json.dumps(results, indent=2))
    with open("dom_probe.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Saved dom_probe.json")

    input("Press Enter to close...")
    browser.close()
