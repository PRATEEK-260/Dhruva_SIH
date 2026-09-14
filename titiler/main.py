"""Dynamic tile server for Shore Console's raster layers.

Deliberately its own service, not a route on the api container: it needs
GDAL/rasterio at the OS level, a materially heavier footprint than the rest
of the backend, and after this session's own api crash-loop (a heavy
dependency pulled in at module import time, from the earlier /advisory work)
that coupling is exactly what to avoid.

This is TiTiler's own documented minimal pattern (TilerFactory + CORS +
exception handlers), not a custom reimplementation.
"""

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.core.factory import TilerFactory

app = FastAPI(title="dhruva-titiler")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# Both router_prefix (on the factory) AND prefix (on include_router) are
# required — found live, not from the docs example, which showed neither:
# router_prefix alone doesn't mount the routes, and prefix alone mounts them
# correctly but leaves the factory's own url_for() (which tilejson.json's
# self-referencing "tiles" field is built from) not knowing about it, so the
# very first curl against .../cog/tiles/... 404'd, and once that was fixed,
# the tilejson response it returned pointed AT ITS OWN "tiles" template
# without /cog either. TiTiler's cogValidateExtension example in its own docs
# is what showed both are needed together.
cog = TilerFactory(router_prefix="/cog")
app.include_router(cog.router, prefix="/cog", tags=["Cloud Optimized GeoTIFF"])
add_exception_handlers(app, DEFAULT_STATUS_CODES)


@app.get("/healthz")
def ping() -> dict[str, str]:
    return {"ping": "pong"}
