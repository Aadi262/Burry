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

if ! docker run -d --name searxng -p 8080:8080 \
  -e SEARXNG_SECRET=butler-secret \
  -v "$(pwd)/docker/searxng/settings.yml:/etc/searxng/settings.yml" \
  -v "$(pwd)/docker/searxng/limiter.toml:/etc/searxng/limiter.toml" \
  searxng/searxng >/dev/null; then
  echo "Failed to start the SearXNG container."
  exit 1
fi

sleep 2

if curl -fsS http://127.0.0.1:8080/ >/dev/null 2>&1; then
  echo "SearXNG started at http://localhost:8080"
  exit 0
fi

echo "SearXNG container started but the service is not responding on http://localhost:8080"
exit 1
