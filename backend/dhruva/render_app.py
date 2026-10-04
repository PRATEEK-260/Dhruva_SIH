"""The app as Render serves it: the API under /api, with no proxy in front.

Vercel rewrites /api/* to this service with the prefix intact. Locally Caddy
strips the prefix; on Render's 512 MB instance a separate proxy process cost
memory the Copernicus fetches need, so the API is mounted under /api here
instead.
"""

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from dhruva.app import app as api

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/api", api)


@app.get("/", response_class=PlainTextResponse)
async def root() -> str:
    return "DHRUVA backend. The app is served from Vercel."
