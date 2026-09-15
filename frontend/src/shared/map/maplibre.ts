import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

// MapLibre 6 finds its worker relative to its own module URL. Vite pre-bundles
// maplibre-gl into .vite/deps/ (and hashed chunks in a build), where that file
// does not exist: the worker 404s, and every tile and GeoJSON source silently
// renders nothing over the style background. Vite bundles the worker with its
// shared chunk here and hands MapLibre a URL that exists.
setWorkerUrl(workerUrl);
