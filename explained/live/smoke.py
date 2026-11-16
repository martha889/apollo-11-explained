"""Headless Chrome smoke test for explained/live/apollo11_live.html."""
from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
import tempfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LIVE = Path(__file__).resolve().parent
HTML_PATH = LIVE / "apollo11_live.html"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
MIN_CANVAS_INK = 25


def load_mission_data(html_path: Path) -> dict:
    text = html_path.read_text(encoding="utf-8")
    m = re.search(
        r'<script id="mission-data" type="application/json">(.*?)</script>',
        text,
        re.DOTALL,
    )
    if not m:
        raise RuntimeError(f"mission-data script not found in {html_path}")
    return json.loads(m.group(1).replace("<\\/", "</"))


def load_event_ids(html_path: Path) -> list[str]:
    data = load_mission_data(html_path)
    return [e["id"] for e in data["events"]]


def interp_timemap(tm: list[list[float]], x: float, ix: int, iy: int) -> float:
    if x <= tm[0][ix]:
        return float(tm[0][iy])
    lo, hi = 0, len(tm) - 1
    if x >= tm[hi][ix]:
        return float(tm[hi][iy])
    while hi - lo > 1:
        mid = (lo + hi) >> 1
        if tm[mid][ix] <= x:
            lo = mid
        else:
            hi = mid
    a, b = tm[lo], tm[hi]
    return float(a[iy] + (b[iy] - a[iy]) * (x - a[ix]) / (b[ix] - a[ix]))


def scene_for_play(data: dict, play_s: float) -> str:
    g = interp_timemap(data["timemap"], play_s, 1, 0)
    for ph in data["phases"]:
        if g < ph["get_end"]:
            return f"{ph['scene']} (phase={ph['id']}, GET={g:.1f}s)"
    ph = data["phases"][-1]
    return f"{ph['scene']} (phase={ph['id']}, GET={g:.1f}s)"


def shot_filename(frag: str) -> str:
    if not frag:
        return "default.png"
    if frag.startswith("t="):
        return f"t-{frag[2:]}.png"
    return f"{frag.replace('=', '-').replace(':', '-')}.png"


