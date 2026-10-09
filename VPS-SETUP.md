# VPS Server Setup — Radar Stack (Docker)

Run in order after `ssh root@YOUR_VPS_IP`:

## 1. System basics
```bash
apt update && apt upgrade -y
apt install -y git curl ufw
```

## 2. Firewall
```bash
ufw allow 22/tcp && ufw --force enable
```

## 3. Docker
```bash
curl -fsSL https://get.docker.com | sh
```

## 4. Pull the project
```bash
mkdir -p /opt/radar && cd /opt/radar
git clone https://github.com/linuxzzz69/radar.git .
```

## 5. State + secrets (NOT in git — bring them from your Mac)
```bash
# from the Mac:
scp ~/Desktop/x/watch_config.json root@YOUR_VPS_IP:/opt/radar/
```
On the VPS, `watch_config.json` must contain: telegram token + chat + watch list.
`.bot_wallet.json` regenerates via `/wallet` in Telegram (or copy from Mac).
`watcher_state.json` rebuilds itself automatically.

## 6. Launch
```bash
cd /opt/radar && docker compose up -d
docker compose ps          # both services 'running'
docker compose logs -f radar-watcher
```

## 7. Verify
- Telegram: `/status` (watched wallets), `/balance` (trading wallet)
- `docker compose logs -f radar-watcher` shows the loop

## Operations
```bash
docker compose logs -f radar-watcher   # live logs
docker compose restart radar-watcher   # after config edits
docker compose down && docker compose up -d   # full recycle
```

## Old systemd way (obsolete)
`systemctl stop/disable radar` — the Docker stack replaces it.
Downgrade: `systemctl enable --now radar` if ever needed.
