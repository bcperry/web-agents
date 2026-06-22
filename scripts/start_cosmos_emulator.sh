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
#   AZURE_COSMOS_ENDPOINT      SDK endpoint (default http://localhost:8081/ for vnext, https://localhost:8081/ otherwise)
#   COSMOS_EMULATOR_CONTAINER  docker container name (default azure-cosmos-emulator)
#   COSMOS_EMULATOR_IMAGE      docker image (default mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:vnext-latest)
#   COSMOS_EMULATOR_DATA_PLANE_PROBE  true/false; verify SDK data plane before returning (default true)
#   COSMOS_EMULATOR_WARM_CONTAINERS true/false; pre-create app containers during probe (default false)
#   COSMOS_EMULATOR_WARM_DATABASES comma-separated extra DBs to warm when warm containers is enabled (default empty)
#   COSMOS_EMULATOR_RECREATE_ON_FAILURE remove/recreate container if restart still fails readiness (default true)
#   ENV_FILE                   path to the .env to source (default <repo>/.env)
#   AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE  classic emulator IP to advertise
#   AZURE_COSMOS_EMULATOR_PARTITION_COUNT      classic emulator partitions (default 3)
#
# Note: the classic Linux emulator advertises its container IP (e.g. 172.17.0.2) for data
# operations, which is often unreachable from the host — you'll see connection timeouts.
# If that happens, either set AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE to a host-reachable
# IP and use that same IP in AZURE_COSMOS_ENDPOINT, or use the newer image that works with
# localhost out of the box:
#   COSMOS_EMULATOR_IMAGE=mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:vnext-latest
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
EMULATOR_WELL_KNOWN_KEY="C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="

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

CONTAINER_NAME="${COSMOS_EMULATOR_CONTAINER:-azure-cosmos-emulator}"
IMAGE="${COSMOS_EMULATOR_IMAGE:-mcr.microsoft.com/cosmosdb/linux/azure-cosmos-emulator:vnext-latest}"
PARTITION_COUNT="${AZURE_COSMOS_EMULATOR_PARTITION_COUNT:-3}"
if [ -n "${AZURE_COSMOS_ENDPOINT:-}" ]; then
  ENDPOINT="${AZURE_COSMOS_ENDPOINT}"
elif [[ "${IMAGE}" == *:vnext-* ]]; then
  ENDPOINT="http://localhost:8081/"
else
  ENDPOINT="https://localhost:8081/"
fi

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

explorer_ready() {
  if [[ "${IMAGE}" == *:vnext-* ]]; then
    curl -ksf "http://localhost:8080/ready" >/dev/null 2>&1
  else
    curl -ksf "${ENDPOINT%/}/_explorer/index.html" >/dev/null 2>&1
  fi
}

data_plane_probe_enabled() {
  case "$(printf '%s' "${COSMOS_EMULATOR_DATA_PLANE_PROBE:-true}" | tr '[:upper:]' '[:lower:]')" in
    0 | false | no | off) return 1 ;;
    *) return 0 ;;
  esac
}

