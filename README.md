# Taxi-Antispoof - Maps

Offline map packs for the Taxi Antispoof Android app: one region per pack, with the map, the road graph for routing and
an address index, so the app shows the map, finds addresses and routes with no server.

The app's **Download maps** reads `catalog.json` from the latest release and fetches the pack's files from that release.
Older releases are kept so that a phone halfway through a download can finish it.

## Data and licences

- Map, roads and addresses: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, Open Database License (ODbL).
- Map style, sprites and fonts: [OpenFreeMap](https://openfreemap.org) "liberty" style.
- Map tiles built with [Planetiler](https://github.com/onthegomap/planetiler); road graph built with [Valhalla](https://github.com/valhalla/valhalla).

Packs are built by the app's own tools (`tools/mapdata/` in the app repository) and published here as GitHub releases.
