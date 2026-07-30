# Single-stage Python image, matching the pattern used by stock-picker/
# Pick-shovels (non-root runtime user via gosu, volume-mounted data dir).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      gosu \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 10001 appuser && useradd -u 10001 -g appuser -m -s /usr/sbin/nologin appuser

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
