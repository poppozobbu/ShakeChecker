"""Build (or refresh) a language pack's name tables from PokeAPI.

Writes src/data/lang/<code>.json with:

- species_names:  National Dex id -> name, from PokeAPI's pokemon_species_names.csv
  (ids above 649 are PokeMMO's extra forms -- Deoxys formes, Rotom... -- and take
  the translated name of the species of the same English name; event monsters with
  no official name keep their English one and are simply left out of the table).
- location_names: encounter-data key -> name, from PokeAPI's location_names.csv.
  These are the names of the MAIN-SERIES GAMES, not necessarily what the PokeMMO
  client prints in its HUD, so treat them as a first draft to verify in game (the
  app logs every HUD name it cannot match to userdata/unmatched_locations.txt).

Hand-written fields (regexes, cave words, templates_subdir, ...) already present
in the file are preserved; only the two name tables and the "_status" notes are
regenerated. A language with no file yet gets the defaults in HAND_DEFAULTS if it
has any, else null/empty fields (= English behaviour until filled in).

Run:  python scripts/build_lang.py fr
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

CSV_BASE = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data"
LANG_DIR = DATA / "lang"

# PokeAPI local_language_id per language code (9 = English).
LANGUAGE_IDS = {"fr": "5", "de": "6", "es": "7", "it": "8"}
EN_ID = "9"
NATIONAL_MAX = 649  # PokeMMO is Gen 1-5; ids above are alternate forms / event monsters

# Fields that need a screenshot of the real client to confirm. Where a tolerant
# provisional value exists it is listed here and flagged in "_status".
HAND_DEFAULTS: dict[str, dict] = {
    "fr": {
        # Banner "Dynavolt Niv. 16"; tolerates the OCR reading the i as l/1, and never
        # splits a longer word (a name starting with "niv...").
        "level_marker": r"\b(?:n[il1][vu]|[li][vu])(?![a-z])",
        "alpha_prefix": None,
        # Chat line "Le tour 3 a commencé !" (the OCR may glue or drop spaces/accents).
        "turn_pattern": r"tour\s*(\d{1,3})\s*a\s*comm",
        # HUD "Route 110 Ch. 3": same suffix as English.
        "channel_suffix": None,
        "cave_keywords": ["grotte", "caverne", "tunnel", "mine", "antre", "chambre", "couronne"],
        "cave_word_groups": [["route", "victoire"]],
        "templates_subdir": "fr",
        # Display labels, keyed by the English label (see src/lang.py). Hand-translated,
        # kept short for the narrow dex panel; edit them in userdata/lang/fr.json.
        "way_names": {
            "Water": "Eau",
            "Dark Grass": "Herbe sombre",
            "Old Rod": "Canne",
            "Good Rod": "Super Canne",
            "Super Rod": "Méga Canne",
            "Rod": "Canne",
            "Headbutt": "Coud'Boule",
            "Honey Tree": "Arbre à miel",
            "Rocks": "Éclate-Roc",
            "Grass Pheno": "Phéno. herbe",
            "Water Pheno": "Phéno. eau",
            "Shadow Pheno": "Phéno. ombre",
            "Dust Pheno": "Phéno. poussière",
            "Fishing Pheno": "Phéno. pêche",
            "Super Rod Pheno": "Phéno. Méga Canne",
        },
        "rarity_names": {
            "Very Common": "Très commun",
            "Common": "Commun",
            "Uncommon": "Peu commun",
            "Rare": "Rare",
            "Very Rare": "Très rare",
            "Lure": "Leurre",
            "Special": "Spécial",
            "Horde": "Horde",
        },
        "period_names": {"Morning": "Matin", "Day": "Jour", "Night": "Nuit"},
        "season_names": {
            "Spring": "Printemps",
            "Summer": "Été",
            "Autumn": "Automne",
            "Winter": "Hiver",
        },
        "region_names": {"Unova": "Unys"},
        "ui": {
            "rate_line": "Taux : {rate}  ·  Tour {turn}",
            "hp_line": "PV : {pct}%",
            # compact: the overlay width is fixed
            "level_tag": "N.{level}",
            "status_slp": "SOM",
            "status_par": "PAR",
            "status_psn": "PSN",
            "status_brn": "BRU",
            "status_frz": "GEL",
            "needed_left": "{n} à capturer",
            "all_caught": "tous capturés ici !",
            "tip_profiles": "Profils : créer / charger / supprimer",
            "tip_balls": "Choisir les balls à afficher",
            "tip_legend": "Légende des couleurs de rareté",
            "profiles": "Profils",
            "delete_profile_tip": "Supprimer le profil « {name} »",
            "new_profile_btn": "+  Nouveau profil…",
            "dex": "Pokédex",
            "show_caught": "Afficher les capturés",
            "tip_show_caught": "Garder les espèces capturées dans la liste, cochées, en bas",
            "delete_profile_title": "Supprimer le profil",
            "delete_profile_q": "Supprimer le profil « {name} » et sa liste de capturés ?",
            "new_profile_title": "Nouveau profil",
            "account_name": "Nom du compte :",
            "rarity_head": "Rareté",
            "show_balls": "Balls affichées",
            "all": "Toutes",
            "none": "Aucune",
            "quit": "Quitter ShakeChecker",
            "tray_running": "v{version} est lancé. Clic droit sur l'icône de la zone de "
            "notification pour quitter.",
        },
    },
}

# Hand-written fields confirmed on real screenshots of the client (1920x1080 window,
# October 2026). Anything else is reported as provisional.
VERIFIED: dict[str, set[str]] = {
    "fr": {"level_marker", "turn_pattern", "channel_suffix", "templates"},
}

# Names PokeAPI lacks that are certain from the other regions' data.
MANUAL_LOCATIONS: dict[str, dict[str, str]] = {
    "fr": {
        "JOHTO_VICTORY_ROAD": "Route Victoire",
        "HOENN_DEWFORD_TOWN": "Village Myokara",  # seen on the HUD (PokeAPI: "Myokara")
    },
}


def fetch_csv(name: str) -> list[dict[str, str]]:
    with urllib.request.urlopen(CSV_BASE + name + ".csv") as resp:  # noqa: S310 (trusted, https)
        text = resp.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def _slug(text: str) -> str:
    folded = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")


def _norm_en(name: str) -> str:
    return name.lower().replace("’", "'").replace(" ", "")


def build_species_names(code: str, species: list[dict]) -> dict[str, str]:
    lang_id = LANGUAGE_IDS[code]
    rows = fetch_csv("pokemon_species_names")
    target = {
        int(r["pokemon_species_id"]): r["name"] for r in rows if r["local_language_id"] == lang_id
    }
    english = {
        int(r["pokemon_species_id"]): r["name"] for r in rows if r["local_language_id"] == EN_ID
    }
    by_english = {
        _norm_en(english[i]): target[i] for i in english if i in target and i <= NATIONAL_MAX
    }
    out: dict[int, str] = {}
    for s in species:
        sid = s["id"]
        if sid <= NATIONAL_MAX and sid in target:
            out[sid] = target[sid]
        elif _norm_en(s["name"]) in by_english:  # extra form of a known species
            out[sid] = by_english[_norm_en(s["name"])]
    return {str(k): out[k] for k in sorted(out)}


def build_ball_names(code: str) -> dict[str, str]:
    """English ball name -> translated name, from PokeAPI's item names (the ball
    identifiers are the slugs of the names in src/data/balls.json)."""
    lang_id = LANGUAGE_IDS[code]
    ids = {r["identifier"]: r["id"] for r in fetch_csv("items")}
    names = {
        r["item_id"]: r["name"]
        for r in fetch_csv("item_names")
        if r["local_language_id"] == lang_id
    }
    balls = json.loads((DATA / "balls.json").read_text("utf-8"))["balls"]
    out: dict[str, str] = {}
    for ball in balls:
        item_id = ids.get(_slug(ball["name"]))
        if item_id and item_id in names:
            out[ball["name"]] = names[item_id]
    return out


def build_location_names(code: str, locations: dict[str, dict]) -> tuple[dict[str, str], list[str]]:
    lang_id = LANGUAGE_IDS[code]
    regions = {r["id"]: r["identifier"] for r in fetch_csv("regions")}
    api_locations = {r["id"]: r for r in fetch_csv("locations")}
    names: dict[str, dict[str, str]] = {}
    for r in fetch_csv("location_names"):
        names.setdefault(r["location_id"], {})[r["local_language_id"]] = r["name"]

    index: dict[tuple[str, str], list[str | None]] = {}
    for lid, loc in api_locations.items():
        region = regions.get(loc["region_id"], "")
        translated = names.get(lid, {}).get(lang_id)
        english = names.get(lid, {}).get(EN_ID)
        if english:
            index.setdefault((region, _slug(english)), []).append(translated)
        index.setdefault((region, loc["identifier"]), []).append(translated)

    found: dict[str, str] = {}
    missing: list[str] = []
    for key, loc in locations.items():
        region = loc["region"].lower()
        slug = _slug(loc["name"])
        candidates = (
            index.get((region, slug))
            or index.get((region, _slug(key.split("_", 1)[1].replace("_", " "))))
            or index.get((region, f"{region}-{slug}"))
            or []
        )
        translated = next((c for c in candidates if c), None)
        if translated:
            found[key] = translated
        else:
            missing.append(key)
    for key, name in MANUAL_LOCATIONS.get(code, {}).items():
        if key in locations:
            found[key] = name
            if key in missing:
                missing.remove(key)
    return {k: found[k] for k in sorted(found)}, sorted(missing)


def _state(code: str, field: str, todo: str) -> str:
    if field in VERIFIED.get(code, set()):
        return "verified on real client screenshots"
    return f"provisional -- {todo}"


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in LANGUAGE_IDS:
        raise SystemExit(f"usage: build_lang.py <{'|'.join(LANGUAGE_IDS)}>")
    code = sys.argv[1]
    species = json.loads((DATA / "species_core.json").read_text("utf-8"))
    locations = json.loads((DATA / "encounters.json").read_text("utf-8"))["locations"]

    path = LANG_DIR / f"{code}.json"
    existing = json.loads(path.read_text("utf-8")) if path.exists() else {}
    kept = {k: v for k, v in existing.items() if not k.startswith("_")}
    hand = {**kept, **HAND_DEFAULTS.get(code, {})}  # the values checked here win

    ball_names = build_ball_names(code)
    species_names = build_species_names(code, species)
    location_names, missing = build_location_names(code, locations)
    untranslated = [s["id"] for s in species if str(s["id"]) not in species_names]

    pack = {
        "_status": {
            "species_names": f"PokeAPI, {len(species_names)}/{len(species)} species; the "
            f"{len(untranslated)} left out are PokeMMO event monsters with no official name",
            "location_names": f"PokeAPI game names, {len(location_names)}/{len(locations)} "
            "locations -- NOT yet checked against the PokeMMO HUD; zones the client shows "
            "differently are listed in userdata/unmatched_locations.txt while playing",
            "location_names_missing": missing,
            "location_names_missing_note": "'Route N' zones need no entry while the HUD "
            "prints them as in English (the English names are indexed too); the others "
            "must be added from the HUD text",
            "level_marker": _state(code, "level_marker", "confirm on a name banner"),
            "alpha_prefix": "the English 'Alpha ' prefix, confirmed by the player on the "
            "PokeMMO French client",
            "turn_pattern": _state(code, "turn_pattern", "confirm with the chat turn line"),
            "channel_suffix": _state(code, "channel_suffix", "confirm on the HUD location line"),
            "ui_strings": "hand-translated (way_names, rarity_names, period_names, "
            "season_names, region_names, ui); the ball names come from PokeAPI. Not "
            "compared with the wording of the PokeMMO client itself",
            "templates": _state(
                code,
                "templates",
                f"src/data/templates/{code}/ must hold the 4 translated templates "
                "(menu_fight, catch_gotcha, action_used, action_go) -- see docs/LANGUAGES.md",
            ),
        },
        **hand,
        "ball_names": ball_names,
        "species_names": species_names,
        "location_names": location_names,
    }
    LANG_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pack, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(
        f"wrote {path}: {len(species_names)} species, {len(location_names)} locations "
        f"({len(missing)} without a name)"
    )


if __name__ == "__main__":
    main()
