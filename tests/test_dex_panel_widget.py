from __future__ import annotations

import pytest

from dex_panel import DexPanel, rarity_color_hex
from dex_session import LocationView
from dex_tracker import DexEntry
from game_time import Period

# --- pure helper ---


def test_rarity_colors_follow_the_scheme():
    assert rarity_color_hex("Common") == "#9d9d9d"
    assert rarity_color_hex("Very Common") == "#9d9d9d"  # falls back to grey
    assert rarity_color_hex("Uncommon") == "#ffffff"
    assert rarity_color_hex("Rare") == "#3fcf5f"
    assert rarity_color_hex("Very Rare") == "#4aa3ff"
    assert rarity_color_hex("Lure") == "#b86bff"
    assert rarity_color_hex("Special") == "#ffd633"
    assert rarity_color_hex("???") == "#9d9d9d"  # unknown -> grey


# --- widget smoke tests ---


@pytest.fixture(scope="module")
def qt_app():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:  # pragma: no cover
        pytest.skip("PyQt6 unavailable")
    yield QApplication.instance() or QApplication([])


def view(entries):
    return LocationView("ROUTE 110", "HOENN", Period.DAY, 1, entries)


def test_show_here_fills_rows_and_colors(qt_app):
    entries = [
        DexEntry(1, "Bulbasaur", (), "Lure", False),
        DexEntry(131, "Lapras", ("Water",), "Very Rare", False),
    ]
    p = DexPanel()
    p.show_here(view(entries))
    assert "2 left" in p._subtitle.text()
    assert "Bulbasaur" in p._rows[0]["name"].text()
    assert "#b86bff" in p._rows[0]["name"].text()  # Lure -> purple
    assert "Water" in p._rows[1]["way"].text()
    assert "#4aa3ff" in p._rows[1]["name"].text()  # Very Rare -> blue


def test_lists_all_entries_scrollable(qt_app):
    # all uncaught get a row (the list scrolls); no "5 + X" cap any more
    entries = [DexEntry(i, f"Mon{i}", (), "Common", False) for i in range(1, 9)]  # 8 uncaught
    p = DexPanel()
    p.show_here(view(entries))
    visible = [r for r in p._rows if r["w"].isVisibleTo(p)]
    assert len(visible) == 8
    assert "Mon8" in p._rows[7]["name"].text()
    assert not hasattr(p, "_overflow")


def test_caught_padding_marked_with_check(qt_app):
    entries = [
        DexEntry(1, "A", (), "Common", False),  # 1 uncaught
        DexEntry(131, "Lapras", ("Water",), "Very Rare", True),  # caught rare -> pads, ✓
    ]
    p = DexPanel()
    p.show_here(view(entries))
    assert "1 left" in p._subtitle.text()
    assert "✓" in p._rows[1]["way"].text()


def test_all_caught_message_in_hide_mode(qt_app):
    entries = [DexEntry(1, "A", (), "Common", True)]  # caught, too common to pad
    p = DexPanel()
    p.get_keep_caught = lambda: False  # hide-mode: caught commons removed -> empty
    p.show_here(view(entries))
    assert "0 left" in p._subtitle.text()
    assert "all caught here" in p._rows[0]["name"].text()


def test_keep_caught_keeps_caught_common_checked(qt_app):
    # issue #16 default: a caught common species stays in the list, checked.
    entries = [DexEntry(1, "A", (), "Common", True)]
    p = DexPanel()
    p.get_keep_caught = lambda: True
    p.show_here(view(entries))
    assert "0 left" in p._subtitle.text()
    assert "A" in p._rows[0]["name"].text()
    assert "✓" in p._rows[0]["way"].text()
    assert "all caught here" not in p._rows[0]["name"].text()


def test_keep_caught_toggle_uses_callback(qt_app):
    calls: list[bool] = []
    p = DexPanel()
    p.on_toggle_keep_caught = lambda: calls.append(True)
    p.get_keep_caught = lambda: True
    p._toggle_keep_caught()
    assert calls == [True]


def test_panel_height_tracks_row_count(qt_app):
    # The scroll viewport grows with more rows and shrinks back to the same height
    # for the same content (e.g. after toggling "show caught" off). The live "stays
    # tall for a refresh" lag is a deferred-relayout issue that only shows with a
    # running event loop; the synchronous invalidate/activate in show_here fixes it
    # but cannot be reproduced headless, so this only locks the resize invariant.
    many = [DexEntry(i, f"Mon{i}", (), "Common", False) for i in range(1, 13)]
    few = [DexEntry(1, "A", (), "Common", False)]
    p = DexPanel()
    p.show_here(view(few))
    small = p._scroll.height()
    p.show_here(view(many))
    assert p._scroll.height() > small  # grew with more rows
    p.show_here(view(few))
    assert p._scroll.height() == small  # back to the same height for the same content


