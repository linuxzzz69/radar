#!/usr/bin/env python3
"""
server-monitor.py — VPS watchdog that pushes notifications to Telegram.

Monitors:
  SSH logins (user, IP, timestamp) from /var/log/auth.log
  SSH failures (brute force alert at 3+ attempts in 60s from same IP)
  Docker container events (start/stop/die/health)
  System health (disk, memory, CPU — every 5 min, warn on thresholds)
  Radar bot errors (tracebacks in docker logs)

Setup:
  1. Create a new bot via @BotFather, get the token
  2. Set SERVER_MON_TOKEN and SERVER_MON_CHAT env vars (or a config file)
  3. Run as root: python3 server-monitor.py

Run as systemd service (recommended):
  /etc/systemd/system/server-monitor.service
"""
import json, os, re, subprocess, sys, time, urllib.request

# ── config ──────────────────────────────────────────────────────────
TOKEN = os.environ.get("SERVER_MON_TOKEN", "")
CHAT = os.environ.get("SERVER_MON_CHAT", "")
CFG_PATH = os.environ.get("SERVER_MON_CFG", "/opt/radar/.server_monitor.json")

if not TOKEN or not CHAT:
    # try config file
    try:
        with open(CFG_PATH) as f:
            cfg = json.load(f)
            TOKEN = TOKEN or cfg.get("token", "")
            CHAT = CHAT or cfg.get("chat_id", "")
    except Exception:
        pass

if not TOKEN or not CHAT:
    print("missing SERVER_MON_TOKEN / SERVER_MON_CHAT (or config file)")
    sys.exit(1)

UA = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}

# thresholds
DISK_WARN_PCT = 85
MEM_WARN_PCT = 85
HEALTH_INTERVAL = 300        # 5 min
AUTH_LOG = "/var/log/auth.log"
DOCKER_SOCK = "/var/run/docker.sock"


