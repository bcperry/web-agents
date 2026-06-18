#!/usr/bin/env bash
#
# Start the Azure Cosmos DB Emulator (Docker) for local development — but only
# when USE_COSMOS_EMULATOR is enabled. Wired into the VS Code "Build & Run" task
# (Ctrl+Shift+B) so the emulator comes up before the backend when requested.
#
# Enable by setting USE_COSMOS_EMULATOR to a truthy value (true/1/yes/on) in your
# shell or in the repo .env (the same .env the backend reads). When unset/false
# this script is a fast no-op so the default build stays quick.
#
# Honoured environment variables:
#   USE_COSMOS_EMULATOR        gate (true/1/yes/on enables; anything else skips)
#   AZURE_COSMOS_ENDPOINT      readiness URL (default https://localhost:8081/)
#   COSMOS_EMULATOR_CONTAINER  docker container name (default azure-cosmos-emulator)
#   COSMOS_EMULATOR_IMAGE      docker image (default mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:latest)
#   ENV_FILE                   path to the .env to source (default <repo>/.env)
#   AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE  classic emulator IP to advertise
#   AZURE_COSMOS_EMULATOR_PARTITION_COUNT      partitions (default 3)
#
# Note: the classic Linux emulator advertises its container IP (e.g. 172.17.0.2) for data
# operations, which is often unreachable from the host — you'll see connection timeouts.
# If that happens, either set AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE to a host-reachable
# IP and use that same IP in AZURE_COSMOS_ENDPOINT, or use the newer image that works with
# localhost out of the box:
#   COSMOS_EMULATOR_IMAGE=mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:vnext-preview
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"

# Load .env (if present) so the flag + Cosmos settings can live alongside the
# backend's configuration. Best-effort; ignore parse errors.
if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  . "${ENV_FILE}" 2>/dev/null || true
  set +a
fi

case "$(printf '%s' "${USE_COSMOS_EMULATOR:-}" | tr '[:upper:]' '[:lower:]')" in
  1 | true | yes | on) ;;
  *)
    echo "[cosmos-emulator] USE_COSMOS_EMULATOR not enabled — skipping emulator start."
    exit 0
    ;;
esac

ENDPOINT="${AZURE_COSMOS_ENDPOINT:-https://localhost:8081/}"
CONTAINER_NAME="${COSMOS_EMULATOR_CONTAINER:-azure-cosmos-emulator}"
IMAGE="${COSMOS_EMULATOR_IMAGE:-mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:latest}"

# Pick a working Docker CLI: prefer the native Linux client, then fall back to
# the Windows Docker Desktop client (docker.exe). The fallback is handy in WSL
# when Docker Desktop is running but WSL integration isn't enabled for this
# distro. Either way, -p published ports are reachable from WSL at localhost.
DOCKER=""
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  DOCKER="docker"
elif command -v docker.exe >/dev/null 2>&1 && docker.exe info >/dev/null 2>&1; then
  DOCKER="docker.exe"
  echo "[cosmos-emulator] Native WSL docker not reachable; using Docker Desktop via docker.exe."
fi

if [ -z "${DOCKER}" ]; then
  echo "[cosmos-emulator] WARNING: no reachable Docker daemon — skipping emulator start."
  echo "[cosmos-emulator]   Docker Desktop on Windows: start it AND enable WSL integration for this"
  echo "[cosmos-emulator]   distro (Settings > Resources > WSL Integration); or native Linux/WSL:"
  echo "[cosmos-emulator]   'sudo service docker start'. The backend will still launch."
  exit 0
fi

if "${DOCKER}" ps --format '{{.Names}}' | tr -d '\r' | grep -qx "${CONTAINER_NAME}"; then
  echo "[cosmos-emulator] '${CONTAINER_NAME}' already running."
  exit 0
fi

if "${DOCKER}" ps -a --format '{{.Names}}' | tr -d '\r' | grep -qx "${CONTAINER_NAME}"; then
  echo "[cosmos-emulator] starting existing container '${CONTAINER_NAME}'..."
  "${DOCKER}" start "${CONTAINER_NAME}" >/dev/null
else
  echo "[cosmos-emulator] creating and starting '${CONTAINER_NAME}'..."
  EMU_ENV=(-e "AZURE_COSMOS_EMULATOR_PARTITION_COUNT=${AZURE_COSMOS_EMULATOR_PARTITION_COUNT:-3}")
  if [ -n "${AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE:-}" ]; then
    EMU_ENV+=(-e "AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE=${AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE}")
  fi
  "${DOCKER}" run -d --name "${CONTAINER_NAME}" \
    -p 8081:8081 -p 10250-10255:10250-10255 \
    "${EMU_ENV[@]}" \
    "${IMAGE}" >/dev/null
fi

echo "[cosmos-emulator] waiting for ${ENDPOINT} (up to ~2 min)..."
for _ in $(seq 1 60); do
  if curl -ksf "${ENDPOINT%/}/_explorer/index.html" >/dev/null 2>&1; then
    echo "[cosmos-emulator] ready."
    exit 0
  fi
  sleep 2
done

echo "[cosmos-emulator] did not become ready in time." >&2
exit 1
