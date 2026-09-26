# Backend for Render's free web service (512 MB, 0.1 CPU). One container runs
# Postgres, Redis, the API, TiTiler and Caddy; the frontend is on Vercel and
# reaches this service through vercel.json rewrites of /api and /tiles.
# Build context is the repository root:
#   docker build -f deploy/render/Dockerfile .
FROM python:3.12-slim-bookworm

# Postgres 16 with PostGIS, pgvector and TimescaleDB — the same engine the
# compose stack runs, from the PGDG and Timescale apt repositories.
RUN apt-get update \
	&& apt-get install -y --no-install-recommends curl ca-certificates gnupg postgresql-common \
	&& /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
	&& curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /usr/share/keyrings/timescale.gpg \
	&& echo "deb [signed-by=/usr/share/keyrings/timescale.gpg] https://packagecloud.io/timescale/timescaledb/debian/ bookworm main" \
		>/etc/apt/sources.list.d/timescale.list \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		postgresql-16 postgresql-16-postgis-3 postgresql-16-pgvector timescaledb-2-postgresql-16 redis-server \
	&& apt-get purge -y gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
ENV PATH=/usr/lib/postgresql/16/bin:$PATH

COPY --from=caddy:2-alpine /usr/bin/caddy /usr/local/bin/caddy
# The official binary carries cap_net_bind_service=ep. BuildKit keeps that
# xattr, and Render's runtime cannot grant it, so exec fails with "Operation
# not permitted". Caddy listens on $PORT (10000) and needs no capability.
RUN python3 -c "import os; p='/usr/local/bin/caddy'; 'security.capability' in os.listxattr(p) and os.removexattr(p, 'security.capability'); assert not os.listxattr(p), os.listxattr(p)"
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_NO_CACHE=1
RUN uv venv -p /usr/local/bin/python3.12 /opt/api && uv venv -p /usr/local/bin/python3.12 /opt/titiler

COPY titiler/requirements.txt /app/titiler/
RUN VIRTUAL_ENV=/opt/titiler uv pip install -r /app/titiler/requirements.txt

COPY backend/pyproject.toml /app/backend/
COPY backend/dhruva/__init__.py /app/backend/dhruva/
RUN VIRTUAL_ENV=/opt/api uv pip install -e "/app/backend[data,geo,graph]"

COPY backend/dhruva /app/backend/dhruva
COPY titiler/main.py /app/titiler/
# TiTiler is handed file:///data/cogs/... by the frontend, and the api reads
# DHRUVA_DATA_DIR/cogs; one /data serves both.
COPY data /data
COPY deploy/render/Caddyfile deploy/render/start.sh deploy/render/boundaries.sql /app/

RUN useradd -u 1000 -m app && chmod +x /app/start.sh && chown -R app:app /app /data
USER app

# Build the database into the image. On 0.1 CPU, initdb plus the boundary
# restore at every wake-up would add a minute to each cold start.
ENV PGDATA=/home/app/pgdata
RUN initdb -U dhruva --auth=trust -D "$PGDATA" >/dev/null \
	&& pg_ctl -D "$PGDATA" -w -o "-c shared_preload_libraries=timescaledb -c unix_socket_directories=/tmp -c listen_addresses=127.0.0.1" start \
	&& psql -h 127.0.0.1 -U dhruva -d postgres -q -c "CREATE DATABASE dhruva" \
	&& psql -h 127.0.0.1 -U dhruva -d dhruva -q -v ON_ERROR_STOP=1 \
		-c "CREATE EXTENSION postgis" -c "CREATE EXTENSION vector" -c "CREATE EXTENSION timescaledb" \
		-f /app/boundaries.sql >/dev/null \
	&& pg_ctl -D "$PGDATA" -w stop

ENV DHRUVA_DATA_DIR=/data DHRUVA_REGISTRY=/data/registry.yaml ENV=prod \
	XDG_DATA_HOME=/tmp/caddy XDG_CONFIG_HOME=/tmp/caddy PORT=10000
EXPOSE 10000
CMD ["/app/start.sh"]
