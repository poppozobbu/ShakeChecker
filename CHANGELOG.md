# Changelog

All notable changes to ShakeChecker are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Language packs (French first)** — `--lang fr` (remembered in
  `userdata/settings.json`) switches the species names, dex location names and the
  strings the OCR looks for (level marker, turn line, channel suffix, cave words) to
  a pack in `src/data/lang/`. Name matching now ignores accents, and
  `userdata/lang/<code>.json` can override any entry. A non-English run logs HUD
  locations it cannot match to `userdata/unmatched_locations.txt`. The French pack
  ships its own battle-text templates and is checked on real captures of a 1920x1080
  client; the Alpha banner prefix and most zone names are still unchecked — see
  [docs/LANGUAGES.md](docs/LANGUAGES.md).
- **Translated overlay and dex panel** — with a language pack, the Poké Ball names, the
  header lines ("Taux : 45 · Tour 3", "PV : 100%"), status badges, the rarity legend,
  encounter conditions ("Canne", "Phéno. ombre"), seasons, periods and the panel and
  tray-menu captions are drawn in the pack's language. The English label stays the
  internal key, so nothing else changes. Any entry can be overridden in
  `userdata/lang/<code>.json`. A long subtitle now shrinks to fit the panel.
- `Fiery Path` now counts as a cave (Dusk Ball), in every language.

### Fixed

- HUD zone matching, in every language: the OCR reading the channel number or route
  digits as letters (`Ch. o`, `Route 1l7`) no longer defeats the match; a floor suffix
  such as `(2F)` is ignored; and a zone missing from the data is no longer matched to
  a look-alike by substring (fuzzy matching now compares whole names).

## [1.2.0] - 2026-06-21

### Added

- **Keep caught species in the dex panel** — caught Pokémon now stay in the
  "missing here" list, shown checked (✓) and sorted by Pokédex number at the
  bottom, instead of disappearing. Toggle it under the gear menu ("Show
  caught"); on by default.
- **Mystery catch rate** — species with no published catch rate (the roaming
  Latias, Latios, Mesprit and Cresselia) show the rate and every ball as "??"
  instead of nothing.

### Fixed

- **Roaming legendary catch rates** — the roaming birds and beasts (Articuno,
  Zapdos, Moltres, Raikou, Entei, Suicune) used the wrong base rate; corrected
  to match the in-client PokeMMO catch calculator. A species with no known rate
  no longer breaks the battle overlay (it shows "??").
- **Dex panel resize lag** — the panel no longer stays too tall for a moment
  after the list shrinks (e.g. after turning "Show caught" off).

### Changed

- A divider now separates the Profiles and Dex sections in the gear menu.

## [1.1.1] - 2026-06-21

### Fixed

- **Nidoran gender** — a male Nidoran was recognized and shown as the female
  one. OCR cannot read the gender glyph, so the name tied between the two
  entries and always resolved to the female. The gender is now read from the
  banner's colored gender icon (pink female / blue male). Catch rates were
  correct before; the name, sprite, and dex record were not.
- **Dex panel at region transitions** — the "missing here" panel no longer
  disappears on a single garbled location read; it stays up through transient
  OCR misses and only hides after several consecutive misses.

### Added

- **Single-instance lock** — starting ShakeChecker a second time now shows a
  notice and exits instead of drawing a duplicate overlay.

### Docs

- Landing page and README note that ShakeChecker is built for the default
  client theme.
- README links the VirusTotal scan and a permanent latest-download link.

## [1.1.0] - 2026-06-18

### Added

- **Ball picker** — choose which Poké Balls appear in the overlay, via the
  Poké Ball button in the dex panel header.
- **Overlay sorted by catch rate** — the best ball is shown on top.
- **System-tray icon with a Quit action** — the windowless build can now be
  closed cleanly.
- New flat retro Poké Ball app/tray icon.

### Fixed

- **Trainer detection in the rain** — a rainy wild battle was misread as a
  trainer battle (which hid the overlay). The party-strip check now requires
  compact icon blobs, so diagonal weather streaks no longer trigger it. Locked
  with a rain fixture as a regression test.
- **Overlay height** — the window now shrinks to fit when balls are filtered, so
  there is no tall empty panel and rows stay evenly spaced for any ball count.
- **Dex header popups** (profiles, ball picker, legend) now close when you click
  back into the game.

### Docs

- New landing page (retro pixel) with an FAQ, demo videos, a screenshot gallery,
  and a fan-made disclaimer.

## [1.0.0] - 2026-06-17

Initial release: read-only catch-rate overlay (HP %, status, per-ball catch
probability using the Gen 3/4 formula), Location Dex "missing here" panel, and a
packaged Windows `.exe`.
