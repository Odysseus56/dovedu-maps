# Dovedu - Maps

Offline map packs for the [Dovedu](https://dovedu.app) Android app: one region per pack, with the map, the road graph for routing and
an address index, so the app shows the map, finds addresses and routes with no server.

The app's **Download maps** reads `catalog.json` from the latest release and fetches the pack's files from that release.
The app asks for it at https://dovedu.app/dl/maps/catalog.json, which the app's website redirects here; keep the name
`catalog.json` in the latest release.
Older releases are kept so that a phone halfway through a download can finish it.

## Data and licences

- Map, roads and addresses: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, Open Database License (ODbL).
- Map style, sprites and fonts: [OpenFreeMap](https://openfreemap.org) "liberty" style.
- Map tiles built with [Planetiler](https://github.com/onthegomap/planetiler); road graph built with [Valhalla](https://github.com/valhalla/valhalla).

Packs are built by the app's own tools (`tools/mapdata/` in the app repository) and published here as GitHub releases.

## Satellite orbits

The release `orbits` holds the last three days' daily broadcast orbit files (RINEX navigation), refreshed every hour by
`.github/workflows/orbits.yml` with `.github/orbits.py`: IGS/BKG when it answers, else Wuhan University's IGS archive (for today,
a merge of its stations' hourly files). The app downloads them from here first (through https://dovedu.app/dl/orbits/, which
the website redirects to this release), because igs.bkg.bund.de does not answer from some networks. That release is never
marked Latest, so the maps' catalogue link stays on the map packs.

This repository was `taxi-antispoof-maps` until 2026-10-14. Apps before 0.24.1 ask that address directly, and GitHub
forwards it here only while no repository of that name exists: never create one.

The app's privacy policy and terms of use are at https://dovedu.app.
