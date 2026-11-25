"""Browser end-to-end test (Playwright). Start the server first, then run:

    pip install playwright && playwright install chromium
    python tests/e2e/browser_e2e.py

Environment variables (all optional):
    BASE_URL        default http://localhost:8000
    ADMIN_EMAIL     default admin@floodalert.lk
    ADMIN_PASSWORD  default ChangeMe123!   (start the server with FLOODALERT_OFFLINE=1 for stable mock data)
    CHROME_PATH     use an installed Chrome instead of Playwright's Chromium
    E2E_LIBS        folder with node_modules/leaflet + chart.js to serve the CDN scripts offline
"""
import base64, os, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.getenv("BASE_URL", "http://localhost:8000")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@floodalert.lk")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
CHROME = os.getenv("CHROME_PATH")
LIBS = Path(os.environ["E2E_LIBS"]) if os.getenv("E2E_LIBS") else None
SP = Path(tempfile.mkdtemp(prefix="floodalert-e2e-"))
ROUTES = {}
if LIBS:
    ROUTES = {
        "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js": (LIBS / "leaflet/dist/leaflet.js", "application/javascript"),
        "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css": (LIBS / "leaflet/dist/leaflet.css", "text/css"),
        "https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js": (LIBS / "chart.js/dist/chart.umd.js", "application/javascript"),
    }
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
(SP / "pic.png").write_bytes(PNG)