def test_row_click_invokes_toggle_with_dex_id(qt_app):
    got: list[int] = []
    p = DexPanel()
    p.on_toggle_caught = got.append
    p.show_here(view([DexEntry(72, "Tentacool", ("Water",), "Uncommon", False)]))
    p._row_clicked(0)
    assert got == [72]
    p._row_clicked(4)  # an empty/hidden row -> no species -> no callback
    assert got == [72]


def test_profile_menu_uses_callback_list(qt_app):
    # the menu is built from get_profiles(); just verify it's consulted safely
    p = DexPanel()
    p.get_profiles = lambda: ("Red", ["Red", "Blue"])
    active, names = p.get_profiles()
    assert active == "Red" and names == ["Red", "Blue"]


def test_ball_picker_toggle_invokes_callback(qt_app):
    toggled: list[str] = []
    p = DexPanel()
    p.get_ball_state = lambda: ([("poke", "Poké Ball"), ("dusk", "Dusk Ball")], {"dusk"})
    p.on_toggle_ball = toggled.append
    p._open_balls()  # builds the popup from get_ball_state (no crash on missing sprites)
    assert p._balls is not None
    p._toggle_ball("poke")
    assert toggled == ["poke"]


def test_ball_picker_set_all_invokes_callback(qt_app):
    calls: list[bool] = []
    p = DexPanel()
    p.get_ball_state = lambda: ([("poke", "Poké Ball")], set())
    p.on_set_all_balls = calls.append
    p._set_all_balls(False)
    assert calls == [False]


def test_popup_closes_when_app_goes_inactive(qt_app):
    from PyQt6.QtCore import Qt

    p = DexPanel()
    p.get_ball_state = lambda: ([("poke", "Poké Ball"), ("dusk", "Dusk Ball")], set())
    p._open_balls()
    assert p._balls is not None and p._balls.isVisible()
    # staying active (e.g. our own profile dialog) must NOT close it
    p._on_app_state_changed(Qt.ApplicationState.ApplicationActive)
    assert p._balls.isVisible()
    # clicking back into the game deactivates the app -> popup closes
    p._on_app_state_changed(Qt.ApplicationState.ApplicationInactive)
    assert not p._balls.isVisible()


def _fr():
    from pathlib import Path

    from lang import load_lang

    return load_lang("fr", Path(__file__).parent.parent / "src" / "data" / "lang")


def test_french_panel_header_ways_and_legend(qt_app):
    p = DexPanel(lang=_fr())
    entries = [
        DexEntry(129, "Magicarpe", ("Rod",), "Very Common", False),  # 2+ rods collapse to "Rod"
        DexEntry(130, "Léviator", ("Super Rod",), "Very Rare", False),
        DexEntry(63, "Abra", ("Shadow Pheno",), "Special", False),
    ]
    p.show_here(LocationView("Route 110", "UNOVA", Period.MORNING, 1, entries))
    assert p._title.text() == "Route 110"
    assert p._subtitle.text() == "Unys · Matin · Été · 3 à capturer"
    # rows are sorted by rarity, so look the ways up by dex id
    ways = {r["dex"]: r["way"].text() for r in p._rows[:3]}
    assert ways == {129: "Canne", 130: "Méga Canne", 63: "Phéno. ombre"}
    legend = p._build_legend()
    texts = " ".join(lab.text() for lab in legend.findChildren(type(p._title)))
    assert "Très rare" in texts and "Leurre" in texts and "Rareté" in texts


def test_french_all_caught_message(qt_app):
    p = DexPanel(lang=_fr())
    p.get_keep_caught = lambda: False
    p.show_here(LocationView("Route 110", "HOENN", Period.DAY, 1, []))
    assert "tous capturés ici" in p._rows[0]["name"].text()


def test_english_panel_header_is_unchanged(qt_app):
    p = DexPanel()
    p.show_here(view([DexEntry(129, "Magikarp", ("Old Rod",), "Common", False)]))
    assert p._title.text() == "Route 110"
    assert p._subtitle.text() == "Hoenn · Day · Summer · 1 left"


def test_display_title_keeps_translated_casing():
    from dex_panel import display_title

    assert display_title("ROUTE 110") == "Route 110"
    assert display_title("VIRIDIAN FOREST") == "Viridian Forest"
    assert display_title("Forêt de Jade") == "Forêt de Jade"  # not "Forêt De Jade"
    assert display_title("Tour des Cieux (Toit)") == "Tour des Cieux (Toit)"


def test_long_translated_subtitle_shrinks_to_fit(qt_app):
    p = DexPanel(lang=_fr())
    p.apply_scale(1.0)
    p._set_subtitle("Sinnoh · Matin · Printemps · 12 à capturer")
    from PyQt6.QtGui import QFontMetrics

    width = QFontMetrics(p._subtitle.font()).horizontalAdvance(p._subtitle.text())
    assert width <= p._panel_w - 2 * 12
    p._set_subtitle("Kanto · Jour")  # short: keeps the normal size
    assert p._subtitle.font().pixelSize() == p._px(11)
