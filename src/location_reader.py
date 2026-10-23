"""Read the location name from the top-left HUD and decide if it is a cave.

The Dusk Ball is boosted in caves (and at night). The vendored locations_index
covers only some regions (no Sinnoh), so cave-ness is decided by the name: a set
of keywords ("cave", "tunnel", "mine", "gate", ...) plus a few keyword-less caves
matched by their distinctive words (Victory Road, Mt. Coronet, Ice Path), which
tolerates OCR noise like "VictoryF Road". This is a heuristic, not a full
location database — see CLAUDE.md milestone 4 for the data-backed version.
"""

from __future__ import annotations

import re

import cv2
import numpy as np

from battle_reader import LocationCalibration
from lang import LangPack, fold_lower
from ocr_engine import run_ocr

# Drops the " Ch. N" channel suffix (and any trailing noise) from the HUD line.
# Same pattern as dex_tracker._CH_SUFFIX (see there); a test keeps them in step.
_CH_SUFFIX = re.compile(
    r"\s*(?:(?<![a-z])ch[.:。,]*\s*[\dolIiEe|]+|ch(?:[.:。,]+\s*[\dolIiEe|]+|\s*\d+))(?![a-z]).*$",
    re.IGNORECASE,
)
_MONEY_TAIL = re.compile(r"\s*[$§].*$")
# The location crop spans from the very top, so a full-window capture (fixtures
# and live alike) picks up the "PokeMMO" window-title text before the HUD name.
_TITLE_PREFIX = re.compile(r"^\s*pokemmo\s*", re.IGNORECASE)

# A location whose name contains any of these is a cave.
_CAVE_KEYWORDS = (
    "cave",
    "cavern",
    "tunnel",
    "mine",
    "gate",
    "grotto",
    "chamber",
    "coronet",  # Mt. Coronet, however "Mt." is OCR'd
)
# Keyword-less caves, matched by ALL their distinctive words (OCR-noise tolerant).
_CAVE_WORD_GROUPS = (
    ("victory", "road"),
    ("ice", "path"),
    ("ravaged", "path"),
    ("fiery", "path"),
    ("stark", "mountain"),
    ("iron", "island"),
)


def clean_location(raw: str, lang: LangPack | None = None) -> str:
    """The location name without the leading 'PokeMMO' title, the ' Ch. N'
    channel suffix, or stray edges."""
    suffix = (
        re.compile(lang.channel_suffix, re.IGNORECASE)
        if lang and lang.channel_suffix
        else _CH_SUFFIX
    )
    s = _MONEY_TAIL.sub("", _TITLE_PREFIX.sub("", raw.strip()))
    return suffix.sub("", s).strip(" .|")


def is_cave_location(name: str, lang: LangPack | None = None) -> bool:
    """True if the location name denotes a cave (Dusk Ball boosted).

    A language pack with its own cave words REPLACES the English lists (English
    substrings misfire in other languages, e.g. "mine" inside French "Cheminée");
    its keywords match at the start of a word, accents and case ignored. Caves with
    no keyword in their name are resolved through the dex tables instead (see
    DexSession.location_is_cave), which works in any language."""
    if lang is not None and (lang.cave_keywords or lang.cave_word_groups):
        f = fold_lower(name)
        if any(re.search(r"\b" + re.escape(fold_lower(k)), f) for k in lang.cave_keywords):
            return True
        return any(all(fold_lower(w) in f for w in group) for group in lang.cave_word_groups)
    n = name.lower()
    if any(k in n for k in _CAVE_KEYWORDS):
        return True
    return any(all(word in n for word in group) for group in _CAVE_WORD_GROUPS)


def read_location(
    frame_bgr: np.ndarray, cal: LocationCalibration, lang: LangPack | None = None
) -> str:
    """OCR the top-left HUD location (cleaned), or '' if not readable."""
    h, w = frame_bgr.shape[:2]
    crop = frame_bgr[int(h * cal.top) : int(h * cal.bottom), int(w * cal.left) : int(w * cal.right)]
    if crop.size == 0:
        return ""
    up = cv2.resize(crop, None, fx=cal.upscale, fy=cal.upscale, interpolation=cv2.INTER_CUBIC)
    texts = run_ocr(up)
    return clean_location(" ".join(texts), lang) if texts else ""


# Matches the HUD clock "HH:MM" (24h), tolerating a '.' for ':' from OCR.
_CLOCK = re.compile(r"\b([01]?\d|2[0-3])\s*[:.]\s*([0-5]\d)\b")


def read_game_clock(frame_bgr: np.ndarray, cal: LocationCalibration) -> int | None:
    """In-game minute-of-day (0..1439) from the top-left HUD clock, or None.

    Reads the displayed game time directly (e.g. "Saturday, 22:41" -> 22*60+41)
    so the Dusk Ball night check uses exactly what the player sees, rather than a
    computed clock. Used as the primary source; callers fall back to the
    deterministic UTC time if this returns None (HUD hidden / unreadable)."""
    h, w = frame_bgr.shape[:2]
    crop = frame_bgr[int(h * cal.top) : int(h * cal.bottom), int(w * cal.left) : int(w * cal.right)]
    if crop.size == 0:
        return None
    up = cv2.resize(crop, None, fx=cal.upscale, fy=cal.upscale, interpolation=cv2.INTER_CUBIC)
    texts = run_ocr(up)
    if not texts:
        return None
    m = _CLOCK.search(" ".join(texts))
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))
