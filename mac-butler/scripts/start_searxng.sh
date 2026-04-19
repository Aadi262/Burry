#!/bin/bash

set -u

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running. Start Docker first."
  exit 1
fi

docker stop searxng >/dev/null 2>&1 || true
docker rm searxng >/dev/null 2>&1 || true

SEARXNG_PORT="${SEARXNG_PORT:-18080}"
SEARXNG_URL="http://127.0.0.1:${SEARXNG_PORT}"

if ! docker run -d --name searxng -p "${SEARXNG_PORT}:8080" \
  -e SEARXNG_SECRET=butler-secret \
  -v "$(pwd)/docker/searxng/settings.yml:/etc/searxng/settings.yml" \
  -v "$(pwd)/docker/searxng/limiter.toml:/etc/searxng/limiter.toml" \
  searxng/searxng >/dev/null; then
  echo "Failed to start the SearXNG container."
  exit 1
fi

sleep 2

if curl -fsS "${SEARXNG_URL}/search?q=butler-health&format=json" >/dev/null 2>&1; then
  echo "SearXNG started at ${SEARXNG_URL}"
  exit 0
fi

echo "SearXNG container started but the service is not responding on ${SEARXNG_URL}"
exit 1
