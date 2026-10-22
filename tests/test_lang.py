"""Language packs: loading/merging, accent-insensitive matching, the French pack's
name tables wired through the readers, and real captures of the French client."""

from __future__ import annotations

import json
import re
from pathlib import Path

import cv2
import pytest

import dex_tracker
import location_reader
from account_store import CaughtStore
from battle_log import parse_turn_number, read_turn_number, turn_pattern
from battle_reader import TEMPLATE_NAMES, BattleTextReader, load_calibration, read_enemy_bars
from dex_session import DexSession
from dex_tracker import EncounterData, location_entries
from lang import (
    DEFAULT_LANG,
    LangPack,
    available_languages,
    fold_accents,
    fold_lower,
    load_lang,
    pick_templates_dir,
)
from location_reader import clean_location, is_cave_location, read_location
from name_reader import (
    NameReader,
    clean_ocr_text,
    match_species_name,
    parse_level,
    strip_alpha_prefix,
)

ROOT = Path(__file__).parent.parent
DATA = ROOT / "src" / "data"
LANG_DIR = DATA / "lang"
SPECIES = json.loads((DATA / "species_core.json").read_text("utf-8"))
CAL = load_calibration(ROOT / "calibration.toml")
FIXTURES = ROOT / "fixtures" / "fr"  # real French-client captures, masked outside the read zones


@pytest.fixture(scope="module")
def fr() -> LangPack:
    return load_lang("fr", LANG_DIR)


@pytest.fixture(scope="module")
def fr_data(fr: LangPack) -> EncounterData:
    return EncounterData.load(DATA / "encounters.json", DATA / "legendaries.json", fr)


# --- accent folding ---------------------------------------------------------


def test_fold_accents_and_ligatures():
    assert fold_accents("Forêt de Jade") == "Foret de Jade"
    assert fold_accents("Cœur") == "Coeur"
    assert fold_accents("Farfetch’d") == "Farfetch'd"
    assert fold_lower("ÉCLAIR") == "eclair"


def test_fold_keeps_the_nidoran_gender_signs():
    assert fold_accents("Nidoran♀") == "Nidoran♀"
    assert fold_accents("Nidoran♂") == "Nidoran♂"


# --- loading ----------------------------------------------------------------


def test_english_is_the_default_without_a_file(tmp_path: Path):
    pack = load_lang(None, tmp_path)
    assert pack.code == DEFAULT_LANG and pack.is_default
    assert pack.species_name(1, "Bulbasaur") == "Bulbasaur"


def test_available_languages_lists_english_first():
    langs = available_languages(LANG_DIR)
    assert langs[0] == "en" and "fr" in langs


def test_unknown_language_is_a_clear_error():
    with pytest.raises(ValueError, match="unknown language 'xx'"):
        load_lang("xx", LANG_DIR)


def test_bad_regex_is_rejected(tmp_path: Path):
    (tmp_path / "xx.json").write_text(json.dumps({"turn_pattern": "(unclosed"}), "utf-8")
    with pytest.raises(ValueError, match="bad regex in 'turn_pattern'"):
        load_lang("xx", tmp_path)


def test_user_file_is_merged_over_the_bundled_pack(tmp_path: Path):
    user = tmp_path / "userdata"
    (user / "lang").mkdir(parents=True)
    (user / "lang" / "fr.json").write_text(
        json.dumps(
            {
                "location_names": {"KANTO_VIRIDIAN_FOREST": "Forêt Verte"},
                "alpha_prefix": "alpha ",
                "_comment": "ignored",
            }
        ),
        "utf-8",
    )
    pack = load_lang("fr", LANG_DIR, user)
    assert pack.location_names["KANTO_VIRIDIAN_FOREST"] == "Forêt Verte"
    assert pack.location_names["KANTO_ROCK_TUNNEL"]  # bundled entries survive
    assert pack.alpha_prefix == "alpha "
    assert pack.species_names[1] == "Bulbizarre"


# --- the bundled French pack ------------------------------------------------


def test_french_pack_covers_the_national_dex(fr: LangPack):
    assert all(i in fr.species_names for i in range(1, 650))
    assert fr.species_names[1] == "Bulbizarre"
    assert fr.species_names[122] == "M. Mime"
    assert fr.species_names[29] == "Nidoran♀" and fr.species_names[32] == "Nidoran♂"


