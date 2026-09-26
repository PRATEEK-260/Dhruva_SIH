#!/usr/bin/env bash
# Build on this machine, ship to the server, start the stack there.
#   deploy/push.sh ubuntu@<public-ip>
# Re-runnable: every step overwrites the previous deploy.
#
# The boundary tables are copied from the local database, so the local stack
# must be up (docker compose up -d) with the Marine Regions layers loaded.
set -euo pipefail

HOST=${1:?usage: deploy/push.sh user@host}
IP=${HOST#*@}
# No domain: sslip.io resolves 1-2-3-4.sslip.io to 1.2.3.4, and Caddy gets a
# real certificate for it.
SITE=${SITE_ADDRESS:-${IP//./-}.sslip.io}
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
cd "$(dirname "$0")/.."

remote_arch=$(ssh "$HOST" uname -m)
if [[ $remote_arch != "$(uname -m)" ]]; then
	echo "server is $remote_arch, this machine is $(uname -m): images would need docker buildx --platform" >&2
	exit 1
fi

echo "==> frontend build"
(cd frontend && npm run build)

echo "==> image build"
docker compose build api titiler

echo "==> sync files"
rsync -azR --delete \
	--exclude '__pycache__' --exclude '.venv' --exclude '.pytest_cache' --exclude '.ruff_cache' \
	./docker-compose.yml ./docker-compose.prod.yml ./deploy ./data ./backend ./titiler ./frontend/dist \
	"$HOST:dhruva/"

if ! ssh "$HOST" test -f dhruva/.env; then
	echo "==> first deploy: copying .env"
	scp -q .env "$HOST:dhruva/.env"
fi
ssh "$HOST" "cd dhruva && sed -i '/^SITE_ADDRESS=/d' .env && echo 'SITE_ADDRESS=$SITE' >> .env"

echo "==> ship images (slow on the first run)"
docker save dhruva-api dhruva-titiler | gzip | ssh "$HOST" 'gunzip | docker load'

echo "==> start"
ssh "$HOST" "cd dhruva && $COMPOSE up -d --wait --wait-timeout 600"

echo "==> copy boundary and PFZ tables"
docker compose exec -T postgres pg_dump -U dhruva -d dhruva --clean --if-exists --no-owner \
	-t maritime_zone -t boundary_line -t pfz_advisory |
	ssh "$HOST" "cd dhruva && $COMPOSE exec -T postgres psql -q -U dhruva -d dhruva" >/dev/null

echo "==> smoke test"
ssh "$HOST" "cd dhruva && $COMPOSE ps --format '{{.Service}}\t{{.Status}}'"
curl -fsS --retry 5 --retry-delay 5 "https://$SITE/api/health/ready"
echo
echo "live: https://$SITE/boat   https://$SITE/shore"
