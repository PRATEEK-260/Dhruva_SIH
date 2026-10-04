# Backend for Render's free web service (512 MB, 0.1 CPU). One container runs
# Postgres (PostGIS) and the API; the frontend, including the map's satellite
# layers as static images, is on Vercel and reaches this service through a
# vercel.json rewrite of /api.
#
# Slimmed on 4 Oct: Redis, Caddy, TiTiler, TimescaleDB and pgvector are not in
# this image (the local docker-compose stack keeps them). With them, the
# Copernicus fetches ran the instance out of memory.
# Build context is the repository root:
#   docker build -f deploy/render/Dockerfile .
FROM python:3.12-slim-bookworm

RUN apt-get update \
	&& apt-get install -y --no-install-recommends curl ca-certificates postgresql-common \
	&& /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
	&& apt-get install -y --no-install-recommends postgresql-16 postgresql-16-postgis-3 \
	&& rm -rf /var/lib/apt/lists/*
ENV PATH=/usr/lib/postgresql/16/bin:$PATH

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_NO_CACHE=1
RUN uv venv -p /usr/local/bin/python3.12 /opt/api

COPY backend/pyproject.toml /app/backend/
COPY backend/dhruva/__init__.py /app/backend/dhruva/
RUN VIRTUAL_ENV=/opt/api uv pip install -e "/app/backend[data,geo,graph]"

COPY backend/dhruva /app/backend/dhruva
COPY data /data
COPY deploy/render/start.sh deploy/render/boundaries.sql deploy/render/pfz.sql deploy/render/seed-requests.txt /app/

RUN useradd -u 1000 -m app && chmod +x /app/start.sh && chown -R app:app /app /data
USER app

# Build the database into the image. On 0.1 CPU, initdb plus the boundary
# restore at every wake-up would add a minute to each cold start. pfz.sql holds the
# INCOIS PFZ lines and landing centres as last fetched locally; refresh it with
# `python -m dhruva.sources.pfz_wfs`, then pg_dump -t pfz_line -t landing_centre.
ENV PGDATA=/home/app/pgdata
RUN initdb -U dhruva --auth=trust -D "$PGDATA" >/dev/null \
	&& pg_ctl -D "$PGDATA" -w -o "-c unix_socket_directories=/tmp -c listen_addresses=127.0.0.1" start \
	&& psql -h 127.0.0.1 -U dhruva -d postgres -q -c "CREATE DATABASE dhruva" \
	&& psql -h 127.0.0.1 -U dhruva -d dhruva -q -v ON_ERROR_STOP=1 \
		-c "CREATE EXTENSION postgis" \
		-f /app/boundaries.sql -f /app/pfz.sql >/dev/null \
	&& pg_ctl -D "$PGDATA" -w stop

# DHRUVA_COPERNICUS_SUBPROCESS=1: each Copernicus fetch runs in a process that
# exits when done. In process, every new place asked left 60-140 MB behind and
# the 512 MB instance died after a few; a child gives it all back.
ENV DHRUVA_DATA_DIR=/data DHRUVA_REGISTRY=/data/registry.yaml ENV=prod PORT=10000 \
	DHRUVA_REQUIRED_EXTENSIONS=postgis DHRUVA_COPERNICUS_SUBPROCESS=1 \
	INCOIS_CA_BUNDLE=/data/ca/incois-bundle.pem
EXPOSE 10000
CMD ["/app/start.sh"]