def test_french_location_names_are_unique_within_a_region(fr: LangPack):
    """Two zones sharing a name inside one region would make the match ambiguous
    (None), so the table must never contain such a pair."""
    locations = json.loads((DATA / "encounters.json").read_text("utf-8"))["locations"]
    seen: dict[tuple[str, str], str] = {}
    for key, name in fr.location_names.items():
        slot = (locations[key]["region"], fold_lower(name))
        assert slot not in seen, f"{key} and {seen[slot]} are both {name!r}"
        seen[slot] = key


def test_french_location_keys_exist_in_the_data(fr: LangPack):
    locations = json.loads((DATA / "encounters.json").read_text("utf-8"))["locations"]
    assert set(fr.location_names) <= set(locations)


@pytest.mark.parametrize(
    ("ocr", "expected"),
    [
        ("Medhyena Niv. 14", "Medhyèna"),  # accent lost by the OCR (seen on a real capture)
        ("Dynavolt Niv. 16 4 0", "Dynavolt"),  # gender/ball icons read as noise
        ("Salameche Niv.12", "Salamèche"),
        ("BULBIZARRE Lv. 5", "Bulbizarre"),  # English marker still accepted
        ("Metamorph Nlv.20", "Métamorph"),  # i read as l
        ("Canarticho Niv.7", "Canarticho"),  # not "Farfetch'd"
        ("M. Mime Niv3", "M. Mime"),
    ],
)
def test_french_species_names_match_through_ocr_noise(fr: LangPack, ocr: str, expected: str):
    names = [fr.species_name(s["id"], s["name"]) for s in SPECIES]
    marker = re.compile(fr.level_marker or "", re.IGNORECASE)
    assert match_species_name(ocr, names, 80, marker) == expected


def test_accent_folding_also_helps_english_names():
    names = [s["name"] for s in SPECIES]
    assert match_species_name("Onix Lv. 9", names, 80) == "Onix"


def test_french_level_marker_does_not_cut_names_short(fr: LangPack):
    marker = re.compile(fr.level_marker or "", re.IGNORECASE)
    # Names starting with N / Ni... must survive intact...
    assert clean_ocr_text("Nidorino Niv.30", marker) == "Nidorino"
    assert clean_ocr_text("Noadkoko Niv. 12", marker) == "Noadkoko"
    # ...and the level is still read after the marker.
    number = re.compile((fr.level_marker or "") + r"\.?\s*(\d{1,3})", re.IGNORECASE)
    assert parse_level("Nidorino Niv.30", number) == 30


def test_alpha_prefix_is_configurable():
    assert strip_alpha_prefix("Alpha Noctowl") == (True, "Noctowl")
    assert strip_alpha_prefix("Alfa Hibou", "alfa ") == (True, "Hibou")


def test_french_turn_pattern(fr: LangPack):
    pattern = turn_pattern(fr)
    assert parse_turn_number(["[Combat] Le tour 3 a commencé !"], pattern) == 3
    assert parse_turn_number(["[Combat] Letour12acommence!"], pattern) == 12  # glued by the OCR
    assert parse_turn_number(["[Combat] Flobio utilise Seisme!", "Normal"], pattern) is None


def test_turn_pattern_defaults_to_english():
    assert turn_pattern(None) is turn_pattern(LangPack())
    assert parse_turn_number(["Turn 4 started!"], turn_pattern(None)) == 4


# --- HUD location -> dex ----------------------------------------------------


def test_channel_suffix_is_the_english_one(fr: LangPack):
    assert fr.channel_suffix is None  # the French HUD prints "Ch. 3" too
    assert clean_location("PokeMMO Route 110 Ch. 3", fr) == "Route 110"
    assert clean_location("PokeMMO Forêt de Jade Ch. 2", fr) == "Forêt de Jade"
    custom = LangPack(channel_suffix=r"\s*canal\s*\d+.*$")
    assert clean_location("PokeMMO Forêt de Jade Canal 2", custom) == "Forêt de Jade"


