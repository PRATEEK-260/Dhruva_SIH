// Basemaps for the shore console. All keyless raster or vector tiles, so there is
// no token and no quota (the reason for MapLibre over Mapbox in the first place).
//
// Esri's Ocean basemap draws the sea floor from GEBCO and NOAA bathymetry: the
// shelf edge and canyons off the coast are what a fisherman navigates by. Esri's
// terms ask for the attribution below; a production deployment needs an ArcGIS
// account, which is free for non-commercial use.

import type { StyleSpecification } from "maplibre-gl";

export type BasemapId = "seafloor" | "satellite" | "dark";

const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
const PLACES = `${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`;

function rasterStyle(
  layers: { id: string; tiles: string; attribution: string; maxzoom: number }[],
): StyleSpecification {
  return {
    version: 8,
    sources: Object.fromEntries(
      layers.map((l) => [
        l.id,
        { type: "raster", tiles: [l.tiles], tileSize: 256, maxzoom: l.maxzoom, attribution: l.attribution },
      ]),
    ),
    layers: layers.map((l) => ({ id: l.id, type: "raster", source: l.id })),
  };
}

export const BASEMAPS: Record<BasemapId, { label: string; style: StyleSpecification | string }> = {
  seafloor: {
    label: "Sea floor",
    style: rasterStyle([
      {
        id: "ocean-base",
        tiles: `${ESRI}/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}`,
        attribution: "Esri, GEBCO, NOAA, National Geographic, Garmin, HERE",
        maxzoom: 10,
      },
      // Places, not Esri's ocean reference layer: that one still says Madras
      // and Bangalore.
      { id: "places", tiles: PLACES, attribution: "", maxzoom: 13 },
    ]),
  },
  satellite: {
    label: "Satellite",
    style: rasterStyle([
      {
        id: "imagery",
        tiles: `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`,
        attribution: "Esri, Maxar, Earthstar Geographics",
        maxzoom: 17,
      },
      // Not CARTO's raster labels: those now need a key and draw an
      // "API KEY REQUIRED" watermark over the map.
      { id: "places", tiles: PLACES, attribution: "", maxzoom: 13 },
    ]),
  },
  dark: {
    label: "Dark",
    style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  },
};
