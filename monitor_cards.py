#!/usr/bin/env python3
"""CARDS/USDC bid-only position monitor - run: python3 monitor_cards.py"""
import json, urllib.request, time

PAIR = "2N1KNuLSt167P6p9P8HYcisTvTTv4vYTM8QJBbtv1xYU"
MIN_PRICE = 0.23491
MAX_PRICE = 0.28175
VOL_FLOOR = 500_000  # below this, fees are dead -> reassess

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=15))

d = get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{PAIR}")["pair"]
price = float(d["priceUsd"])
vol24 = (d.get("volume") or {}).get("h24") or 0
chg24 = (d.get("priceChange") or {}).get("h24") or 0
liq = (d.get("liquidity") or {}).get("usd") or 0

if price > MAX_PRICE:
    state = "WAITING (out of range, USDC idle) - earn $0, this is normal"
elif price >= MIN_PRICE:
    state = "IN RANGE - USDC converting to CARDS bin by bin"
else:
    state = "BELOW RANGE - fully converted, you are now a CARDS holder"

flags = []
if vol24 < VOL_FLOOR:
    flags.append(f"VOLUME DEAD (${vol24:,.0f} < ${VOL_FLOOR:,}) - reassess position")
if chg24 < -20:
    flags.append(f"CRYPTO DUMP ({chg24}%) - check if this is a flush or a death")
if price > MAX_PRICE * 1.10:
    flags.append("PRICE >10% ABOVE RANGE - consider recenting up (after days, not hours)")

ts = time.strftime("%Y-%m-%d %H:%M:%S")
print(f"[{ts}] CARDS = ${price:.4f} (24h {chg24:+.1f}%) | pool liq ${liq:,.0f} | vol24h ${vol24:,.0f}")
print(f"Range: {MIN_PRICE:.4f} - {MAX_PRICE:.4f}")
print(f"State: {state}")
for f in flags:
    print(f"!! {f}")