errors, results = [], []
def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""))

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"]) if CHROME else p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, permissions=["geolocation", "clipboard-read", "clipboard-write"],
                        geolocation={"latitude": 7.2906, "longitude": 80.6337})
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" and "tile" not in m.text.lower() and "ERR_" not in m.text else None)

    def route(r):
        url = r.request.url
        if url in ROUTES:
            f, ct = ROUTES[url]; r.fulfill(body=f.read_bytes(), content_type=ct)
        elif "arcgisonline.com" in url:
            r.abort()
        else:
            r.continue_()
    if ROUTES:
        ctx.route("**/*", route)

    page.goto(BASE + "/")
    page.wait_for_function("document.querySelectorAll('#areaPick option').length === 25", timeout=10000)
    check("25 districts in picker", page.locator("#areaPick option").count() == 25)
    check("map circles drawn", page.locator("#map path.leaflet-interactive").count() >= 25)
    check("default language Sinhala", page.locator("#tabs button[data-tab=areas]").inner_text().strip() == "උපකරණ පුවරුව")
    page.wait_for_selector("#detail .metric", timeout=8000)
    check("4 metric tiles", page.locator("#detail .metric").count() == 4)
    check("chart canvas visible", page.locator("#chart").is_visible())
    check("stat tiles sum to 25", sum(int(page.locator(i).inner_text()) for i in ("#tileSafe", "#tileCrit")) + int(page.locator("#tileRisk").inner_text()) == int(page.locator("#tileTotal").inner_text()) == 25)
    check("safe-zone card shows sample zone", page.locator("#zoneBody .zone").count() == 1 and "sample" in page.locator("#zoneBody").inner_text().lower())
    page.screenshot(path=str(SP / "1_home_si.png"))

    page.select_option("#areaPick", label=page.locator("#areaPick option").nth(3).inner_text())
    page.wait_for_timeout(600)
    check("picking a district updates badge", page.locator("#areaBadge").inner_text().strip() != "")
    page.click("#modeSat")
    check("satellite toggle active", page.locator("#modeSat.active").count() == 1)
    page.click("#modeMap")
    page.screenshot(path=str(SP / "2_detail.png"))

    page.select_option("#langSel", "ta")
    check("Tamil UI", page.locator("#tabs button[data-tab=areas]").inner_text().strip() == "முகப்பு")
    page.select_option("#langSel", "en")
    check("English UI", page.locator("#tabs button[data-tab=areas]").inner_text().strip() == "Dashboard")
    check("alert banner has content", page.locator("#bannerTitle").inner_text().strip() != "")

    # report without login -> asks to log in
    page.click("#tabs button[data-tab=report]")
    page.click("#reportForm button[type=submit]")
    page.wait_for_selector("#authDlg[open]")
    check("report requires login (dialog opens)", True)
    page.click("#authSwitch")
    page.fill("#auName", "Kamal Perera"); page.fill("#auEmail", f"kamal{int(time.time())}@test.lk"); page.fill("#auPass", "Password123")
    page.click("#authSubmit")
    page.wait_for_selector("#authDlg:not([open])", state="attached")
    check("registered + logged in", "Kamal" in page.locator("#authBtn").inner_text())
    check("citizen has no admin tab", page.locator("#adminTabBtn").is_hidden())

    page.click("#locBtn")
    page.wait_for_function("document.getElementById('toast').classList.contains('show')")
    page.select_option("#repType", "landslide")
    page.fill("#repDesc", "Road blocked <img src=x onerror=window.__xss=1> by mud")
    page.set_input_files("#repPhoto", str(SP / "pic.png"))
    page.click("#reportForm button[type=submit]")
    page.wait_for_function("document.getElementById('toast').textContent.includes('verification')", timeout=8000)
    check("report submitted", True)
    page.screenshot(path=str(SP / "3_report.png"))

    # subscribe
    page.click("#tabs button[data-tab=settings]")
    page.fill("#subContact", "+94771234567"); page.click("#subForm button[type=submit]")
    page.wait_for_selector("#mySubs .item", timeout=5000)
    check("subscription listed", "+94771234567" in page.locator("#mySubs").inner_text())

    # logout, login as admin, moderate
    page.click("#accountBody [data-act=logout]")
    page.click("#authBtn"); page.wait_for_selector("#authDlg[open]")
    page.fill("#auEmail", ADMIN_EMAIL); page.fill("#auPass", ADMIN_PASSWORD)
    page.click("#authSubmit"); page.wait_for_selector("#authDlg:not([open])", state="attached")
    check("admin tab visible", page.locator("#adminTabBtn").is_visible())
    page.click("#adminTabBtn")
    page.wait_for_selector("#pending .item", timeout=5000)
    txt = page.locator("#pending").inner_text()
    check("pending report visible to admin", "Road blocked" in txt)
    check("XSS payload rendered as text, not executed", page.evaluate("window.__xss") is None and page.locator("#pending img[src=x]").count() == 0)
    check("photo shown", page.locator("#pending img").count() == 1)
    page.screenshot(path=str(SP / "4_admin.png"))
    page.click("#pending [data-do=verify]")
    page.wait_for_function("document.querySelector('#pending').innerText.includes('Nothing waiting')", timeout=5000)
    check("verify moves it out of pending", True)

    page.click("#tabs button[data-tab=admin]"); page.click("#refreshBtn")
    page.wait_for_function("document.getElementById('toast').textContent.includes('refreshed')", timeout=15000)
    check("manual refresh works", True)

    # community feed shows the report the admin just verified
    page.click("#tabs button[data-tab=report]")
    page.wait_for_selector("#feedList .feed", timeout=5000)
    check("verified report appears in community feed", "Road blocked" in page.locator("#feedList").inner_text())
    check("feed XSS payload is text", page.evaluate("window.__xss") is None and page.locator("#feedList img[src=x]").count() == 0)

    # 3-day forecast + compare
    page.click("#tabs button[data-tab=forecast]")
    page.wait_for_selector("#fcDays .fcday", timeout=8000)
    check("forecast shows 3 days for the district", page.locator("#fcDays .fcday").count() == 3)
    page.select_option("#fcB", index=2)
    page.wait_for_function("document.querySelectorAll('#fcDays .fchead').length === 2")
    check("compare shows two districts (6 day rows)", page.locator("#fcDays .fcday").count() == 6)
    check("forecast chart drawn", page.evaluate("!!Chart.getChart('fcChart')"))
    check("top-5 highest risk list", page.locator("#fcTop .item").count() == 5)
    page.screenshot(path=str(SP / "7_forecast.png"))

    # emergency contacts + I'm safe
    page.click("#tabs button[data-tab=safe]")
    check("5 emergency numbers with tel: links", page.locator("#emergList a[href^='tel:']").count() == 5)
    check("117 is listed", page.locator("#emergList a[href='tel:117']").count() == 1)
    page.fill("#safeName", "Kamal"); page.click("#safeCopy")
    page.wait_for_function("document.getElementById('toast').classList.contains('show')")
    clip = page.evaluate("navigator.clipboard.readText()")
    check("I'm safe message copied", "Kamal" in clip and "FloodAlert LK" in clip, clip[:60])
    page.screenshot(path=str(SP / "8_safe_tab.png"))

    page.click("#tabs button[data-tab=alerts]")
    page.wait_for_selector("#alertList .item", timeout=5000)
    check("alerts listed", page.locator("#alertList .item").count() >= 1)

    page.click("#tabs button[data-tab=safe]"); page.click("#findSafeBtn")
    page.wait_for_function("document.querySelector('#safeList .item') && document.querySelector('#safeList').innerText.includes('km')", timeout=8000)
    first = page.locator("#safeList .item").first.inner_text()
    check("nearest safe zone = Kandy (geolocated at Kandy)", "Kandy" in first, first.split("\n")[0])
    check("directions link uses OSM", "openstreetmap.org/directions" in page.locator("#safeList a").first.get_attribute("href"))
    page.screenshot(path=str(SP / "5_safe.png"))

    # mobile layout
    page.set_viewport_size({"width": 390, "height": 800}); page.wait_for_timeout(300)
    check("no horizontal scroll on mobile", page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
    page.screenshot(path=str(SP / "6_mobile.png"))

    # service worker registers
    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_timeout(1500)
    sw = page.evaluate("navigator.serviceWorker.getRegistration().then(r => !!r)")
    check("service worker registered", sw)
    b.close()

print("\nJS errors:", errors or "none")
failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed or errors else 0)
