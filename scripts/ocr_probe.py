"""Show what the OCR reads in a screenshot: the enemy name banner, the chat and the
HUD location line -- and how the active language pack parses them.

Use it on a screenshot of a non-English client to find the exact text the readers
must look for (level marker, Alpha prefix, "turn started" line, channel suffix):

    python scripts/ocr_probe.py shot.png --lang fr

Needs a full-window screenshot at the game's native size (no scaling). Prints text
only; nothing is written.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402

import paths  # noqa: E402
from battle_log import parse_turn_number, turn_pattern  # noqa: E402
from battle_reader import load_calibration, read_enemy_bars  # noqa: E402
from dex_tracker import EncounterData  # noqa: E402
from lang import load_lang  # noqa: E402
from location_reader import clean_location  # noqa: E402
from name_reader import (  # noqa: E402
    _level_patterns,  # noqa: E402
    clean_ocr_text,
    parse_level,
    strip_alpha_prefix,
)
from ocr_engine import run_ocr, run_ocr_lines  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image")
    ap.add_argument("--lang", default="en")
    args = ap.parse_args()

    frame = cv2.imread(args.image)
    if frame is None:
        raise SystemExit(f"cannot read image: {args.image!r}")
    h, w = frame.shape[:2]
    cal = load_calibration(paths.CALIBRATION_PATH)
    lang = load_lang(args.lang, paths.DATA_DIR / "lang", paths.userdata_dir())
    print(f"{args.image}  ({w}x{h}, lang={lang.code})\n")

    marker, number = _level_patterns(lang)
    bars = read_enemy_bars(frame, cal)
    print(f"== enemy name banner ({len(bars)} HP bar(s) found)")
    for i, bar in enumerate(bars):
        n = cal.name
        y0, y1, x0, x1 = bar.y + n.dy0, bar.y + n.dy1, bar.x + n.dx0, bar.x + n.dx1
        crop = frame[max(y0, 0) : y1, max(x0, 0) : x1]
        if crop.size == 0:
            continue
        up = cv2.resize(crop, None, fx=n.upscale, fy=n.upscale, interpolation=cv2.INTER_CUBIC)
        raw = " ".join(run_ocr(up))
        alpha, rest = strip_alpha_prefix(raw, (lang.alpha_prefix or "alpha ").lower())
        print(f"  bar {i}: raw={raw!r}")
        print(
            f"         alpha={alpha} name={clean_ocr_text(rest, marker)!r} "
            f"level={parse_level(raw, number)}"
        )

    print("\n== chat")
    c = cal.chat
    x0, x1 = c.crop_x(w)
    chat = frame[int(h * c.top) : int(h * c.bottom), x0:x1]
    up = cv2.resize(chat, None, fx=c.upscale, fy=c.upscale, interpolation=cv2.INTER_CUBIC)
    lines = run_ocr_lines(up)
    for line in lines:
        print(f"  {line!r}")
    print(f"  -> turn number: {parse_turn_number(lines, turn_pattern(lang))}")

    print("\n== HUD location")
    loc = cal.location
    hud = frame[int(h * loc.top) : int(h * loc.bottom), int(w * loc.left) : int(w * loc.right)]
    up = cv2.resize(hud, None, fx=loc.upscale, fy=loc.upscale, interpolation=cv2.INTER_CUBIC)
    texts = run_ocr(up)
    print(f"  raw: {texts!r}")
    name = clean_location(" ".join(texts), lang)
    print(f"  cleaned: {name!r}")
    enc = paths.DATA_DIR / "encounters.json"
    if enc.exists():
        data = EncounterData.load(enc, paths.DATA_DIR / "legendaries.json", lang)
        print(
            f"  dex key: {data.match_location(name)} (regions: "
            f"{sorted(data.regions_for_name(name))})"
        )


if __name__ == "__main__":
    main()