probe_data_plane() {
  if ! data_plane_probe_enabled; then
    return 0
  fi
  if ! command -v uv >/dev/null 2>&1; then
    echo "[cosmos-emulator] uv not found; skipping SDK data-plane probe."
    return 0
  fi

  COSMOS_PROBE_ENDPOINT="${ENDPOINT}" \
  COSMOS_PROBE_KEY="${AZURE_COSMOS_KEY:-${EMULATOR_WELL_KNOWN_KEY}}" \
  COSMOS_PROBE_DATABASE="${AZURE_COSMOS_DATABASE_NAME:-agent-memory}" \
  COSMOS_PROBE_CONTAINER="${COSMOS_EMULATOR_PROBE_CONTAINER:-__startup_probe}" \
  COSMOS_WARM_CONTAINERS="${COSMOS_EMULATOR_WARM_CONTAINERS:-false}" \
  COSMOS_WARM_DATABASES="${COSMOS_EMULATOR_WARM_DATABASES:-}" \
  COSMOS_MESSAGES_CONTAINER="${AZURE_COSMOS_CONTAINER_NAME:-chat-history}" \
  COSMOS_CONVERSATIONS_CONTAINER="${AZURE_COSMOS_CONVERSATIONS_CONTAINER:-conversations}" \
  COSMOS_AUTONOMOUS_CONTAINER="${AZURE_COSMOS_AUTONOMOUS_CONTAINER:-autonomous-runs}" \
  COSMOS_LEASES_CONTAINER="${AZURE_COSMOS_LEASES_CONTAINER:-autonomous-leases}" \
  COSMOS_DIRECTIVES_CONTAINER="${AZURE_COSMOS_DIRECTIVES_CONTAINER:-autonomous-directives}" \
  COSMOS_SKILLS_CONTAINER="${AZURE_COSMOS_SKILLS_CONTAINER:-skills}" \
  COSMOS_CUSTOM_AGENTS_CONTAINER="${AZURE_COSMOS_CUSTOM_AGENTS_CONTAINER:-custom-agents}" \
  COSMOS_AGENT_CUSTOMIZATIONS_CONTAINER="${AZURE_COSMOS_AGENT_CUSTOMIZATIONS_CONTAINER:-agent-customizations}" \
  COSMOS_USER_PROFILES_CONTAINER="${AZURE_COSMOS_USER_PROFILES_CONTAINER:-user-profiles}" \
  uv run python - <<'PY'
import asyncio
import os
import uuid

from azure.cosmos import PartitionKey
from azure.cosmos.aio import CosmosClient


async def main() -> None:
    endpoint = os.environ["COSMOS_PROBE_ENDPOINT"].rstrip("/")
    key = os.environ["COSMOS_PROBE_KEY"]
    primary_database = os.environ["COSMOS_PROBE_DATABASE"]
    extra_databases = [
        name.strip()
        for name in os.environ.get("COSMOS_WARM_DATABASES", "").split(",")
        if name.strip()
    ]
    database_names = list(dict.fromkeys([primary_database, *extra_databases]))
    warm_containers = os.environ.get("COSMOS_WARM_CONTAINERS", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    app_containers: list[tuple[str, str, int | None]] = [
        (os.environ["COSMOS_PROBE_CONTAINER"], "/id", None),
        (os.environ["COSMOS_MESSAGES_CONTAINER"], "/session_id", None),
        (os.environ["COSMOS_CONVERSATIONS_CONTAINER"], "/user_id", None),
        (os.environ["COSMOS_AUTONOMOUS_CONTAINER"], "/directive_id", None),
        (os.environ["COSMOS_LEASES_CONTAINER"], "/directive_id", -1),
        (os.environ["COSMOS_DIRECTIVES_CONTAINER"], "/id", None),
        (os.environ["COSMOS_SKILLS_CONTAINER"], "/id", None),
        (os.environ["COSMOS_CUSTOM_AGENTS_CONTAINER"], "/user_id", None),
        (os.environ["COSMOS_AGENT_CUSTOMIZATIONS_CONTAINER"], "/user_id", None),
        (os.environ["COSMOS_USER_PROFILES_CONTAINER"], "/user_id", None),
    ]

    client = CosmosClient(
        url=endpoint,
        credential=key,
        connection_verify=False,
        enable_endpoint_discovery=False,
    )
    try:
        database = await client.create_database_if_not_exists(primary_database)
        container = await database.create_container_if_not_exists(
            id=os.environ["COSMOS_PROBE_CONTAINER"],
            partition_key=PartitionKey(path="/id"),
        )
        for _ in range(3):
            item_id = f"probe-{uuid.uuid4()}"
            await container.create_item({"id": item_id, "kind": "startup-probe"})
            await container.read_item(item=item_id, partition_key=item_id)
            await container.delete_item(item_id, partition_key=item_id)

        if warm_containers:
            for database_name in database_names:
                database = await client.create_database_if_not_exists(database_name)
                for container_name, partition_path, default_ttl in app_containers:
                    kwargs = {
                        "id": container_name,
                        "partition_key": PartitionKey(path=partition_path),
                    }
                    if default_ttl is not None:
                        kwargs["default_ttl"] = default_ttl
                    await database.create_container_if_not_exists(**kwargs)
    finally:
        await client.close()


asyncio.run(main())
PY
}

wait_for_ready() {
  echo "[cosmos-emulator] waiting for ${ENDPOINT} (up to ~2 min)..."
  for _ in $(seq 1 60); do
    if explorer_ready; then
      echo "[cosmos-emulator] explorer ready."
      break
    fi
    sleep 2
  done

  if ! explorer_ready; then
    echo "[cosmos-emulator] explorer did not become ready in time." >&2
    return 1
  fi

  if data_plane_probe_enabled; then
    echo "[cosmos-emulator] checking SDK data plane..."
    probe_log="$(mktemp)"
    for _ in $(seq 1 30); do
      if probe_data_plane >"${probe_log}" 2>&1; then
        rm -f "${probe_log}"
        echo "[cosmos-emulator] ready."
        return 0
      fi
      sleep 2
    done

    echo "[cosmos-emulator] data plane did not become ready in time." >&2
    tail -n 20 "${probe_log}" >&2 || true
    rm -f "${probe_log}"
    return 1
  fi

  echo "[cosmos-emulator] ready."
  return 0
}

recreate_on_failure_enabled() {
  case "$(printf '%s' "${COSMOS_EMULATOR_RECREATE_ON_FAILURE:-true}" | tr '[:upper:]' '[:lower:]')" in
    0 | false | no | off) return 1 ;;
    *) return 0 ;;
  esac
}

