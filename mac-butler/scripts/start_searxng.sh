#!/bin/bash

docker stop searxng 2>/dev/null
docker rm searxng 2>/dev/null
docker run -d --name searxng -p 8080:8080 \
  -e SEARXNG_SECRET=butler-secret \
  -v "$(pwd)/docker/searxng/settings.yml:/etc/searxng/settings.yml" \
  -v "$(pwd)/docker/searxng/limiter.toml:/etc/searxng/limiter.toml" \
  searxng/searxng
echo "SearXNG started at http://localhost:8080"