@pytest.mark.parametrize(
    "hud", ["Forêt de Jade", "FORET DE JADE Ch. 2", "foret de jade", "VIRIDIAN FOREST"]
)
def test_french_hud_names_resolve_to_the_data_key(fr_data: EncounterData, hud: str):
    assert fr_data.match_location(hud) == "KANTO_VIRIDIAN_FOREST"


def test_route_names_still_need_a_region_hint(fr_data: EncounterData):
    assert fr_data.match_location("Route 5") is None  # Kanto and Unova both have one
    assert fr_data.match_location("Route 5", "Kanto") == "KANTO_ROUTE_5"


def test_french_display_name_for_the_panel(fr_data: EncounterData):
    assert fr_data.location_name("KANTO_VIRIDIAN_FOREST") == "Forêt de Jade"
    assert fr_data.location_for_key("KANTO_VIRIDIAN_FOREST")["name"] == "Forêt de Jade"


def test_english_data_is_untouched_without_a_pack():
    plain = EncounterData.load(DATA / "encounters.json", DATA / "legendaries.json")
    assert plain.location_name("KANTO_VIRIDIAN_FOREST") == "VIRIDIAN FOREST"
    assert plain.match_location("Forêt de Jade") is None


def test_species_are_listed_by_their_french_name(fr_data: EncounterData):
    entries = fr_data.entries_here("KANTO_VIRIDIAN_FOREST", "DAY", 0, set())
    names = {e.id: e.name for e in entries}
    assert names[10] == "Chenipan" and names[25] == "Pikachu"


def test_location_entries_name_hook():
    encounters = [
        {
            "id": 1,
            "name": "Bulbasaur",
            "method": "Grass",
            "rarity": "Common",
            "min_level": 5,
            "max_level": 5,
            "periods": ["DAY"],
            "seasons": [0],
        }
    ]
    out = location_entries(encounters, "DAY", 0, set(), set(), lambda _i, n: n.upper())
    assert out[0].name == "BULBASAUR"


# --- caves ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "cave"),
    [
        ("Grotte Perdue", True),
        ("Mine Charbourg", True),
        ("Tunnel Merazon", True),
        ("Mont Couronné", True),
        ("Route Victoire", True),
        ("Cheminée", False),  # French 'mine' must not fire inside a word
        ("Forêt de Jade", False),
        ("Route 5", False),
    ],
)
def test_french_cave_keywords(fr: LangPack, name: str, cave: bool):
    assert is_cave_location(name, fr) is cave


def test_english_caves_unchanged_without_a_pack():
    assert is_cave_location("Rock Tunnel")
    assert is_cave_location("Fiery Path")
    assert not is_cave_location("Viridian Forest")


def test_caves_without_a_keyword_resolve_through_the_dex(
    fr: LangPack, fr_data: EncounterData, tmp_path: Path
):
    """'Veine Souterraine' (Wellspring Cave) and 'Chemin Ardent' (Fiery Path) have no
    French cave word, but the HUD name resolves to the English record, whose name
    the English heuristic recognises."""
    session = DexSession(fr_data, CaughtStore(tmp_path / "c.json", set()))
    assert not is_cave_location("Veine Souterraine", fr)
    assert session.location_is_cave("Veine Souterraine", is_cave_location)
    assert not is_cave_location("Chemin Ardent", fr)
    assert session.location_is_cave("Chemin Ardent", is_cave_location)
    assert not session.location_is_cave("Forêt de Jade", is_cave_location)


# --- templates --------------------------------------------------------------

REQUIRED = ("a.png", "b.png")


def test_templates_fall_back_to_english_when_incomplete(tmp_path: Path):
    pack = LangPack(code="fr", templates_subdir="fr")
    (tmp_path / "fr").mkdir()
    (tmp_path / "fr" / "a.png").write_bytes(b"x")  # b.png missing
    assert pick_templates_dir(tmp_path, pack, REQUIRED) == (tmp_path, False)


def test_translated_templates_are_used_when_complete(tmp_path: Path):
    pack = LangPack(code="fr", templates_subdir="fr")
    (tmp_path / "fr").mkdir()
    for name in REQUIRED:
        (tmp_path / "fr" / name).write_bytes(b"x")
    assert pick_templates_dir(tmp_path, pack, REQUIRED) == (tmp_path / "fr", True)


