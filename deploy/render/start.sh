#!/usr/bin/env bash
# Starts the backend inside one Render container. The database was built into
# the image, so this only starts processes.
set -euo pipefail

# Small settings for a 512 MB instance.
pg_ctl -D "$PGDATA" -w -l /tmp/postgres.log -o "-c listen_addresses=127.0.0.1 \
	-c shared_preload_libraries=timescaledb -c unix_socket_directories=/tmp \
	-c shared_buffers=32MB -c max_connections=20 -c timescaledb.telemetry_level=off" start

redis-server --bind 127.0.0.1 --save "" --appendonly no --maxmemory 32mb --daemonize yes

export DATABASE_URL=postgresql://dhruva@127.0.0.1:5432/dhruva
export REDIS_URL=redis://127.0.0.1:6379/0

# Caddy first: Render marks the deploy live once $PORT answers.
caddy run --config /app/Caddyfile --adapter caddyfile &
pids=($!)
(cd /app/titiler && exec /opt/titiler/bin/uvicorn main:app --host 127.0.0.1 --port 8001 --root-path /tiles) &
pids+=($!)
(cd /app/backend && exec /opt/api/bin/uvicorn dhruva.app:app --host 127.0.0.1 --port 8000) &
pids+=($!)

# The first advisory after boot takes ~20 s on 0.1 CPU (lazy imports, first
# fetch); later ones ~2 s. Spend that on a warm-up request, not on a judge.
# log=false keeps it out of the advisory log the shore console shows.
(
	until curl -sf -o /dev/null http://127.0.0.1:8000/health; do sleep 2; done
	curl -s -o /dev/null -m 180 -X POST http://127.0.0.1:8000/advisory -H 'content-type: application/json' \
		-d '{"query":"warm-up","lat":11.05,"lon":79.95,"language":"en","boat_class":"frp_under_12m","log":false}' ||
		true
) &

# If any service dies (the warm-up job is not one), exit so Render restarts the container instead of
# serving half a backend.
wait -n "${pids[@]}"
echo "a service exited; stopping" >&2
exit 1
