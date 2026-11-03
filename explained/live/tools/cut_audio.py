"""Cut the voice-loop audio clips listed in ../audio/clips.json.

Downloads each source recording once (from the Apollo Flight Journal / Apollo
Lunar Surface Journal, which publish NASA's public-domain Apollo 11 audio),
takes the [t0, t1] window, adds 30 ms fades, peak-normalises it and writes a
small mono MP3 into ../audio/. The clips are committed, so the viewer's build
and the GitHub Pages workflow never need this script or its dependency.

    pip install av        # PyAV, bundles FFmpeg
    python explained/live/tools/cut_audio.py --cache /some/tmp/dir
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

import av
import numpy as np

AUDIO = Path(__file__).resolve().parent.parent / "audio"
RATE = 22050


def fetch(url: str, cache: Path) -> Path:
    dest = cache / url.rsplit("/", 1)[1]
    if not dest.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (apollo-11-explained cut_audio.py)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            dest.write_bytes(r.read())
    return dest


def decode(path: Path, t0: float, t1: float) -> np.ndarray:
    c = av.open(str(path))
    st = c.streams.audio[0]
    rs = av.AudioResampler(format="flt", layout="mono", rate=RATE)
    c.seek(int(max(0.0, t0 - 2.0) / st.time_base), stream=st)
    chunks, first = [], None
    for fr in c.decode(st):
        ts = float(fr.pts * st.time_base)
        if ts > t1 + 0.5:
            break
        for r in rs.resample(fr):
            if first is None:
                first = ts
            chunks.append(r.to_ndarray().reshape(-1))
    c.close()
    x = np.concatenate(chunks)
    i0, i1 = int((t0 - first) * RATE), int((t1 - first) * RATE)
    return x[max(0, i0):i1].astype(np.float32)


def encode(x: np.ndarray, dest: Path) -> None:
    n = int(0.03 * RATE)
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    x[:n] *= ramp
    x[-n:] *= ramp[::-1]
    peak = float(np.max(np.abs(x))) or 1.0
    x = np.clip(x * (0.89 / peak), -1.0, 1.0)
    out = av.open(str(dest), "w", format="mp3")
    s = out.add_stream("libmp3lame", rate=RATE, layout="mono")
    s.bit_rate = 48_000
    frame_len = 1152
    pcm = x.reshape(1, -1)
    for i in range(0, pcm.shape[1], frame_len):
        fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(pcm[:, i:i + frame_len]), format="flt", layout="mono")
        fr.sample_rate = RATE
        for p in s.encode(fr):
            out.mux(p)
    for p in s.encode(None):
        out.mux(p)
    out.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", required=True, type=Path, help="folder for the downloaded source recordings")
    args = ap.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((AUDIO / "clips.json").read_text(encoding="utf-8"))
    total = 0
    for c in manifest["clips"]:
        src = fetch(c["source"], args.cache)
        x = decode(src, c["t0"], c["t1"])
        encode(x, AUDIO / c["clip"])
        total += (AUDIO / c["clip"]).stat().st_size
        print(f"{c['get']}  {c['t1'] - c['t0']:5.1f} s  -> audio/{c['clip']}")
    print(f"{len(manifest['clips'])} clips, {total / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
