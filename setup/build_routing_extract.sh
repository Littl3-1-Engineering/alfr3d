#!/usr/bin/env bash
# SA-6: build a regional OSRM dataset for self-hosted routing (see
# todo/todo_self_hosted_routing.md for the Phase 0 spike this implements, including the real
# preprocessing numbers this script's own steps reproduce).
#
# The Kit ships to unknown geographies, so this derives a region sized to wherever the
# household actually is, not a hardcoded place -- via BBBike's (https://bbbike.org) predefined
# city extracts, a direct synchronous download. This is the exact pipeline proven live against
# real production hardware in Phase 0 (a 98MB Toronto extract preprocessed in under 2 minutes).
#
# Usage:
#   ROUTING_CITY=Toronto ./build_routing_extract.sh
#
# Output: ./routing_data/${ROUTING_REGION_NAME:-region}.osrm* -- exactly what the `routing`
# service in docker-compose.yml (profile "routing") expects to find mounted at /data.
#
# If the household's city isn't in BBBike's ~250-city list (see
# https://download.bbbike.org/osm/bbbike/ for the supported names), this script stops rather
# than guess at an automated alternative -- see "Not yet done" in todo_self_hosted_routing.md
# for the manual osmium-extract-from-a-larger-region path that covers that case, which this
# pass scoped but did not build and verify end-to-end.

set -euo pipefail

: "${ROUTING_CITY:?Set ROUTING_CITY to a name from https://download.bbbike.org/osm/bbbike/ (e.g. Toronto)}"

REGION_NAME="${ROUTING_REGION_NAME:-region}"
OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/routing_data"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

OSRM_IMAGE="ghcr.io/project-osrm/osrm-backend:latest"

mkdir -p "$OUT_DIR"

echo "Fetching BBBike predefined extract for city: ${ROUTING_CITY}"
EXTRACT_URL="https://download.bbbike.org/osm/bbbike/${ROUTING_CITY}/${ROUTING_CITY}.osm.pbf"
curl -f -s -o "${WORK_DIR}/${REGION_NAME}.osm.pbf" "$EXTRACT_URL" || {
  echo "No BBBike extract found for '${ROUTING_CITY}' -- see https://download.bbbike.org/osm/bbbike/ for the supported list." >&2
  exit 1
}

echo "Preprocessing with osrm-extract/partition/customize (MLD)..."
docker run --rm -v "${WORK_DIR}:/data" "$OSRM_IMAGE" \
  osrm-extract -p /opt/car.lua "/data/${REGION_NAME}.osm.pbf"
docker run --rm -v "${WORK_DIR}:/data" "$OSRM_IMAGE" \
  osrm-partition "/data/${REGION_NAME}.osrm"
docker run --rm -v "${WORK_DIR}:/data" "$OSRM_IMAGE" \
  osrm-customize "/data/${REGION_NAME}.osrm"

echo "Copying processed dataset to ${OUT_DIR}"
# osrm-customize writes some output files (e.g. *.osrm.fileIndex) root-owned and 0700 inside the
# container -- unreadable by this script's own user on the host bind mount. Fix permissions via a
# throwaway container (a minimal, definitely-available image, not assuming osrm-backend's own
# minimal base carries chmod/a shell) before copying out.
docker run --rm -v "${WORK_DIR}:/data" alpine sh -c "chmod -R a+r /data/${REGION_NAME}.osrm*"
cp "${WORK_DIR}/${REGION_NAME}.osrm"* "$OUT_DIR/"

echo "Done. Start the routing service with: ROUTING_REGION_NAME=${REGION_NAME} docker compose --profile routing up -d routing"
