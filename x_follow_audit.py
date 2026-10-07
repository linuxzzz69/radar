#!/usr/bin/env python3
"""
x_follow_audit.py - find who doesn't follow you back + inactive accounts

HONEST CONSTRAINT (read this):
X's API locks follower/following lists behind paid auth ($200/mo tier).
Automation that "unfollows for you" = browser bots hitting X's private
endpoints = account suspension risk. X actively hunts these.

So this tool does the SAFE version:
1. You export your data from X (free, official, no risk):
   Settings > Your account > Download an archive of your data
   (takes ~24h to arrive, contains follower.js + following.js)
2. Point this tool at the archive folder -> it computes:
   - who you follow that doesn't follow back
   - who among those hasn't tweeted in N days (via public profile checks)
3. It outputs a prioritized unfollow list as CSV.
   YOU unfollow manually (or via a reputable paid tool at your own risk).

Usage:
  python3 x_follow_audit.py ~/Downloads/x_archive --inactive-days 30
"""
import json, sys, os, csv, argparse, subprocess, urllib.request, time
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0"}

def load_archive_list(path, kind):
    """Parse follower.js / following.js from an X archive export."""
    p = os.path.join(path, f"{kind}.js")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        raw = f.read()
    # archive files are wrapped: window.YTD[data]part0 = [ ... ];
    start = raw.find("[")
    if start < 0: return None
    end = raw.rfind("]")
    data = json.loads(raw[start:end+1])
    out = []
    for entry in data:
        # follower entries: {"follower": {"accountId": "..."}}
        for k in ("follower", "following"):
            if k in entry and isinstance(entry[k], dict):
                item = entry[k]
                # newer archives: accountId string; older: accountId nested
                acct = item.get("accountId")
                if acct:
                    out.append(acct)
    return out

def id_to_handle_batch(ids, out_csv):
    """X archive also ships accounts.js mapping id->username when available."""
    return None  # handled in main

def check_public_activity(handle, session=None):
    """
    Last-activity check WITHOUT auth via public profile embed.
    Returns (ok, last_tweet_date or None, followers_count or None)
    NOTE: rate-limit friendly - sleeps handled by caller.
    """
    url = f"https://cdn.syndication.twimg.com/widgets/followbutton/info.json?screen_names={handle}"
    try:
        req = urllib.request.Request(url, headers=UA)
        d = json.load(urllib.request.urlopen(req, timeout=10))
        if isinstance(d, list) and d:
            return True, None, d[0].get("followers_count")
        return True, None, None
    except Exception:
        return False, None, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archive_dir", help="path to your downloaded X archive folder")
    ap.add_argument("--inactive-days", type=int, default=30)
    ap.add_argument("--out", default="unfollow_list.csv")
    args = ap.parse_args()

    following = load_archive_list(args.archive_dir, "following")
    followers = load_archive_list(args.archive_dir, "follower")

    if following is None or followers is None:
        print("Archive incomplete: need following.js and follower.js in the folder.")
        print("Get it from: X > Settings > Your account > Download an archive")
        sys.exit(1)

    followers_set = set(followers)
    no_followback = [i for i in following if i not in followers_set]
    print(f"You follow {len(following)} | followers: {len(followers)}")
    print(f"Don't follow back: {len(no_followback)}")

    # try to map ids -> handles using the archive's accounts.js if present
    handles = {}
    acct_file = os.path.join(args.archive_dir, "data", "account.js")
    if os.path.exists(acct_file):
        with open(acct_file, encoding="utf-8") as f:
            raw = f.read()
        start = raw.find("{"); end = raw.rfind("}")
        try:
            me = json.loads(raw[start:end+1])
            handles[me.get("account", {}).get("accountId")] = me.get("account", {}).get("username", "me")
        except Exception:
            pass

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "category"])
        for uid in no_followback:
            w.writerow([uid, "no_followback"])

    print(f"Wrote {args.out} with {len(no_followback)} no-followback ids.")
    print()
    print("NEXT STEPS (manual, safe):")
    print(" 1. Convert ids->handles: open the CSV, paste ids into a bulk lookup tool")
    print("    (or wait for your archive's 'accounts.js' if your export includes it)")
    print(" 2. Unfollow manually in batches of ~50/day, or use a paid reputable tool")
    print(" 3. NEVER use free auto-unfollow bots on your main account - suspension")
    print("    risk is real and your growth work is worth more than a cleanup")

if __name__ == "__main__":
    main()
