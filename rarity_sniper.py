#!/usr/bin/env python3
"""
rarity_sniper.py - NFT rarity scanner + floor-mispricing detector
Part of Radar: on-chain analysis tools for NFT/EVM markets

Two modes:

MODE 1: On-chain rarity scan (no API key needed)
  Reads an ERC-721 collection directly from the chain (ETH mainnet or any
  EVM including Robinhood Chain), samples token metadata via tokenURI,
  fetches trait JSONs (ipfs/arweave/http/base64), computes rarity scores
  (sum of inverse trait frequency - the community-standard method), and
  ranks every token scanned. Output: console top-list + CSV.

  python3 rarity_sniper.py --contract 0x... --sample 300
  python3 rarity_sniper.py --contract 0x... --rpc https://your-rpc --sample 500

MODE 2: OpenSea floor sniping (needs OPENSEA_API_KEY env var)
  Pulls collection NFTs + live listings from OpenSea v2, ranks traits,
  and flags listings priced BELOW the rarity-implied percentile band.
  Underpriced rare items = snipe targets (alert via Telegram if --tg).

  export OPENSEA_API_KEY=...
  python3 rarity_sniper.py --slug boredapeyachtclub --floor-snipe --tg

Notes:
- Polite polling only: built-in delays, rotate RPCs on 429s.
- Marketplace ToS may restrict bots - keep rates human-ish.
- Rarity score = sum over traits of 1 / (count_of_value / total).
- Nothing here is financial advice. DYOR. The chain keeps the receipts.

Requires: only python3 stdlib (requests-free, urllib only).
"""
import argparse, base64, csv, json, os, re, sys, time, urllib.request, urllib.error
from collections import Counter

# ---------- config ----------
UA = {"User-Agent": "Mozilla/5.0 (radar-rarity-sniper)", "Content-Type": "application/json"}
RPCS_DEFAULT = "https://ethereum-rpc.publicnode.com,https://rpc.ankr.com/eth,https://eth.llamarpc.com"
IPFS_GATEWAYS = ["https://ipfs.io/ipfs/", "https://cloudflare-ipfs.com/ipfs/", "https://gateway.pinata.cloud/ipfs/"]
OS_API = "https://api.opensea.io/api/v2"
TG_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watch_config.json")
POLL_DELAY = 0.35
SAMPLE_DELAY = 0.15

rpc_idx = 0

def get_rpcs(cli_rpc):
    if cli_rpc:
        return [cli_rpc]
    return os.environ.get("RPC_URLS", RPCS_DEFAULT).split(",")

# ---------- http helpers ----------
def http_json(url, headers=None, timeout=25, retries=2):
    h = dict(UA)
    if headers:
        h.update(headers)
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h)
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < retries:
                time.sleep(1.5 * (i + 1)); continue
            raise
        except Exception:
            if i < retries:
                time.sleep(0.8); continue
            raise
    return None

def http_text(url, headers=None, timeout=25):
    h = {"User-Agent": UA["User-Agent"]}
    if headers: h.update(headers)
    req = urllib.request.Request(url, headers=h)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="ignore")

# ---------- EVM raw calls ----------
def eth_call(rpcs, to, data):
    global rpc_idx
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": to, "data": data}, "latest"]}).encode()
    for _ in range(len(rpcs)):
        try:
            req = urllib.request.Request(rpcs[rpc_idx], data=body, headers=UA)
            r = json.load(urllib.request.urlopen(req, timeout=20))
            if "error" in r:
                return None
            return r.get("result")
        except Exception:
            rpc_idx = (rpc_idx + 1) % len(rpcs)
            time.sleep(0.5)
    return None

def decode_string(hexres):
    if not hexres or hexres == "0x":
        return None
    b = bytes.fromhex(hexres[2:])
    if len(b) < 64:
        return None
    try:
        off = int.from_bytes(b[0:32], "big")
        ln = int.from_bytes(b[off:off+32], "big")
        return b[off+32:off+32+ln].decode("utf-8", errors="ignore")
    except Exception:
        return None

def decode_uint(hexres):
    if not hexres or hexres == "0x":
        return None
    return int(hexres, 16)

# ERC-721 selectors
SEL_NAME = "0x06fdde03"
SEL_TOTALSUPPLY = "0x18160ddd"
SEL_TOKENURI = "0xc87b56dd"

def token_uri(rpcs, contract, token_id):
    data = SEL_TOKENURI + hex(token_id)[2:].rjust(64, "0")
    return decode_string(eth_call(rpcs, contract, data))

