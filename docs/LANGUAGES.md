# Language packs

ShakeChecker reads the PokeMMO screen, so a few things depend on the client language.
English is built in; other languages are **packs** in `src/data/lang/<code>.json`.
French (`fr`) is the first one. Verified on a real 1920x1080 French client: the four
battle-text templates, the level marker (`Niv.`), the chat turn line (`Le tour 3 a
commencé !`), the `Ch. 3` channel suffix, the name/level banner, and a handful of HUD
zones (`Route 110`, `Tunnel Merazon`, `Chemin Ardent`, `Tour des Cieux`). **Not yet
checked:** the Alpha banner itself (the narration reads `Un Alpha Nostenfer sauvage
apparaît!`, so the `Alpha ` prefix is most likely the English one), and most of the
other ~300 zone names (they come from the main-series games).

## Using a pack

```text
python src/app.py --lang fr        # remembered in userdata/settings.json
```

The packaged exe has no command line: set `"language": "fr"` in
`userdata/settings.json` (`%APPDATA%\ShakeChecker\settings.json`).

To fix or add a single entry without touching the bundled data, create
`userdata/lang/fr.json` with only the keys to change; it is merged on top of the pack:

```json
{ "location_names": { "KANTO_VIRIDIAN_FOREST": "Forêt de Jade" } }
```

While you play, every HUD location the dex tables cannot match is appended (once)
to `userdata/unmatched_locations.txt`: those are the names missing from the pack.

## What a pack contains

| Field | Used for | English default |
| --- | --- | --- |
| `species_names` | id → name: fuzzy matching of the enemy name, overlay and dex lists | `species_core.json` |
| `location_names` | data key → HUD zone name (`KANTO_ROUTE_5`…) | names in `encounters.json` |
| `level_marker` | regex for the "Lv" token that ends the name on the banner | `\b[li][vu]\b` |
| `alpha_prefix` | prefix of an Alpha banner (lowercase, trailing space) | `alpha ` |
| `turn_pattern` | regex for the chat turn line, group 1 = the number | `turn\s*(\d{1,3})\s*start` |
| `channel_suffix` | regex for the HUD " Ch. 2" suffix | `\s*ch\.?\s*\d+.*$` |
| `cave_keywords`, `cave_word_groups` | cave words (Dusk Ball); **replace** the English ones | English lists |
| `templates_subdir` | folder in `src/data/templates/` with the translated templates | – |
| `ball_names` | English ball name → drawn name (overlay rows, ball picker) | English names |
| `way_names` | how to find a species ("Rod", "Shadow Pheno", "Headbutt"…) in the dex panel | English labels |
| `rarity_names` | rarity legend ("Very Rare"…) | English labels |
| `period_names`, `season_names`, `region_names` | the panel's subtitle ("Unova · Morning · Summer") | English labels |
| `ui` | the short fixed texts: rate/turn line, HP line, level tag, status badges, panel and menu captions (see the keys in `fr.json`) | English texts |

Matching ignores case and accents everywhere, because the OCR drops them. English zone
names are always indexed too, so a zone the pack does not translate still matches if
the HUD shows it in English, and `Route N` zones need no entry. A cave whose name has no
keyword is still found through the dex tables (the HUD name resolves to the English
record).

`scripts/build_lang.py <code>` regenerates the two name tables from PokeAPI and keeps
the hand-written fields.

## Checklist for a new or provisional language

The pieces that need screenshots of the real client, **unscaled**. Capture the PokeMMO
window with nothing overlapping it (another window over its edge ends up in the
frame, and its text gets OCR'd):

1. **Battle-text templates** (the turn counter and the catch detection depend on them;
   French is done, from `ATTAQUE`, `Et hop!`, `utilise` and `envoyé`).
   Four tight crops of one word each, in `src/data/templates/<code>/`:
   `menu_fight.png` (the Fight button label), `catch_gotcha.png` (the catch banner),
   `action_used.png` (the word "used" in "X used Y!"), `action_go.png` ("Go!" when a
   Pokémon is sent out). Cut them with `scripts/crop_template.py`, then verify:

   ```text
   python scripts/check_templates.py --lang fr menu.png catch.png used.png go.png
   ```

   Until all four exist the English ones are used and a warning is logged.
2. **Level marker, Alpha prefix, turn line, channel suffix.** Run
   `python scripts/ocr_probe.py --lang fr shot.png` on a battle screenshot (name banner
   + chat + HUD) to see the exact text the OCR reads, then adjust the regexes.
3. **Zone names.** Compare `location_names` with what the HUD prints (the unmatched log
   above), then correct the pack or the user file.
4. **OCR accents.** The bundled model is Chinese/English; check that accented names read
   acceptably with `ocr_probe.py`. Accent folding makes small losses harmless.

## Zone matching

A HUD name is matched to the dex tables as a whole string, never as a substring, so
a place with no wild encounters in the data (towns, `Lavandia`, `Vergazon`,
`Volucité`...) comes out as "unknown" instead of as a look-alike (`New Lavandia`).
Those names still land in `userdata/unmatched_locations.txt`; they need no fix.
Also handled: the OCR reading channel/route digits as letters (`Ch. o`, `Route 1l7`),
a floor suffix (`Tour des Cieux (2em)`), the money line glued after the zone name,
and the map icon read as a stray `Yh` before it.

## Display texts

`ball_names`, `way_names`, `rarity_names`, `period_names`, `season_names`,
`region_names` and `ui` only change what is **drawn**. The English label stays the
internal key (sprite lookup, colours, sorting, hiding a ball), so a missing entry just
shows the English text and never breaks anything. In `ui`, `{placeholders}` must be kept
(`"{n} à capturer"`); a template that does not format falls back to the English text.

The bundled French labels are hand-translated from the main-series games (the ball names
come from PokeAPI) and have **not** been compared with the PokeMMO client's own wording.
To change one, put just that entry in `userdata/lang/fr.json`:

```json
{ "ui": { "needed_left": "{n} restants" }, "ball_names": { "Dusk Ball": "Sombre" } }
```

The panel is a fixed width: a long subtitle shrinks its font down to 8 px, and a long
"way" label is cut with an ellipsis, so prefer short wording.
