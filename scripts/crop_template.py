"""Cut a battle-text template out of a native-size screenshot.

    python scripts/crop_template.py shot.png 384 972 433 987 menu_fight.png

Arguments are the image, the crop box as x0 y0 x1 y1 (pixels, x1/y1 exclusive) and
the output file; save the result as src/data/templates/<lang>/<name>.png. The
template must hug the word (see the English ones in src/data/templates/) and come
from an UNSCALED capture, since matching is pixel-exact.
"""

from __future__ import annotations

import sys

import cv2


def main() -> None:
    if len(sys.argv) != 7:
        raise SystemExit(__doc__)
    image, x0, y0, x1, y1, out = sys.argv[1:]
    frame = cv2.imread(image, cv2.IMREAD_GRAYSCALE)
    if frame is None:
        raise SystemExit(f"cannot read image: {image!r}")
    crop = frame[int(y0) : int(y1), int(x0) : int(x1)]
    if crop.size == 0:
        raise SystemExit("empty crop box")
    cv2.imwrite(out, crop)
    print(f"wrote {out} ({crop.shape[1]}x{crop.shape[0]} px)")


if __name__ == "__main__":
    main()