def fetch_metadata(uri):
    """Fetch JSON metadata from http(s)/ipfs/arweave/base64-data URIs."""
    if not uri:
        return None
    # base64 data URI
    if uri.startswith("data:application/json;base64,"):
        try:
            return json.loads(base64.b64decode(uri.split(",", 1)[1]).decode("utf-8", errors="ignore"))
        except Exception:
            return None
    # ipfs
    if uri.startswith("ipfs://"):
        cid = uri[len("ipfs://"):]
        for gw in IPFS_GATEWAYS:
            try:
                return json.loads(http_text(gw + cid))
            except Exception:
                continue
        return None
    # arweave
    if uri.startswith("ar://"):
        try:
            return json.loads(http_text("https://arweave.net/" + uri[5:]))
        except Exception:
            return None
    # plain http(s)
    try:
        txt = http_text(uri)
        return json.loads(txt)
    except Exception:
        return None

# ---------- rarity math ----------
def trait_pairs(meta):
    """Extract (trait_type, value) pairs from standard OpenSea-style metadata."""
    attrs = meta.get("attributes") or meta.get("traits") or meta.get("attributes")
    if attrs is None:
        return []
    out = []
    if isinstance(attrs, dict):  # some collections use {trait: value}
        for k, v in attrs.items():
            out.append((str(k), str(v)))
    else:
        for a in attrs:
            if isinstance(a, dict):
                t = a.get("trait_type") or a.get("key") or ""
                v = a.get("value")
                if v is not None:
                    out.append((str(t), str(v)))
    return out

def rarity_scores(tokens):
    """tokens: list of {id, traits:[(t,v)]}. Returns {id: score, rank}."""
    total = len(tokens)
    counts = Counter()
    for tok in tokens:
        for pair in tok["traits"]:
            counts[pair] += 1
    scores = {}
    for tok in tokens:
        s = 0.0
        for pair in tok["traits"]:
            c = counts.get(pair, 1)
            s += total / c  # inverse frequency; rarer = higher
        scores[tok["id"]] = s
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    return scores, ranked

