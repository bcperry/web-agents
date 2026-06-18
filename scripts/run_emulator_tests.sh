#!/usr/bin/env bash
#
# Run the Cosmos emulator-backed integration tests (`@pytest.mark.emulator`).
#
# Starts the Azure Cosmos DB Emulator in Docker if it is not already running,
# exports the well-known emulator endpoint/key (a public, fixed value — not a
# secret), then runs the emulator-marked test tier. Any extra args are passed
# through to pytest.
#
# Usage:
#   scripts/run_emulator_tests.sh [extra pytest args]
set -euo pipefail

ENDPOINT="${AZURE_COSMOS_EMULATOR_ENDPOINT:-https://localhost:8081/}"
KEY="${AZURE_COSMOS_KEY:-C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==}"
CONTAINER_NAME="azure-cosmos-emulator"
IMAGE="mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:latest"

if command -v docker >/dev/null 2>&1; then
  if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Starting Azure Cosmos DB Emulator (${CONTAINER_NAME})..."
    docker run -d --name "${CONTAINER_NAME}" \
      -p 8081:8081 -p 10250-10255:10250-10255 \
      "${IMAGE}" >/dev/null
    echo "Waiting for the emulator to accept connections (up to ~2 min)..."
    for _ in $(seq 1 60); do
      if curl -ksf "${ENDPOINT}_explorer/index.html" >/dev/null 2>&1; then
        break
      fi
      sleep 2
    done
  fi
else
  echo "docker not found; assuming an emulator is already reachable at ${ENDPOINT}" >&2
fi

export AZURE_COSMOS_ENDPOINT="${ENDPOINT}"
export AZURE_COSMOS_EMULATOR_ENDPOINT="${ENDPOINT}"
export AZURE_COSMOS_KEY="${KEY}"
export AZURE_COSMOS_DATABASE_NAME="${AZURE_COSMOS_DATABASE_NAME:-agent-memory-test}"
export AZURE_COSMOS_CONTAINER_NAME="${AZURE_COSMOS_CONTAINER_NAME:-chat-history-test}"
export AZURE_COSMOS_CONVERSATIONS_CONTAINER="${AZURE_COSMOS_CONVERSATIONS_CONTAINER:-conversations-test}"

echo "Running emulator integration tests against ${ENDPOINT}..."
exec uv run pytest -m emulator -v "$@"