def test_english_always_uses_the_base_templates(tmp_path: Path):
    assert pick_templates_dir(tmp_path, LangPack(), REQUIRED) == (tmp_path, True)


# --- real captures of the French client (1920x1080 window) -------------------


def _frame(name: str):
    img = cv2.imread(str(FIXTURES / name))
    assert img is not None, name
    return img


def test_french_templates_are_complete(fr: LangPack):
    folder, translated = pick_templates_dir(DATA / "templates", fr, TEMPLATE_NAMES)
    assert translated and folder == DATA / "templates" / "fr"


@pytest.mark.parametrize(
    ("fixture", "menu", "caught", "action"),
    [
        ("fr_menu_attaque.png", True, False, False),  # ATTAQUE / SAC / POKÉMON / FUITE
        ("fr_action_utilise.png", False, False, True),  # "Flobio utilise Séisme!"
        ("fr_action_envoye.png", False, False, True),  # "Flobio est envoyé par PoppoZobbu!"
        ("fr_catch_et_hop.png", False, True, False),  # "Et hop! Medhyèna est attrapé!"
        ("fr_hud_tunnel_merazon.png", False, False, False),  # overworld: nothing to detect
        # "Un Alpha Nostenfer sauvage apparaît!": "sauvage" once scored 0.82 against a
        # shorter "envoyé" template, so the template includes "est ".
        ("fr_alpha_intro.png", False, False, False),
    ],
)
def test_french_battle_text_templates_on_real_frames(
    fixture: str, menu: bool, caught: bool, action: bool
):
    reader = BattleTextReader(CAL.battle_text, DATA / "templates" / "fr")
    got = reader.read(_frame(fixture))
    assert (got.menu_present, got.caught, got.action) == (menu, caught, action)


def test_english_templates_do_not_read_the_french_menu():
    """Why the translated set is needed: the English 'FIGHT' never matches."""
    reader = BattleTextReader(CAL.battle_text, DATA / "templates")
    assert not reader.read(_frame("fr_menu_attaque.png")).menu_present


def test_french_enemy_banner_is_read(fr: LangPack):
    img = _frame("fr_menu_attaque.png")
    species = NameReader(CAL.name, DATA / "species_core.json", fr).read(
        img, read_enemy_bars(img, CAL)[0]
    )
    assert species is not None
    assert (species["name"], species["level"]) == ("Dynavolt", 16)


def test_french_banner_survives_dropped_accents(fr: LangPack):
    img = _frame("fr_action_envoye.png")  # the OCR reads "Medhyena Niv. 14"
    species = NameReader(CAL.name, DATA / "species_core.json", fr).read(
        img, read_enemy_bars(img, CAL)[0]
    )
    assert species is not None
    assert (species["name"], species["level"]) == ("Medhyèna", 14)


def test_french_chat_turn_line_is_read(fr: LangPack):
    assert read_turn_number(_frame("fr_catch_et_hop.png"), CAL.chat, fr) == 3


@pytest.mark.parametrize(
    ("fixture", "hud", "key", "cave"),
    [
        ("fr_menu_attaque.png", "Route 110", "HOENN_ROUTE_110", False),
        ("fr_hud_tunnel_merazon.png", "Tunnel Merazon", "HOENN_RUSTURF_TUNNEL", True),
        ("fr_hud_chemin_ardent.png", "Chemin Ardent", "HOENN_FIERY_PATH", True),
    ],
)
def test_french_hud_location_to_dex_and_cave(
    fr: LangPack,
    fr_data: EncounterData,
    tmp_path: Path,
    fixture: str,
    hud: str,
    key: str,
    cave: bool,
):
    name = read_location(_frame(fixture), CAL.location, fr)
    assert name == hud
    assert fr_data.match_location(name) == key
    session = DexSession(fr_data, CaughtStore(tmp_path / "c.json", set()))
    found = is_cave_location(name, fr) or session.location_is_cave(name, is_cave_location)
    assert found is cave


def test_alpha_intro_frame_hud_and_chat(fr: LangPack, fr_data: EncounterData):
    img = _frame("fr_alpha_intro.png")
    name = read_location(img, CAL.location, fr)
    assert name == "Tour des Cieux (Toit)"
    assert fr_data.match_location(name) == "UNOVA_CELESTIAL_TOWER"
    assert read_turn_number(img, CAL.chat, fr) == 1


