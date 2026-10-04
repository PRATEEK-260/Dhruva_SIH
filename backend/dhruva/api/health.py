"""Liveness and readiness.

/health answers whether the process is up. /health/ready answers whether it can
actually do work, and returns 503 when it cannot — a readiness probe that always
returns 200 is a readiness probe that never tells you anything.
"""

import os

import asyncpg
from fastapi import APIRouter, Response

from dhruva.config import settings

router = APIRouter(tags=["health"])

# The plan puts geofencing, advisory RAG and vessel tracks in one engine.
# If any of these is missing the engine cannot do the job it was chosen for.
# Render's 512 MB image runs PostGIS only (DHRUVA_REQUIRED_EXTENSIONS=postgis):
# no feature uses the other two yet, and their memory went to Copernicus.
REQUIRED_EXTENSIONS = tuple(
    os.environ.get("DHRUVA_REQUIRED_EXTENSIONS", "postgis,vector,timescaledb").split(",")
)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "env": settings.env}


@router.get("/health/ready")
async def ready(response: Response) -> dict[str, object]:
    checks: dict[str, object] = {}
    ok = True

    try:
        conn = await asyncpg.connect(settings.database_url, timeout=5)
        try:
            await conn.fetchval("SELECT 1")
            installed = {r["extname"] for r in await conn.fetch("SELECT extname FROM pg_extension")}
            missing = [e for e in REQUIRED_EXTENSIONS if e not in installed]
            checks["postgres"] = {
                "ok": not missing,
                "extensions": sorted(installed & set(REQUIRED_EXTENSIONS)),
                "missing": missing,
            }
            ok = ok and not missing
        finally:
            await conn.close()
    except Exception as exc:
        checks["postgres"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        ok = False

    # Only the health check uses Redis; a deployment without it says so
    # (REDIS_URL=none) rather than failing readiness over an unused service.
    if settings.redis_url.lower() == "none":
        checks["redis"] = {"ok": True, "skipped": "not deployed"}
        if not ok:
            response.status_code = 503
        return {"ready": ok, "checks": checks}
    import redis.asyncio as aioredis

    try:
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        try:
            await r.ping()
            checks["redis"] = {"ok": True}
        finally:
            await r.aclose()
    except Exception as exc:
        checks["redis"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        ok = False

    if not ok:
        response.status_code = 503
    return {"ready": ok, "checks": checks}
