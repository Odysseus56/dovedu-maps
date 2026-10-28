# Dovedu - Maps

Offline map packs for the [Dovedu](https://dovedu.app) Android app: one region per pack, with the map, the road graph for routing and
an address index, so the app shows the map, finds addresses and routes with no server.

The app's **Download maps** reads `catalog.json` and fetches the pack's files from the release it links to. Each catalogue
format has its own rolling release, `catalog-v<format>`, holding only a copy of the live `catalog.json` of that format: an
app asks https://dovedu.app/dl/maps/catalog-v<its format>/catalog.json (apps up to 0.35.0: /dl/maps/catalog.json, format 3),
which the app's website redirects here. So a new format goes live beside the old one and never strands an older app.
Never delete a `catalog-v<n>` release while apps of that format are out: they lose their maps and road data.
Older releases are kept so that a phone halfway through a download can finish it, and so that each format's catalogue
keeps working. Latest marks the newest live release, for this page only: no app reads it.

## Data and licences

- Map, roads and addresses: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, Open Database License (ODbL).
- Map style, sprites and fonts: [OpenFreeMap](https://openfreemap.org) "liberty" style.
- Map tiles built with [Planetiler](https://github.com/onthegomap/planetiler); road graph built with [Valhalla](https://github.com/valhalla/valhalla).

Packs are built by the app's own tools (`tools/mapdata/` in the app repository) and published here as GitHub releases.

## Satellite orbits

The release `orbits` holds the last three days' daily broadcast orbit files (RINEX navigation), refreshed every hour by
`.github/workflows/orbits.yml` with `.github/orbits.py`: IGS/BKG when it answers, else Wuhan University's IGS archive (for today,
a merge of its stations' hourly files; a file without the GPS ionosphere lines gets a station's). Beside them, CODE's (Bern)
forecast ionosphere maps for today and tomorrow (IONEX, `COD0OPSP0D_`/`COD0OPSP1D_<day>`, from ESA's or Wuhan's archive).
The app downloads them from here first (through https://dovedu.app/dl/orbits/, which
the website redirects to this release), because igs.bkg.bund.de does not answer from some networks. That release is never
marked Latest.

This repository was `taxi-antispoof-maps` until 2026-10-14. Apps before 0.24.1 ask that address directly, and GitHub
forwards it here only while no repository of that name exists: never create one.

The app's privacy policy and terms of use are at https://dovedu.app.
