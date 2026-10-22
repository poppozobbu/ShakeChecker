"""Check the battle-text templates of a language against screenshots.

For each screenshot prints the best match score of the four templates (menu word,
catch banner, "used", "Go!") and whether it clears the threshold in
calibration.toml, so you can confirm a translated template set works -- and see
which scores sit near a threshold:

    python scripts/check_templates.py --lang fr shot1.png shot2.png ...

A screenshot that shows the command menu should read menu=yes; one with the catch
banner, catch=yes; and so on. Scores below ~0.7 on a screenshot that DOES show the
word mean the template does not match the client's pixels (wrong crop or scaled
screenshot).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402

import paths  # noqa: E402
from battle_reader import TEMPLATE_NAMES, BattleTextReader, load_calibration  # noqa: E402
from lang import load_lang, pick_templates_dir  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("images", nargs="+")
    ap.add_argument("--lang", default="en")
    args = ap.parse_args()

    cal = load_calibration(paths.CALIBRATION_PATH)
    lang = load_lang(args.lang, paths.DATA_DIR / "lang", paths.userdata_dir())
    folder, translated = pick_templates_dir(paths.DATA_DIR / "templates", lang, TEMPLATE_NAMES)
    print(f"templates: {folder}" + ("" if translated else "  (NOT translated -> English)"))
    reader = BattleTextReader(cal.battle_text, folder)
    bt = cal.battle_text
    for path in args.images:
        frame = cv2.imread(path)
        if frame is None:
            print(f"{path}: cannot read")
            continue
        h, w = frame.shape[:2]
        band = frame[int(h * bt.top) : int(h * bt.bottom), int(w * bt.left) : int(w * bt.right)]
        gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
        scores = {
            "menu": (reader._match(gray, reader._menu_tpl), bt.menu_match_min),
            "catch": (reader._match(gray, reader._catch_tpl), bt.catch_match_min),
            "used": (reader._match(gray, reader._action_tpls[0]), bt.action_match_min),
            "go": (reader._match(gray, reader._action_tpls[1]), bt.action_match_min),
        }
        cells = "  ".join(
            f"{k}={'yes' if s >= t else 'no '} ({s:.2f}/{t:.2f})" for k, (s, t) in scores.items()
        )
        print(f"{Path(path).name}  [{w}x{h}]  {cells}")


if __name__ == "__main__":
    main()
