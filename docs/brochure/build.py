"""Build DHRUVA-brochure.pdf from docs/brochure/index.html.

    uvx --with playwright==1.58.0 python docs/brochure/build.py --shots --tests 412

--shots retakes every screenshot from the running app (dev server on :5173, the
production preview on :4173 for the offline phone, backend on :8000). Without it
the existing img/ is used. The PDF is printed by headless Chromium, so the Tamil
text and the verdict shapes render exactly as in the app.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
from pathlib import Path

from playwright.async_api import Page, async_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
IMG = HERE / "img"
OUT = ROOT / "DHRUVA-brochure.pdf"
DEV = "http://localhost:5173"
PREVIEW = "http://localhost:4173"
GL = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]


async def ask(page: Page, question: str) -> None:
    await page.get_by_role("button", name="Ask", exact=True).click()
    await page.get_by_text(question).click()
    await page.wait_for_selector("text=Ask about the sea", state="detached", timeout=300_000)
    await page.wait_for_timeout(6000)  # let the voice note settle


async def shots(p) -> str:
    """Returns the alert capsule the terminal sent, for the offline phone."""
    IMG.mkdir(exist_ok=True)
    browser = await p.chromium.launch(args=GL)

    phone = await (await browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)).new_page()
    await phone.goto(f"{DEV}/boat")
    await phone.wait_for_timeout(1000)
    await phone.get_by_role("button", name="Ask", exact=True).click()
    await phone.wait_for_timeout(600)
    await phone.screenshot(path=IMG / "phone_ask.png")
    await phone.get_by_role("button", name="Close").first.click()
    await ask(phone, "மீன் பிடிக்க எங்கே போவது?")
    await phone.screenshot(path=IMG / "phone_answer.png")
    y = await phone.evaluate(
        "() => { const t=[...document.querySelectorAll('section')]"
        ".find(s=>s.textContent.includes('Nearest fishing zone'));"
        " return t.getBoundingClientRect().top + window.scrollY - 12; }"
    )
    await phone.evaluate(f"window.scrollTo(0, {y})")
    await phone.wait_for_timeout(500)
    await phone.screenshot(path=IMG / "phone_evidence.png")
    print("phone", flush=True)

    term = await (await browser.new_context(viewport={"width": 1400, "height": 820}, device_scale_factor=2)).new_page()
    await term.goto(f"{DEV}/emulator")
    await term.wait_for_timeout(800)
    await term.get_by_text("Simulate a cyclone warning").click()
    await term.wait_for_selector("text=The whole answer", timeout=300_000)
    await term.wait_for_timeout(800)
    await term.screenshot(path=IMG / "terminal.jpg")
    capsule = (await term.locator("p.font-mono").inner_text()).strip()
    print("terminal", capsule, flush=True)

    shore = await (await browser.new_context(viewport={"width": 1440, "height": 860}, device_scale_factor=2)).new_page()
    await shore.goto(f"{DEV}/shore")
    await shore.wait_for_timeout(6000)
    await shore.screenshot(path=IMG / "shore_pfz.jpg")
    box = await shore.locator(".maplibregl-canvas").bounding_box()
    assert box
    await shore.mouse.click(box["x"] + box["width"] * 0.555, box["y"] + box["height"] * 0.60)
    await shore.wait_for_selector("text=What the boat will hear", timeout=300_000)
    await shore.wait_for_timeout(1500)
    await shore.screenshot(path=IMG / "shore_check.jpg")
    await shore.get_by_role("tab", name="Warn boats").click()
    await shore.get_by_text("Use the demo cyclone position").click()
    await shore.wait_for_timeout(2500)
    await shore.get_by_text("Work out each boat's message").click()
    await shore.wait_for_selector("text=different message", timeout=900_000)
    await shore.wait_for_timeout(1500)
    await shore.screenshot(path=IMG / "shore_warn.jpg")
    print("shore", flush=True)
    await browser.close()
    return capsule


async def offline_phone(p, capsule: str) -> None:
    """The at-sea scene for real: production build, network cut, the terminal's
    QR fed to the camera, the phone decodes and speaks."""
    qr, y4m = IMG / "_qr.png", IMG / "_qr.y4m"
    subprocess.run(
        ["node", "-e", f"require('{ROOT}/frontend/node_modules/qrcode').toFile('{qr}','{capsule}',{{width:420,margin:4}})"],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(qr), "-vf",
         "scale=640:480:force_original_aspect_ratio=decrease,pad=640:480:(ow-iw)/2:(oh-ih)/2:white,format=yuv420p",
         "-t", "3", "-r", "10", str(y4m)],
        check=True,
    )
    browser = await p.chromium.launch(
        args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
              f"--use-file-for-fake-video-capture={y4m}", "--autoplay-policy=no-user-gesture-required"]
    )
    ctx = await browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                    permissions=["camera", "microphone"], service_workers="allow")
    page = await ctx.new_page()
    await page.goto(f"{PREVIEW}/boat")
    await page.evaluate("navigator.serviceWorker.ready.then(() => true)")
    await page.reload()
    await page.wait_for_timeout(2500)
    await ctx.set_offline(True)
    await page.reload()
    await page.wait_for_timeout(1500)
    await page.get_by_role("button", name="Receive").click()
    await page.wait_for_selector("text=Arrived by satellite message", timeout=30_000)
    await page.wait_for_timeout(2500)
    await page.screenshot(path=IMG / "phone_blocked.png")
    await browser.close()
    qr.unlink(missing_ok=True)
    y4m.unlink(missing_ok=True)
    print("offline phone", flush=True)


async def pdf(p, tests: str, capsule: str | None) -> None:
    browser = await p.chromium.launch()
    page = await browser.new_page()
    query = f"?tests={tests}" + (f"&capsule={capsule}" if capsule else "")
    await page.goto(f"file://{HERE / 'index.html'}{query}")
    await page.wait_for_load_state("networkidle")
    await page.evaluate("document.fonts.ready.then(() => true)")
    await page.pdf(path=str(OUT), format="A4", print_background=True, prefer_css_page_size=True)
    await browser.close()
    print(f"wrote {OUT}", flush=True)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", action="store_true")
    ap.add_argument("--tests", default="412")
    args = ap.parse_args()
    async with async_playwright() as p:
        capsule = None
        if args.shots:
            capsule = await shots(p)
            await offline_phone(p, capsule)
        await pdf(p, args.tests, capsule)


if __name__ == "__main__":
    asyncio.run(main())