def verify_png_canvas_not_blank(png_path: Path) -> tuple[bool, str]:
    """Decode PNG using stdlib zlib/struct and verify the left canvas region has non-background ink."""
    if not png_path.is_file():
        return False, "screenshot file missing"
    raw = png_path.read_bytes()
    if len(raw) < 15000 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        return False, f"invalid or tiny PNG ({len(raw)} bytes)"
    pos = 8
    w = h = bit_depth = color_type = 0
    idat = bytearray()
    while pos + 8 <= len(raw):
        length = struct.unpack(">I", raw[pos : pos + 4])[0]
        ctype = raw[pos + 4 : pos + 8]
        chunk_data = raw[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            w, h, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", chunk_data[:13])
        elif ctype == b"IDAT":
            idat.extend(chunk_data)
        elif ctype == b"IEND":
            break
    if w == 0 or h == 0 or bit_depth != 8 or color_type not in (2, 6):
        return True, ""
    bpp = 4 if color_type == 6 else 3
    stride = w * bpp
    try:
        decomp = zlib.decompress(bytes(idat))
    except Exception as exc:
        return False, f"zlib error: {exc}"

    # Reconstruct scanlines (sample every 8th row in the trajectory canvas region: y in 12%..78%, x in 4%..55%)
    # Wait: PNG Paeth/Up/Average filters depend on the previous row, so reconstruct rows up to 78% of height.
    max_y = int(h * 0.78)
    prev = bytearray(stride)
    cur = bytearray(stride)
    # Panel background is #131a26 -> RGB(19, 26, 38)
    br, bg_g, bb = 19, 26, 38
    ink_samples = 0
    total_samples = 0
    x0, x1 = int(w * 0.04), int(w * 0.55)
    y0 = int(h * 0.12)
    pos_d = 0
    for y in range(max_y):
        if pos_d + 1 + stride > len(decomp):
            break
        ftype = decomp[pos_d]
        row = decomp[pos_d + 1 : pos_d + 1 + stride]
        pos_d += 1 + stride
        if ftype == 0:
            cur[:] = row
        elif ftype == 1:
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                cur[i] = (row[i] + a) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                cur[i] = (row[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                b = prev[i]
                cur[i] = (row[i] + ((a + b) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa = abs(p - a)
                pb = abs(p - b)
                pc = abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                cur[i] = (row[i] + pr) & 0xFF
        if y >= y0 and (y - y0) % 6 == 0:
            for x in range(x0, x1, 6):
                idx = x * bpp
                r, g, b_val = cur[idx], cur[idx + 1], cur[idx + 2]
                total_samples += 1
                if abs(r - br) + abs(g - bg_g) + abs(b_val - bb) > 24:
                    ink_samples += 1
        prev, cur = cur, prev

    if total_samples > 0 and ink_samples < 15:
        return False, f"blank canvas in PNG (ink_samples={ink_samples}/{total_samples})"
    return True, ""


def check_dom_target(
    frag: str, file_uri: str, scene_hint: str = ""
) -> tuple[str, bool, str]:
    url = f"{file_uri}#{frag}" if frag else file_uri
    label = frag or "(no-hash)"
    suffix = f" [{scene_hint}]" if scene_hint else ""
    last_reason = "unknown"
    for _attempt in range(3):
        budget = 8000 + _attempt * 3000
        with tempfile.TemporaryDirectory(prefix="apollo11_smoke_") as udir:
            cmd = [
                CHROME,
                "--headless=new",
                "--disable-gpu",
                f"--virtual-time-budget={budget}",
                "--window-size=1440,900",
                f"--user-data-dir={udir}",
                "--dump-dom",
                url,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                last_reason = f"exit {res.returncode}{suffix}"
                continue
            dom = res.stdout
            m_html = re.search(r"<html\b[^>]*>", dom, re.IGNORECASE)
            html_tag = m_html.group(0) if m_html else ""
            if "data-ready=" not in html_tag:
                last_reason = f"missing data-ready{suffix}"
                continue
            if "data-draw-error=" in html_tag:
                return label, False, f"draw error in {html_tag}{suffix}"
            if "data-js-error=" in html_tag:
                return label, False, f"js error in {html_tag}{suffix}"
            m_ink = re.search(r'data-canvas-ink="(\d+)"', html_tag)
            if not m_ink:
                last_reason = f"missing data-canvas-ink{suffix}"
                continue
            ink = int(m_ink.group(1))
            if ink < MIN_CANVAS_INK:
                return label, False, f"blank canvas (data-canvas-ink={ink} < {MIN_CANVAS_INK}){suffix}"
            return label, True, ""
    return label, False, last_reason


def take_screenshot_target(
    frag: str, file_uri: str, shots_dir: Path, scene_hint: str = ""
) -> tuple[str, bool, str]:
    url = f"{file_uri}#{frag}" if frag else file_uri
    label = frag or "(no-hash)"
    suffix = f" [{scene_hint}]" if scene_hint else ""
    shot_path = shots_dir / shot_filename(frag)
    last_reason = "screenshot failed"
    for attempt in range(3):
        budget = 6500 + attempt * 2000
        with tempfile.TemporaryDirectory(prefix="apollo11_shot_") as udir:
            if shot_path.exists():
                shot_path.unlink()
            cmd_shot = [
                CHROME,
                "--headless=new",
                "--disable-gpu",
                f"--virtual-time-budget={budget}",
                "--window-size=1440,900",
                f"--user-data-dir={udir}",
                f"--screenshot={shot_path}",
                url,
            ]
            res = subprocess.run(cmd_shot, capture_output=True, text=True, timeout=60)
            if res.returncode != 0 or not shot_path.is_file():
                last_reason = f"screenshot failed (exit {res.returncode}){suffix}"
                continue
            ok_png, png_reason = verify_png_canvas_not_blank(shot_path)
            if not ok_png:
                last_reason = f"{png_reason}{suffix}"
                continue
            return label, True, ""
    return label, False, last_reason


def fmt_t(val: float) -> str:
    s = f"{val:.3f}".rstrip("0").rstrip(".")
    return s if s else "0"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shots", metavar="DIR", help="save a PNG screenshot per target")
    ap.add_argument("--only", metavar="ID1,ID2", help="comma-separated event IDs to check")
    ap.add_argument("--at", metavar="T1,T2", help="comma-separated playback seconds to check via #t=")
    ap.add_argument("--sweep", metavar="N", type=int, help="test N evenly spaced playback times across TOTAL")
    args = ap.parse_args(argv)

    data = load_mission_data(HTML_PATH)
    all_ids = [e["id"] for e in data["events"]]
    total_play = float(data["timemap"][-1][1])

    targets: list[tuple[str, str]] = []
    if args.sweep is not None:
        n_sweep = max(1, args.sweep)
        for i in range(n_sweep):
            t_val = (total_play * i / (n_sweep - 1)) if n_sweep > 1 else 0.0
            t_str = fmt_t(t_val)
            targets.append((f"t={t_str}", scene_for_play(data, float(t_str))))
    elif args.at:
        for raw_t in args.at.split(","):
            raw_t = raw_t.strip()
            if not raw_t:
                continue
            t_val = float(raw_t)
            targets.append((f"t={raw_t}", scene_for_play(data, t_val)))
    elif args.only:
        for raw_id in args.only.split(","):
            raw_id = raw_id.strip()
            if not raw_id:
                continue
            targets.append((raw_id, ""))
    else:
        targets = [("", "")] + [(eid, "") for eid in all_ids]

    shots_dir = Path(args.shots).resolve() if args.shots else None
    if shots_dir is not None:
        shots_dir.mkdir(parents=True, exist_ok=True)

    file_uri = HTML_PATH.resolve().as_uri()
    with ThreadPoolExecutor(max_workers=3) as ex:
        dom_results = list(
            ex.map(lambda item: check_dom_target(item[0], file_uri, item[1]), targets)
        )

    results = dict((label, (ok, reason)) for label, ok, reason in dom_results)

    if shots_dir is not None:
        shot_targets = [item for item in targets if results.get(item[0] or "(no-hash)", (False, ""))[0]]
        with ThreadPoolExecutor(max_workers=2) as ex:
            shot_results = list(
                ex.map(
                    lambda item: take_screenshot_target(item[0], file_uri, shots_dir, item[1]),
                    shot_targets,
                )
            )
        for label, ok, reason in shot_results:
            if not ok:
                results[label] = (False, reason)

    ordered_results = [
        (frag or "(no-hash)", results[frag or "(no-hash)"][0], results[frag or "(no-hash)"][1])
        for frag, _ in targets
    ]
    failed = [(label, reason) for label, ok, reason in ordered_results if not ok]
    n = len(ordered_results)
    if failed:
        for label, reason in failed:
            print(f"FAIL {label}: {reason}", file=sys.stderr)
        print("SMOKE FAIL: " + ", ".join(label for label, _ in failed))
        return 1

    print(f"SMOKE OK {n}/{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
