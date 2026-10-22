"""Per-language strings for non-English PokeMMO clients.

English is the built-in default: every reader keeps its English patterns as
module constants and only consults a LangPack for overrides. A pack is a JSON
file (src/data/lang/<code>.json) holding the pieces of the UI that are text:

- species_names:  National Dex id -> display name (matching + overlay)
- location_names: encounter-data key (e.g. KANTO_VIRIDIAN_FOREST) -> HUD name
- level_marker / alpha_prefix / turn_pattern / channel_suffix: regex sources
  for the strings the OCR readers look for (null = keep the English one)
- cave_keywords / cave_word_groups: extra words that mark a cave (Dusk Ball)
- templates_subdir: folder under data/templates/ with the translated
  menu/"Gotcha!"/"used"/"Go!" templates (falls back to the English ones)
- ball_names, way_names, rarity_names, period_names, season_names, region_names:
  display labels for the overlay and the dex panel, keyed by the ENGLISH label
  ("Great Ball", "Very Rare", "Shadow Pheno", "Morning", "Unova"...). The English
  label stays the internal key everywhere (sprite lookup, colours, ranking); a
  table only changes what is drawn.
- ui: the short fixed texts of the overlay and the panel ("Rate: {rate}  ·  Turn
  {turn}", "{n} left"...), keyed by a stable id; {placeholders} are filled in.

A user file at userdata/lang/<code>.json is merged on top, so a wrong name can be
fixed without touching the bundled data. Keys starting with "_" are comments.

Pure: no capture, no global state; paths are passed in.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_LANG = "en"

_LIGATURES = {"œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE", "’": "'", "‘": "'"}


def fold_accents(text: str) -> str:
    """Strip accents and fold ligatures/typographic apostrophes: 'Forêt de Jade' ->
    'Foret de Jade', 'Cœur' -> 'Coeur'. The OCR often drops or garbles accents, so
    names are compared in this folded form. Non-letters such as the Nidoran gender
    signs are left untouched."""
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def fold_lower(text: str) -> str:
    """Accent-folded, lowercase form used as the comparison key for fuzzy matching."""
    return fold_accents(text).lower()


@dataclass(frozen=True)
class LangPack:
    code: str = DEFAULT_LANG
    species_names: dict[int, str] = field(default_factory=dict)
    location_names: dict[str, str] = field(default_factory=dict)
    level_marker: str | None = None
    alpha_prefix: str | None = None
    turn_pattern: str | None = None
    channel_suffix: str | None = None
    cave_keywords: tuple[str, ...] = ()
    cave_word_groups: tuple[tuple[str, ...], ...] = ()
    templates_subdir: str | None = None
    ball_names: dict[str, str] = field(default_factory=dict)
    way_names: dict[str, str] = field(default_factory=dict)
    rarity_names: dict[str, str] = field(default_factory=dict)
    period_names: dict[str, str] = field(default_factory=dict)
    season_names: dict[str, str] = field(default_factory=dict)
    region_names: dict[str, str] = field(default_factory=dict)
    ui: dict[str, str] = field(default_factory=dict)

    @property
    def is_default(self) -> bool:
        return self.code == DEFAULT_LANG

    def species_name(self, species_id: int, default: str) -> str:
        return self.species_names.get(species_id, default)

    def location_name(self, key: str, default: str) -> str:
        return self.location_names.get(key, default)

    # Display labels: the English label in, the translated one out (or itself).
    def ball(self, label: str) -> str:
        return self.ball_names.get(label, label)

    def way(self, label: str) -> str:
        return self.way_names.get(label, label)

    def rarity(self, label: str) -> str:
        return self.rarity_names.get(label, label)

    def period(self, label: str) -> str:
        return self.period_names.get(label, label)

    def season(self, label: str) -> str:
        return self.season_names.get(label, label)

    def region(self, label: str) -> str:
        return self.region_names.get(label, label)

    def text(self, key: str, default: str, **fields: object) -> str:
        """A fixed UI text with its {placeholders} filled. A template in the pack that
        does not format (typo in a user file) falls back to the English default."""
        template = self.ui.get(key, default)
        try:
            return template.format(**fields)
        except (KeyError, IndexError, ValueError):
            return default.format(**fields)


_REGEX_FIELDS = ("level_marker", "turn_pattern", "channel_suffix")
_TABLE_FIELDS = (
    "species_names",
    "location_names",
    "ball_names",
    "way_names",
    "rarity_names",
    "period_names",
    "season_names",
    "region_names",
    "ui",
)


def available_languages(lang_dir: Path | str) -> list[str]:
    """Language codes with a bundled pack, English first."""
    d = Path(lang_dir)
    codes = sorted(p.stem.lower() for p in d.glob("*.json")) if d.is_dir() else []
    return [DEFAULT_LANG] + [c for c in codes if c != DEFAULT_LANG]


def _read_json(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return raw


def _merge(base: dict, override: dict) -> dict:
    """Override scalars/lists, merge the two name tables entry by entry."""
    merged = dict(base)
    for key, value in override.items():
        if key in _TABLE_FIELDS and isinstance(value, dict):
            merged[key] = {**base.get(key, {}), **value}
        else:
            merged[key] = value
    return merged


def _strings(data: dict, name: str) -> dict[str, str]:
    return {str(k): str(v) for k, v in data.get(name, {}).items()}


def _build(code: str, raw: dict) -> LangPack:
    data = {k: v for k, v in raw.items() if not k.startswith("_")}
    for name in _REGEX_FIELDS:
        src = data.get(name)
        if src is not None:
            try:
                re.compile(src)
            except re.error as exc:
                raise ValueError(f"lang {code!r}: bad regex in {name!r}: {exc}") from exc
    return LangPack(
        code=code,
        species_names={int(k): str(v) for k, v in data.get("species_names", {}).items()},
        location_names={str(k): str(v) for k, v in data.get("location_names", {}).items()},
        level_marker=data.get("level_marker"),
        alpha_prefix=data.get("alpha_prefix"),
        turn_pattern=data.get("turn_pattern"),
        channel_suffix=data.get("channel_suffix"),
        cave_keywords=tuple(str(k) for k in data.get("cave_keywords", ())),
        cave_word_groups=tuple(tuple(str(w) for w in g) for g in data.get("cave_word_groups", ())),
        templates_subdir=data.get("templates_subdir"),
        ball_names=_strings(data, "ball_names"),
        way_names=_strings(data, "way_names"),
        rarity_names=_strings(data, "rarity_names"),
        period_names=_strings(data, "period_names"),
        season_names=_strings(data, "season_names"),
        region_names=_strings(data, "region_names"),
        ui=_strings(data, "ui"),
    )


def load_lang(
    code: str | None, lang_dir: Path | str, user_dir: Path | str | None = None
) -> LangPack:
    """The pack for `code` (default English = no overrides). `user_dir` is the
    userdata directory; a lang/<code>.json there is merged on top of the bundled
    pack. Raises ValueError for an unknown language or a malformed file."""
    code = (code or DEFAULT_LANG).strip().lower()
    bundled = Path(lang_dir) / f"{code}.json"
    user = Path(user_dir) / "lang" / f"{code}.json" if user_dir is not None else None
    if not bundled.exists():
        if code == DEFAULT_LANG and (user is None or not user.exists()):
            return LangPack()
        if code != DEFAULT_LANG:
            known = ", ".join(available_languages(lang_dir))
            raise ValueError(f"unknown language {code!r} (available: {known})")
    raw = _read_json(bundled) if bundled.exists() else {}
    if user is not None and user.exists():
        raw = _merge(raw, _read_json(user))
    return _build(code, raw)


def pick_templates_dir(
    base: Path | str, lang: LangPack, required: tuple[str, ...]
) -> tuple[Path, bool]:
    """The template folder for `lang` and whether it is the translated one.

    Uses base/<templates_subdir> only if it holds every required file; otherwise
    returns `base` (the English templates) with False, so a half-translated set
    can never crash the reader."""
    base = Path(base)
    if lang.templates_subdir:
        sub = base / lang.templates_subdir
        if all((sub / name).is_file() for name in required):
            return sub, True
    return base, lang.is_default