# --- OCR noise seen in a real French session (userdata/unmatched_locations.txt) ----


def test_channel_suffix_patterns_stay_in_step():
    assert dex_tracker._CH_SUFFIX.pattern == location_reader._CH_SUFFIX.pattern


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("PokeMMO Route 110 Ch. o $188 878 jeudi, 19:37, Eté", "Route 110"),  # channel 0 read "o"
        ("PokeMMO Route 111 Ch..3 o $188 614  jeudi, 15:43, Ete", "Route 111"),
        ("PokeMMO Route117 ch:5 0$182790 jeudi,13:13,Ete", "Route117"),
        ("PokeMMO Route 110 Ch. Eo $188 878  jeudi, 19:41 Eté", "Route 110"),
        ("PokeMMO Chemin Ardent Ch. 3", "Chemin Ardent"),  # "Ch" inside a word is kept
        ("PokeMMO Charbourg Ch. 2", "Charbourg"),
    ],
)
def test_hud_line_noise_is_cut_after_the_name(raw: str, cleaned: str):
    assert clean_location(raw) == cleaned


@pytest.mark.parametrize(
    ("hud", "key"),
    [
        ("Route 110", "HOENN_ROUTE_110"),
        ("Route 11o", "HOENN_ROUTE_110"),
        ("Route 1l7", "HOENN_ROUTE_117"),
        ("Route 11l", "HOENN_ROUTE_111"),
        ("Route 1ll", "HOENN_ROUTE_111"),
        ("Route 1i1", "HOENN_ROUTE_111"),
        ("Route 1il", "HOENN_ROUTE_111"),
        ("Route11r", "HOENN_ROUTE_111"),
        ("MRoutei11", "HOENN_ROUTE_111"),
        ("Route1io C", "HOENN_ROUTE_110"),
        ("Yh Route 110", "HOENN_ROUTE_110"),  # map icon read as "Yh"
        ("Route 110 Ch. o $188 878  jeudi, 19:37, Ete", "HOENN_ROUTE_110"),
    ],
)
def test_route_numbers_survive_digit_letter_confusions(fr_data: EncounterData, hud: str, key: str):
    assert fr_data.match_location(hud) == key


@pytest.mark.parametrize(
    "hud",
    [
        "Tour des Cieux (1er)",
        "Tour des Cieux (2em)",
        "Tour des cieux (2em)",
        "Tour des Cieux × (3em)",
        "Tour des Cieux (Toit)",
    ],
)
def test_floor_suffix_is_not_part_of_the_zone_name(fr_data: EncounterData, hud: str):
    assert fr_data.match_location(hud) == "UNOVA_CELESTIAL_TOWER"


@pytest.mark.parametrize(
    "hud", ["Lavandia", "Yh Lavandia", "Mont Dresseurs", "Vergazon", "Volucité"]
)
def test_zones_missing_from_the_data_never_match_a_lookalike(fr_data: EncounterData, hud: str):
    """Lavandia (Mauville City), Mont Dresseurs (Trainer Hill), Vergazon (Verdanturf)
    and Volucité (Castelia) have no wild encounters in the data: they must come out as
    unknown, not as 'New Lavandia' / 'Mont Foré' / 'L'Océane' (substring look-alikes)."""
    assert fr_data.match_location(hud) is None
    assert fr_data.regions_for_name(hud) == set()


def test_english_floor_suffix_and_exact_names_still_work():
    data = EncounterData.load(DATA / "encounters.json", DATA / "legendaries.json")
    assert data.match_location("Celestial Tower (2F) Ch. 4") == "UNOVA_CELESTIAL_TOWER"
    assert data.match_location("Route 41 Ch. 2") == "JOHTO_ROUTE_41"


# --- display labels and UI texts ----------------------------------------------


def test_display_labels_fall_back_to_the_english_label():
    pack = LangPack()
    assert pack.ball("Great Ball") == "Great Ball"
    assert pack.way("Shadow Pheno") == "Shadow Pheno"
    assert pack.rarity("Very Rare") == "Very Rare"
    assert pack.period("Morning") == "Morning"
    assert pack.season("Summer") == "Summer"
    assert pack.region("Unova") == "Unova"


