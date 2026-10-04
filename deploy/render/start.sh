#!/usr/bin/env bash
# Starts the backend inside one Render container: Postgres and the API. The
# database was built into the image, so this only starts processes.
#
# Slimmed on 4 Oct for the free instance's 512 MB: no Redis (only the health
# check used it), no Caddy (the API serves /api itself, dhruva/render_app.py),
# no TiTiler (the map layers are static images on Vercel), and Postgres without
# the TimescaleDB preload (no feature uses it). That memory now holds the
# Copernicus fetches.
set -euo pipefail

pg_ctl -D "$PGDATA" -w -l /tmp/postgres.log -o "-c listen_addresses=127.0.0.1 \
	-c unix_socket_directories=/tmp -c shared_buffers=32MB -c max_connections=20" start

export DATABASE_URL=postgresql://dhruva@127.0.0.1:5432/dhruva
export REDIS_URL=none
API=http://127.0.0.1:$PORT/api

# The API listens on $PORT; Render marks the deploy live once it answers.
(cd /app/backend && exec /opt/api/bin/uvicorn dhruva.render_app:app --host 0.0.0.0 --port "$PORT") &
api=$!

# The first advisory after boot takes ~20 s on 0.1 CPU (lazy imports, first
# fetch); later ones ~2 s. Spend that on a warm-up request, not on a judge.
# log=false keeps it out of the advisory log the shore console shows.
(
	until curl -sf -o /dev/null "$API/health"; do sleep 2; done
	curl -s -o /dev/null -m 180 -X POST "$API/advisory" -H 'content-type: application/json' \
		-d '{"query":"warm-up","lat":11.05,"lon":79.95,"language":"en","boat_class":"frp_under_12m","log":false}' ||
		true
	# Then seed the request log (see seed-requests.txt): real verdicts from live
	# data, simulated askers. The comment line and the "(near)" hint are skipped.
	grep -v '^#' /app/seed-requests.txt | while read -r lat lon boat_class language _; do
		[[ -n $lat ]] || continue
		curl -s -o /dev/null -m 120 -X POST "$API/advisory" -H 'content-type: application/json' \
			-d "{\"query\":\"Is it safe to go fishing today?\",\"lat\":$lat,\"lon\":$lon,\"language\":\"$language\",\"boat_class\":\"$boat_class\",\"log\":true}" ||
			true
	done
) &

# INCOIS PFZ lines and IMD's National Bulletins: no feed exists for either, so
# both are read now and every 30 minutes. IMD's archive listing is read now
# and every 30 minutes (dhruva/sources/imd_feed.py). A failed check is recorded
# and the answer says how old the last good one is. Not waited on: a failed
# check must not restart the backend.
(
	cd /app/backend
	until curl -sf -o /dev/null "$API/health"; do sleep 2; done
	while true; do
		# INCOIS fishing-zone lines: the image's snapshot goes stale in 3 days
		# (an older advisory is not shown), so read INCOIS's map service again.
		# A failed read keeps the last lines; they still expire by their date.
		/opt/api/bin/python -m dhruva.sources.pfz_wfs >>/tmp/pfz_wfs.log 2>&1 || true
		/opt/api/bin/python -m dhruva.sources.imd_feed >>/tmp/imd_feed.log 2>&1 || true
		# Warm the Copernicus answers for the demo places. On 0.1 CPU a first
		# fetch takes over two minutes, past Vercel's limit for a proxied
		# request; results are cached per place and day, so a later ask there
		# answers in seconds. Cheap when already warm; refetches on a new day.
		for spot in "11.05 79.95" "20.85 70.25"; do
			set -- $spot
			for q in "Why are there fewer fish here?" "Where is the water with high chlorophyll and good temperature?"; do
				curl -s -o /dev/null -m 600 -X POST "$API/advisory" -H 'content-type: application/json' \
					-d "{\"query\":\"$q\",\"lat\":$1,\"lon\":$2,\"language\":\"en\",\"log\":false}" || true
			done
		done
		sleep 1800
	done
) &

# If the API dies, exit so Render restarts the container instead of serving
# nothing.
wait "$api"
echo "the api exited; stopping" >&2
exit 1
