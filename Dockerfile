FROM python:3.12-slim AS base

# Node 20 for the DBC SDK microservice
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (solders + base58 for trading, stdlib for the rest)
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

# Node deps for dbc-state
COPY radar-dbc/package.json /app/radar-dbc/package.json
RUN cd /app/radar-dbc && npm install --omit=dev --no-audit --no-fund

# Code
COPY watcher.py trading_bot.py monitor_cards.py insider_radar.py /app/
COPY radar-dbc/dbc_state.js /app/radar-dbc/dbc_state.js

# NOTE: runs as root because state files are host-mounted (root-owned).
# Acceptable for a single-tenant VPS container with no exposed ports.
WORKDIR /app
CMD ["python3", "-u", "watcher.py"]
