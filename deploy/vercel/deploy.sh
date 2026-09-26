#!/usr/bin/env bash
# Deploys the frontend to the Vercel project "dhruva".
#   deploy/vercel/deploy.sh          production
#   deploy/vercel/deploy.sh preview  preview URL only
#
# The frontend bundles the codebook from data/codebook/build/ at the repo root,
# so uploading frontend/ alone fails to build. This stages exactly those two
# trees with their relative layout intact and nothing else: no backend, no
# .env, no docs. Vercel serves only frontend/dist from the build.
set -euo pipefail
cd "$(dirname "$0")/../.."

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

tar -c --exclude node_modules --exclude dist --exclude .vercel --exclude '.env*' frontend | tar -x -C "$STAGE"
mkdir -p "$STAGE/data/codebook"
cp -r data/codebook/build "$STAGE/data/codebook/build"
cp deploy/vercel/vercel.json "$STAGE/vercel.json"

# Reuse the project link so every run deploys to the same project.
if [[ -d deploy/vercel/.vercel ]]; then
	cp -r deploy/vercel/.vercel "$STAGE/.vercel"
else
	(cd "$STAGE" && npx --yes vercel@latest link --yes --project dhruva)
	cp -r "$STAGE/.vercel" deploy/vercel/.vercel
fi

if [[ ${1:-prod} == preview ]]; then
	(cd "$STAGE" && npx --yes vercel@latest deploy --yes)
else
	(cd "$STAGE" && npx --yes vercel@latest deploy --prod --yes)
fi
