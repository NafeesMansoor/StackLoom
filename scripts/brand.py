"""Write the STACKLOOM logo set (SVG) and render PNG sizes with headless Chrome.

    python scripts/brand.py            # SVGs only
    python scripts/brand.py --png      # also PNGs (needs Google Chrome)

The mark: three staggered layers (the stack) and two threads (the loom). Each
thread breaks where it passes under a layer, so the weave reads in one colour.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "assets" / "logo"
ICONS = ROOT / "assets" / "icons"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

NAVY, BURGUNDY, BONE, ROSE, SKY = "#1b2a44", "#7b2236", "#f5f2ec", "#e09aaa", "#9db8e8"
WORD_FONT = "Inter, 'SF Pro Display', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"

# 32-unit grid. Layers: y, x-start, x-end. Threads: x and their visible segments (gaps where they pass under).
LAYERS = [(10, 10, 26), (16, 6, 26), (22, 6, 22)]
THREADS = [(12.5, [(6, 13.4), (18.6, 26)]),               # over top and bottom, under the middle
           (19.5, [(6, 7.4), (12.6, 19.4), (24.6, 26)])]  # under top and bottom, over the middle


def mark(layer: str, thread: str, transform: str = "") -> str:
    bars = "".join(f"M{x1} {y}H{x2}" for y, x1, x2 in LAYERS)
    threads = "".join(f"M{x} {a}V{b}" for x, segs in THREADS for a, b in segs)
    return (f'<g fill="none" stroke-linecap="round"{f" transform={chr(34)}{transform}{chr(34)}" if transform else ""}>'
            f'<path d="{bars}" stroke="{layer}" stroke-width="3.4"/>'
            f'<path d="{threads}" stroke="{thread}" stroke-width="2.8"/></g>')


def svg(width: float, height: float, body: str, title: str = "STACKLOOM") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-label="{title}"><title>{title}</title>{body}</svg>\n')


def tile(bg: str, layer: str, thread: str, radius: float = 7) -> str:
    return f'<rect width="32" height="32" rx="{radius}" fill="{bg}"/>' + mark(layer, thread)


def lockup(layer: str, thread: str, text: str, bg: str | None = None) -> str:
    back = f'<rect width="208" height="48" fill="{bg}"/>' if bg else ""
    return svg(208, 48, back + mark(layer, thread, "translate(4 4) scale(1.25)") +
               f'<text x="54" y="31.5" font-family="{WORD_FONT}" font-size="20" font-weight="700" letter-spacing="2.4" '
               f'fill="{text}">STACKLOOM</text>')


FILES = {
    "logo/stackloom-symbol.svg": svg(32, 32, mark(NAVY, BURGUNDY)),
    "logo/stackloom-symbol-dark.svg": svg(32, 32, mark("#e7e9ee", ROSE)),
    "logo/stackloom-symbol-mono.svg": svg(32, 32, mark("currentColor", "currentColor")),
    "logo/stackloom-logo-light.svg": lockup(NAVY, BURGUNDY, NAVY),
    "logo/stackloom-logo-dark.svg": lockup("#e7e9ee", ROSE, "#e7e9ee", bg="#14161a"),
    "logo/stackloom-logo-mono.svg": lockup("currentColor", "currentColor", "currentColor"),
    "icons/stackloom-app-icon.svg": svg(32, 32, tile(BURGUNDY, BONE, SKY)),
    "icons/favicon.svg": svg(32, 32, tile(BURGUNDY, BONE, SKY, 7)),
}
PNG_SIZES = {"icons/stackloom-app-icon.svg": [16, 32, 48, 64, 128, 180, 192, 256, 512, 1024],
             "logo/stackloom-symbol.svg": [64, 256, 512], "logo/stackloom-logo-light.svg": [416, 832],
             "logo/stackloom-logo-dark.svg": [416, 832]}


def render(src: Path, width: int, out: Path) -> None:
    w, h = (float(v) for v in src.read_text().split('viewBox="')[1].split('"')[0].split()[2:])
    height = round(width * h / w)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "p.html"
        page.write_text(f'<html><body style="margin:0;background:transparent"><img src="{src.as_uri()}" '
                        f'width="{width}" height="{height}" style="display:block"></body></html>')
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
                        f"--user-data-dir={tmp}/prof", "--default-background-color=00000000",
                        f"--window-size={width},{height}", f"--screenshot={out}", page.as_uri()],
                       check=True, capture_output=True, timeout=60)


def main() -> int:
    for rel, content in FILES.items():
        path = ROOT / "assets" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    shutil.copy(ROOT / "assets/icons/favicon.svg", ROOT / "frontend/public/favicon.svg")
    if "--png" in sys.argv:
        for rel, sizes in PNG_SIZES.items():
            src = ROOT / "assets" / rel
            for size in sizes:
                render(src, size, src.with_name(f"{src.stem}-{size}.png"))
        shutil.copy(ROOT / "assets/icons/stackloom-app-icon-180.png", ROOT / "frontend/public/apple-touch-icon.png")
        shutil.copy(ROOT / "assets/icons/stackloom-app-icon-32.png", ROOT / "frontend/public/favicon-32.png")
    print("wrote", len(FILES), "SVGs" + (" and PNGs" if "--png" in sys.argv else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
