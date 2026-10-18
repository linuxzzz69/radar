# Server Monitor Setup (run on VPS, one-time)

## 1. Create a new Telegram bot

Open Telegram, talk to @BotFather:
```
/newbot
Name: radar-server-monitor
Username: linuxz69_monitor_bot
```
Copy the token it gives you.

## 2. Get your chat ID

Send any message to the new bot, then:
```bash
curl -s "https://api.telegram.org/bot<YOUR_NEW_TOKEN>/getUpdates" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for u in d.get('result',[]):
    m = u.get('message') or u.get('callback_query',{}).get('message',{})
    if m and m.get('chat',{}).get('id'):
        print('chat_id:', m['chat']['id'])
        break
"
```

## 3. Install on the VPS

```bash
cd /opt/radar

# create the config
cat > .server_monitor.json << 'EOF'
{
  "token": "YOUR_NEW_BOT_TOKEN",
  "chat_id": "YOUR_CHAT_ID"
}
EOF
chmod 600 .server_monitor.json

# copy the service file
cp server-monitor.service /etc/systemd/system/

# edit the service file to reference the config
# (the python script reads .server_monitor.json, so the env vars can stay empty)
sed -i 's/YOUR_BOT_TOKEN_HERE//' /etc/systemd/system/server-monitor.service
sed -i 's/YOUR_CHAT_ID_HERE//' /etc/systemd/system/server-monitor.service

# enable and start
systemctl daemon-reload
systemctl enable --now server-monitor
systemctl status server-monitor
```

## 4. Verify

You should get a message in Telegram:
```
📡 Server Monitor online
host: vultr
monitoring: SSH logins, Docker events, system health, radar errors
```

## What you'll get notified about:

| Event | Alert |
|---|---|
| SSH login | 🔐 user, IP, method, timestamp |
| 3+ failed logins in 60s | 🚨 brute force alert with IP |
| Container dies | ☠️ name, exit code |
| Container starts | ▶️ name |
| Health status change | ✅/⚠️ healthy/unhealthy |
| Disk > 85% | 💾 warning |
| Memory > 85% | 🧠 warning |
| Radar traceback in logs | 🔴 error lines |
| Every hour | 💓 heartbeat |