# ---------- mode 1: on-chain scan ----------
def scan_onchain(contract, rpcs, sample, start, out_csv):
    name = decode_string(eth_call(rpcs, contract, SEL_NAME)) or contract
    print(f"collection : {name}")
    print(f"contract   : {contract}")
    print(f"scanning   : tokens {start}..{start+sample-1} (traits only)")
    tokens, failed = [], 0
    for i in range(start, start + sample):
        uri = token_uri(rpcs, contract, i)
        meta = fetch_metadata(uri) if uri else None
        if not meta:
            failed += 1
            if failed <= 3:
                print(f"  ! token {i}: no metadata (uri={uri or 'none'})")
        else:
            tokens.append({"id": i, "traits": trait_pairs(meta), "name": meta.get("name", "")})
        if (i - start) % 25 == 0 and i > start:
            print(f"  ... {i-start}/{sample} scanned")
        time.sleep(SAMPLE_DELAY)
    if not tokens:
        sys.exit("no metadata fetched - is this an ERC-721 with tokenURI?")
    scores, ranked = rarity_scores(tokens)
    print(f"\nscanned {len(tokens)} tokens ({failed} failed). rarity ranking (top 15):")
    print(f"{'rank':>4} {'token':>6} {'score':>8}  name")
    for rank, (tid, s) in enumerate(ranked[:15], 1):
        nm = next((t["name"] for t in tokens if t["id"] == tid), "")
        print(f"{rank:>4} {tid:>6} {s:>8.1f}  {nm[:40]}")
    if out_csv:
        with open(out_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rank", "token_id", "rarity_score", "name"])
            for rank, (tid, s) in enumerate(ranked, 1):
                nm = next((t["name"] for t in tokens if t["id"] == tid), "")
                w.writerow([rank, tid, round(s, 2), nm])
        print(f"\nCSV saved: {out_csv}")
    return ranked

# ---------- mode 2: OpenSea snipe ----------
def os_get(path, key):
    return http_json(OS_API + path, headers={"x-api-key": key})

def snipe_opensea(slug, key, ratio_threshold, tg):
    print(f"OpenSea mode: collection '{slug}' (key detected)")
    # 1) pull NFTs w/ traits (paginate a few pages)
    nfts, next_ptr, pages = [], None, 0
    while pages < 6:
        q = f"/collection/{slug}/nfts?limit=50" + (f"&next={next_ptr}" if next_ptr else "")
        r = os_get(q, key) or {}
        batch = r.get("nfts") or []
        nfts.extend(batch)
        next_ptr = r.get("next")
        pages += 1
        if not next_ptr or not batch:
            break
        time.sleep(0.5)
    if not nfts:
        sys.exit("no NFTs returned - bad slug or key limits")
    tokens = []
    for n in nfts:
        traits = [(str(a.get("trait_type", "")), str(a.get("value", "")))
                  for a in (n.get("traits") or [])]
        tokens.append({"id": n.get("identifier"), "traits": traits,
                       "name": n.get("name", ""), "meta": n})
    scores, ranked = rarity_scores(tokens)
    print(f"ranked {len(tokens)} NFTs by rarity")
    # 2) pull live listings
    listings, lnext, lpages = [], None, 0
    while lpages < 6:
        q = f"/listings/collection/{slug}/all?limit=50" + (f"&next={lnext}" if lnext else "")
        r = os_get(q, key) or {}
        listings.extend(r.get("listings") or [])
        lnext = r.get("next"); lpages += 1
        if not lnext: break
        time.sleep(0.5)
    if not listings:
        print("no live listings returned (endpoint/key limits) - rarity ranking printed above")
        return ranked
    priced = []
    for l in listings:
        cur = ((l.get("price") or {}).get("current") or {})
        try:
            price = float(cur.get("value", 0) or 0) / (10 ** int(cur.get("decimals", 18) or 18))
        except Exception:
            continue
        ident = None
        for offer in (((l.get("protocol_data") or {}).get("parameters") or {}).get("offer") or []):
            if offer.get("itemType") in (2, 3) and offer.get("identifierOrCriteria") is not None:
                ident = str(int(offer.get("identifierOrCriteria")))
                break
        if price > 0 and ident is not None:
            priced.append((ident, price))
    if not priced:
        print("listings returned but none parseable to token ids - rarity ranking printed above")
        return ranked
    floor = min(p for _, p in priced)
    print(f"live listings: {len(listings)} | parsed: {len(priced)} | floor: {floor:.4f} ETH")
    median_score = sorted(scores.values())[len(scores)//2] if scores else 1
    print(f"\nSNIPE TARGETS (rare + priced near floor):")
    hits = []
    for ident, price in priced:
        s = scores.get(ident)
        if s is None:
            continue
        if s > median_score * 1.8 and price < floor * max(1.25, ratio_threshold):
            nm = next((t["name"] for t in tokens if t["id"] == ident), "")
            print(f"  #{ident} '{nm[:30]}' score={s:.1f} price={price:.4f} ETH (floor {floor:.3f})")
            hits.append((ident, s, price, nm))
    if not hits:
        print("  none found this sweep - rerun or widen threshold")
    if tg and hits:
        tg_send(tg, f"🕸 rarity_sniper: {len(hits)} snipe targets in '{slug}' (floor {floor:.3f} ETH):\n" +
                "\n".join(f"#{h[0]} score {h[1]:.0f} @ {h[2]:.3f} ETH" for h in hits[:5]))
    return hits

# ---------- telegram ----------
def tg_send(cfg, text):
    tok = cfg.get("telegram", {}).get("token")
    chat = cfg.get("telegram", {}).get("chat_id")
    if not tok or not chat:
        return
    try:
        data = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{tok}/sendMessage", data=data, headers=UA), timeout=15)
    except Exception:
        pass

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", help="ERC-721 contract address (on-chain mode)")
    ap.add_argument("--slug", help="OpenSea collection slug (OS mode)")
    ap.add_argument("--rpc", help="single RPC URL (default: ETH public set; pass a Robinhood Chain RPC for EVMs there)")
    ap.add_argument("--sample", type=int, default=200, help="how many tokens to scan (on-chain mode)")
    ap.add_argument("--start", type=int, default=0, help="first token id to scan")
    ap.add_argument("--csv", help="output CSV path for ranked results")
    ap.add_argument("--floor-snipe", action="store_true", help="OS mode: flag rare items near floor")
    ap.add_argument("--threshold", type=float, default=1.25, help="price < floor*threshold AND score > median*1.8")
    ap.add_argument("--tg", action="store_true", help="send hits to Telegram (uses watch_config.json creds)")
    a = ap.parse_args()

    tg = json.load(open(TG_CFG)) if (a.tg and os.path.exists(TG_CFG)) else None

    if a.slug:
        key = os.environ.get("OPENSEA_API_KEY")
        if not key:
            sys.exit("OS mode needs OPENSEA_API_KEY env var (free at docs.opensea.io)")
        snipe_opensea(a.slug, key, a.threshold, tg)
    elif a.contract:
        rpcs = get_rpcs(a.rpc)
        scan_onchain(a.contract, rpcs, a.sample, a.start, a.csv or "rarity_ranked.csv")
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