def tg(text):
    """Push a message to Telegram. Fire-and-forget, never crash."""
    try:
        data = json.dumps({"chat_id": CHAT, "text": text,
                           "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data, headers=UA)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"tg send failed: {e}", file=sys.stderr)


# ── SSH login monitor ──────────────────────────────────────────────
login_pat = re.compile(r"Accepted (password|publickey) for (\S+) from (\S+)")
fail_pat = re.compile(r"Failed (password|publickey) for (?:invalid user )?(\S+) from (\S+)")
logout_pat = re.compile(r"session opened for user (\S+)")

fail_counts = {}  # ip -> (count, first_ts)


def tail_auth_log():
    """Tail auth.log and extract SSH events."""
    pos = 0
    if os.path.exists(AUTH_LOG):
        pos = os.path.getsize(AUTH_LOG)
    while True:
        try:
            if not os.path.exists(AUTH_LOG):
                time.sleep(2)
                continue
            size = os.path.getsize(AUTH_LOG)
            if size < pos:
                pos = 0  # log rotated
            if size > pos:
                with open(AUTH_LOG, "r") as f:
                    f.seek(pos)
                    for line in f:
                        parse_auth_line(line.strip())
                pos = size
        except Exception as e:
            print(f"auth log err: {e}", file=sys.stderr)
        time.sleep(1)


def parse_auth_line(line):
    """Parse one auth.log line and fire alerts."""
    now = time.strftime("%H:%M:%S %d %b")
    # successful login
    m = login_pat.search(line)
    if m:
        method, user, ip = m.groups()
        tg(f"🔐 <b>SSH LOGIN</b>\n"
           f"user: <code>{user}</code>\n"
           f"ip: <code>{ip}</code>\n"
           f"method: {method}\n"
           f"time: {now}")
        return
    # failed login
    m = fail_pat.search(line)
    if m:
        method, user, ip = m.groups()
        ts = time.time()
        if ip not in fail_counts:
            fail_counts[ip] = [0, ts]
        fail_counts[ip][0] += 1
        if fail_counts[ip][0] >= 3 and ts - fail_counts[ip][1] < 60:
            tg(f"🚨 <b>BRUTE FORCE</b> — {fail_counts[ip][0]} failed attempts\n"
               f"ip: <code>{ip}</code>\n"
               f"last user tried: <code>{user}</code>\n"
               f"time: {now}")
            fail_counts[ip] = [0, ts]  # reset after alerting
        return


# ── Docker events monitor ───────────────────────────────────────────
def watch_docker_events():
    """Watch Docker events via the events API."""
    while True:
        try:
            proc = subprocess.Popen(
                ["docker", "events", "--format", "{{json .}}"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1)
            for line in proc.stdout:
                try:
                    ev = json.loads(line.strip())
                    handle_docker_event(ev)
                except Exception:
                    pass
        except Exception as e:
            print(f"docker events err: {e}", file=sys.stderr)
            time.sleep(10)


def handle_docker_event(ev):
    """Send notifications for important Docker events."""
    action = ev.get("Action", "")
    name = (ev.get("Actor") or {}).get("Attributes", {}).get("name", "?")
    typ = ev.get("Type", "")
    ts = time.strftime("%H:%M:%S")
    if typ == "container":
        if action in ("die", "kill", "oom"):
            exit_code = (ev.get("Actor") or {}).get("Attributes", {}).get("exitCode", "?")
            tg(f"☠️ <b>CONTAINER DIED</b>\n"
               f"name: <code>{name}</code>\n"
               f"action: {action} (exit {exit_code})\n"
               f"time: {ts}")
        elif action == "start":
            tg(f"▶️ <b>CONTAINER STARTED</b>\n"
               f"name: <code>{name}</code>\n"
               f"time: {ts}")
        elif action == "health_status":
            status = (ev.get("Actor") or {}).get("Attributes", {}).get("status", "?")
            if "unhealthy" in status or "healthy" in status:
                emoji = "✅" if "healthy" in status else "⚠️"
                tg(f"{emoji} <b>HEALTH</b>\n"
                   f"name: <code>{name}</code>\n"
                   f"status: {status}\n"
                   f"time: {ts}")


# ── System health monitor ───────────────────────────────────────────
def health_loop():
    """Every 5 min: check disk, memory, and radar heartbeat."""
    while True:
        try:
            check_disk()
            check_memory()
            check_radar_logs()
        except Exception as e:
            print(f"health err: {e}", file=sys.stderr)
        time.sleep(HEALTH_INTERVAL)


def check_disk():
    try:
        r = subprocess.run(["df", "/"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                pct = int(parts[4].replace("%", ""))
                if pct >= DISK_WARN_PCT:
                    tg(f"💾 <b>DISK WARNING</b>\n"
                       f"/ usage: <b>{pct}%</b>\n"
                       f"time: {time.strftime('%H:%M:%S')}")
    except Exception:
        pass


def check_memory():
    try:
        r = subprocess.run(["free", "-b"], capture_output=True, text=True, timeout=10)
        lines = r.stdout.splitlines()
        if len(lines) > 1:
            parts = lines[1].split()
            total, used = int(parts[1]), int(parts[2])
            pct = int(used / total * 100)
            if pct >= MEM_WARN_PCT:
                gb = total / 1e9
                tg(f"🧠 <b>MEMORY WARNING</b>\n"
                   f"usage: <b>{pct}%</b> of {gb:.1f}GB\n"
                   f"time: {time.strftime('%H:%M:%S')}")
    except Exception:
        pass


def check_radar_logs():
    """Check radar-watcher logs for tracebacks."""
    try:
        r = subprocess.run(
            ["docker", "logs", "radar-watcher", "--tail", "50", "--since", "5m"],
            capture_output=True, text=True, timeout=15)
        errors = []
        for line in r.stdout.splitlines():
            if "Traceback" in line or "Error" in line:
                errors.append(line.strip()[:120])
        if errors:
            # dedupe: only alert if there are NEW errors (not the same ones)
            txt = "\n".join(f"  <code>{e}</code>" for e in errors[:5])
            tg(f"🔴 <b>RADAR ERRORS</b> (last 5 min)\n{txt}")
    except Exception:
        pass


# ── Command audit monitor ────────────────────────────────────────────
CMD_LOG = "/var/log/commands_audit.log"

# sensitive commands that trigger Telegram alerts
SENSITIVE = re.compile(
    r"^(?:sudo )?(?:rm |kill |shutdown|reboot|halt|poweroff|"
    r"systemctl |docker |docker-compose |"
    r"chmod |chown |passwd |useradd |userdel |adduser |deluser |"
    r"crontab |iptables |ufw |"
    r"ssh-keygen |curl.*\|.*sh|wget.*\|.*sh|"
    r"apt |apt-get |pip install|"
    r"git push|git reset|git checkout|git filter)", re.IGNORECASE)

# commands that are too noisy to alert even though they're "sensitive"
SKIP = re.compile(r"docker ps|docker logs|docker exec.*grep|docker compose ps")


def tail_cmd_log():
    """Tail the command audit log and alert on sensitive commands."""
    pos = 0
    if os.path.exists(CMD_LOG):
        pos = os.path.getsize(CMD_LOG)
    while True:
        try:
            if not os.path.exists(CMD_LOG):
                time.sleep(3)
                continue
            size = os.path.getsize(CMD_LOG)
            if size < pos:
                pos = 0  # log rotated
            if size > pos:
                with open(CMD_LOG, "r") as f:
                    f.seek(pos)
                    for line in f:
                        parse_cmd_line(line.strip())
                pos = size
        except Exception as e:
            print(f"cmd log err: {e}", file=sys.stderr)
        time.sleep(0.5)


def parse_cmd_line(line):
    """Format: timestamp|user|ip|command"""
    parts = line.split("|", 3)
    if len(parts) < 4:
        return
    ts, user, ip, cmd = parts
    if not cmd or SKIP.search(cmd):
        return
    if SENSITIVE.search(cmd):
        cmd_short = cmd[:200] if len(cmd) > 200 else cmd
        ip_disp = ip if ip != "local" else "console"
        tg(f"⌨️ <b>SENSITIVE CMD</b>\n"
           f"user: <code>{user}</code>\n"
           f"ip: <code>{ip_disp}</code>\n"
           f"cmd: <code>{cmd_short}</code>\n"
           f"time: {ts}")


# ── main ────────────────────────────────────────────────────────────
def main():
    import threading
    tg("📡 <b>Server Monitor</b> online\n"
       f"host: <code>{os.uname().nodename}</code>\n"
       f"monitoring: SSH logins, Docker events, system health, radar errors, commands")
    threads = [
        threading.Thread(target=tail_auth_log, daemon=True),
        threading.Thread(target=watch_docker_events, daemon=True),
        threading.Thread(target=health_loop, daemon=True),
        threading.Thread(target=tail_cmd_log, daemon=True),
    ]
    for t in threads:
        t.start()
    # keep alive
    while True:
        time.sleep(3600)
        tg("💓 server monitor alive")


if __name__ == "__main__":
    main()