container_env_value() {
  key="$1"
  "${DOCKER}" inspect "${CONTAINER_NAME}" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
    | tr -d '\r' \
    | awk -F= -v key="${key}" '$1 == key { print substr($0, length(key) + 2); exit }'
}

container_matches_config() {
  current_image="$("${DOCKER}" inspect "${CONTAINER_NAME}" --format '{{.Config.Image}}' 2>/dev/null | tr -d '\r')"

  if [ "${current_image}" != "${IMAGE}" ]; then
    echo "[cosmos-emulator] existing container image '${current_image}' does not match '${IMAGE}'."
    return 1
  fi

  if [[ "${IMAGE}" == *:vnext-* ]]; then
    for published_port in 8081/tcp 8080/tcp 1234/tcp; do
      if ! "${DOCKER}" port "${CONTAINER_NAME}" "${published_port}" >/dev/null 2>&1; then
        echo "[cosmos-emulator] existing vNext container is missing published port ${published_port}."
        return 1
      fi
    done
    return 0
  fi

  current_partition_count="$(container_env_value AZURE_COSMOS_EMULATOR_PARTITION_COUNT)"
  current_ip_override="$(container_env_value AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE)"
  if [ "${current_partition_count}" != "${PARTITION_COUNT}" ]; then
    echo "[cosmos-emulator] existing container partition count '${current_partition_count:-<unset>}' does not match '${PARTITION_COUNT}'."
    return 1
  fi
  if [ "${current_ip_override}" != "${AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE:-}" ]; then
    echo "[cosmos-emulator] existing container IP override differs from requested configuration."
    return 1
  fi
  return 0
}

create_container() {
  echo "[cosmos-emulator] creating and starting '${CONTAINER_NAME}'..."
  if [[ "${IMAGE}" == *:vnext-* ]]; then
    endpoint_protocol="${ENDPOINT%%:*}"
    case "${endpoint_protocol}" in
      http | https) ;;
      *) endpoint_protocol="http" ;;
    esac
    "${DOCKER}" run -d --name "${CONTAINER_NAME}" \
      -p 8081:8081 -p 8080:8080 -p 1234:1234 \
      "${IMAGE}" --protocol "${endpoint_protocol}" >/dev/null
    return
  fi

  EMU_ENV=(-e "AZURE_COSMOS_EMULATOR_PARTITION_COUNT=${PARTITION_COUNT}")
  if [ -n "${AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE:-}" ]; then
    EMU_ENV+=(-e "AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE=${AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE}")
  fi
  "${DOCKER}" run -d --name "${CONTAINER_NAME}" \
    -p 8081:8081 -p 10250-10255:10250-10255 \
    "${EMU_ENV[@]}" \
    "${IMAGE}" >/dev/null
}

recreate_container() {
  echo "[cosmos-emulator] recreating '${CONTAINER_NAME}' (local emulator data will be reset)..."
  "${DOCKER}" rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  create_container
}

if "${DOCKER}" ps --format '{{.Names}}' | tr -d '\r' | grep -qx "${CONTAINER_NAME}"; then
  if ! container_matches_config; then
    if recreate_on_failure_enabled; then
      recreate_container
      wait_for_ready
      exit $?
    fi
    echo "[cosmos-emulator] WARNING: existing container configuration differs; continuing because recreation is disabled."
  fi
  echo "[cosmos-emulator] '${CONTAINER_NAME}' already running; verifying readiness..."
  if wait_for_ready; then
    exit 0
  fi
  echo "[cosmos-emulator] '${CONTAINER_NAME}' did not pass readiness checks; restarting..."
  "${DOCKER}" restart "${CONTAINER_NAME}" >/dev/null
  if wait_for_ready; then
    exit 0
  fi
  if recreate_on_failure_enabled; then
    recreate_container
    wait_for_ready
    exit $?
  fi
  exit 1
fi

if "${DOCKER}" ps --format '{{.Names}}' | tr -d '\r' | grep -qx "${CONTAINER_NAME}"; then
  :
elif "${DOCKER}" ps -a --format '{{.Names}}' | tr -d '\r' | grep -qx "${CONTAINER_NAME}"; then
  if ! container_matches_config; then
    if recreate_on_failure_enabled; then
      recreate_container
      wait_for_ready
      exit $?
    fi
    echo "[cosmos-emulator] WARNING: existing container configuration differs; continuing because recreation is disabled."
  fi
  echo "[cosmos-emulator] starting existing container '${CONTAINER_NAME}'..."
  "${DOCKER}" start "${CONTAINER_NAME}" >/dev/null
else
  create_container
fi

if wait_for_ready; then
  exit 0
fi

if recreate_on_failure_enabled; then
  recreate_container
  wait_for_ready
  exit $?
fi

exit 1