def test_ui_text_fills_placeholders_and_falls_back_on_a_broken_template():
    pack = LangPack(ui={"rate_line": "Taux : {rate} · Tour {turn}", "oops": "{missing}"})
    assert pack.text("rate_line", "Rate: {rate}", rate=45, turn=2) == "Taux : 45 · Tour 2"
    assert pack.text("absent", "{n} left", n=3) == "3 left"  # no entry: the English default
    assert pack.text("oops", "{n} left", n=3) == "3 left"  # bad user template: default


def test_user_file_can_override_one_ui_text(tmp_path: Path):
    user = tmp_path / "userdata"
    (user / "lang").mkdir(parents=True)
    (user / "lang" / "fr.json").write_text(
        json.dumps({"ui": {"needed_left": "{n} restants"}, "ball_names": {"Dusk Ball": "Sombre"}}),
        "utf-8",
    )
    pack = load_lang("fr", LANG_DIR, user)
    assert pack.text("needed_left", "{n} left", n=4) == "4 restants"
    assert pack.ball("Dusk Ball") == "Sombre"
    assert pack.ball("Great Ball") == "Super Ball"  # the bundled entries survive the merge
    assert "rate_line" in pack.ui  # the other bundled texts survive the merge


def test_french_ball_names_cover_every_ball(fr: LangPack):
    balls = json.loads((DATA / "balls.json").read_text("utf-8"))["balls"]
    missing = [b["name"] for b in balls if b["name"] not in fr.ball_names]
    assert not missing, missing
    assert fr.ball("Great Ball") == "Super Ball"
    assert fr.ball("Quick Ball") == "Rapide Ball"
    assert fr.ball("Poké Ball") == "Poké Ball"


def test_french_labels_cover_every_value_in_the_data(fr: LangPack):
    """Every rarity, season, period, region and way the dex panel can print has a
    French label (a missing one would silently stay English)."""
    import dex_tracker

    locations = json.loads((DATA / "encounters.json").read_text("utf-8"))["locations"]
    rarities, ways, periods, regions = set(), set(), set(), set()
    for loc in locations.values():
        regions.add(loc["region"].title())
        for e in loc["encounters"]:
            rarities.add(e["rarity"])
            periods.update(p.title() for p in e["periods"])
            ways.add(dex_tracker.encounter_tag(e["method"], e["rarity"]))
    ways.discard("")
    ways.add("Rod")  # the collapse of two or more rods (see dex_tracker._compact_ways)
    assert rarities <= set(fr.rarity_names), rarities - set(fr.rarity_names)
    assert ways <= set(fr.way_names), ways - set(fr.way_names)
    assert periods <= set(fr.period_names), periods - set(fr.period_names)
    assert {"Spring", "Summer", "Autumn", "Winter"} <= set(fr.season_names)
    assert "Unova" in regions and fr.region("Unova") == "Unys"
    assert fr.region("Kanto") == "Kanto"  # same name: no entry needed


def test_every_ui_key_used_in_the_code_exists_in_the_french_pack(fr: LangPack):
    """The code asks for texts by key with an English default; a typo'd key would
    silently show English. Check each key, and that the French template uses exactly
    the placeholders of the English default."""
    sources = "".join(
        (ROOT / "src" / f).read_text("utf-8") for f in ("overlay.py", "dex_panel.py", "app.py")
    )
    calls = re.findall(r'\.text\(\s*"([a-z_]+)"\s*,\s*"((?:[^"\\]|\\.)*)"', sources)
    assert len(calls) >= 20
    for key, default in calls:
        assert key in fr.ui, f"ui key {key!r} used in the code but missing from fr.json"
        assert set(re.findall(r"{(\w+)}", fr.ui[key])) == set(re.findall(r"{(\w+)}", default)), key
    for status in ("slp", "par", "psn", "brn", "frz"):  # built with an f-string in overlay.py
        assert f"status_{status}" in fr.ui


def test_status_badge_label_is_translated(fr: LangPack):
    from overlay import status_badge

    assert status_badge("slp", fr)[0] == "SOM"
    assert status_badge("slp")[0] == "SLP"
    assert status_badge("brn", fr)[0] == "BRU"
    assert status_badge(None, fr) is None
    assert status_badge("unknown", fr) is None
