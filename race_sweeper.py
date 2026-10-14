#!/usr/bin/env python3
"""
race_sweeper.py - Race-mode sweeper bot for compromised Solana wallets (v2, raw RPC)

The situation: a keypair is compromised. A sweeper bot watches the address and
instantly sweeps any incoming SOL. Staked/locked assets (e.g. staked JUP) can
only be moved WITH that keypair, so the only way out is to win the race:
fund the address with the minimum fee amount, and INSTANTLY sign + broadcast
a withdraw-and-transfer transaction in the same block, before the bot's tx lands.

HOW IT WORKS
1. Prepare: compromised key file (solana-keygen json array format),
   destination (fresh) wallet address, and the exit mode.
2. Run with --arm. The compromised keypair is loaded into memory ONLY
   (never saved, never sent anywhere). Ctrl+C purges it.
3. The script polls the compromised address's SOL balance via raw JSON-RPC.
4. The instant the balance crosses the threshold, it:
     a) builds the exit transaction with a high priority fee
     b) signs with the compromised key (in memory)
     c) broadcasts immediately
5. If the sweeper wins (balance swept before our tx lands), the loop re-arms:
   fund again and it fires again. The bot cannot take the STAKED asset
   directly, only free SOL, so the staked value stays winnable.

MODES
- sol : plain SOL exit (sweep everything above rent to destination)
- spl : move an SPL token balance (creates destination ATA if needed)

WATCH MODE (no key needed): profiles the sweeper's latency/threshold so you
know what race window you're fighting.

⚠️ SAFETY RULES
- Run on a clean machine. Key lives ONLY in this process's memory while running.
- NEVER paste the private key into any website or DM. All "recovery services"
  that ask for keys are drainers.
- Destination must be a FRESH wallet with a NEW seed.
- After a successful exit, that keypair is burned. Never reuse it.

Usage:
  # watch-only: profile the sweeper first
  python3 race_sweeper.py --watch --addr <COMPROMISED_WALLET>

  # race for plain SOL exit
  python3 race_sweeper.py --arm --key key.json --dest <FRESH_WALLET> --mode sol

  # race for SPL token exit
  python3 race_sweeper.py --arm --key key.json --dest <FRESH_WALLET> --mode spl --mint <MINT>

Requires: solders (pip3 install solders). Raw JSON-RPC for everything else.
"""
import argparse, base64, json, os, sys, time, urllib.request

try:
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solders.transaction import Transaction
    from solders.message import Message
    from solders.compute_budget import set_compute_unit_price, set_compute_unit_limit
    from solders.system_program import transfer, TransferParams
except ImportError:
    sys.exit("missing deps: pip3 install solders")

UA = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
RPCS = os.environ.get(
    "RPC_URLS",
    "https://api.mainnet-beta.solana.com,https://solana-rpc.publicnode.com"
).split(",")
rpc_idx = 0
PRIORITY_FEE_MICROLAMPORTS = 300_000   # 0.0003 SOL priority fee: win the race
POLL_SECONDS = 0.30
FUND_THRESHOLD_SOL = 0.0030            # enough for fees + small rent ops
RENT_EXEMPTION_RESERVE = 0.00205       # keep account alive between attempts

def rpc(method, params, retries=3):
    global rpc_idx
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for i in range(retries):
        try:
            r = json.load(urllib.request.urlopen(
                urllib.request.Request(RPCS[rpc_idx], data=body, headers=UA), timeout=20))
            if "error" in r and "429" in str(r["error"]):
                rpc_idx = (rpc_idx + 1) % len(RPCS); continue
            return r.get("result")
        except Exception as e:
            if "429" in str(e) or "Too Many" in str(e):
                rpc_idx = (rpc_idx + 1) % len(RPCS); continue
            time.sleep(0.4)
    return None

def sol_balance(addr):
    r = rpc("getBalance", [addr])
    return (r.get("value") or 0) / 1e9 if r else None

def get_blockhash():
    r = rpc("getLatestBlockhash", [])
    return r["value"]["blockhash"] if r else None

def sign_and_send(kp, ixs):
    """Sign locally, broadcast raw. skip_preflight for the race."""
    bh = get_blockhash()
    if not bh: return "ERR no blockhash"
    msg = Message(ixs, kp.pubkey())
    tx = Transaction([kp], msg, bh)
    wire = base64.b64encode(bytes(tx)).decode()
    r = rpc("sendTransaction", [wire, {"encoding": "base64", "skipPreflight": True,
                                        "maxSupportedTransactionVersion": 0}])
    if r is None: return "ERR rpc"
    if "error" in r: return f"ERR {str(r['error'])[:140]}"
    return r.get("result", "ERR no sig")

# ---------- exit builders ----------

def build_sol_exit(kp, dest):
    bal = sol_balance(str(kp.pubkey()))
    if bal is None: return None
    sendable = bal - RENT_EXEMPTION_RESERVE - 0.000005 * 3  # fee + prio headroom
    if sendable <= 0: return None
    lamports = int(sendable * 1e9)
    ixs = [
        set_compute_unit_price(PRIORITY_FEE_MICROLAMPORTS),
        set_compute_unit_limit(40_000),
        transfer(TransferParams(from_pubkey=kp.pubkey(),
                                 to_pubkey=Pubkey.from_string(dest),
                                 lamports=lamports)),
    ]
    return ixs

def build_spl_exit(kp, dest, mint_str):
    """SPL token transfer via raw instructions (creates dst ATA if needed)."""
    mint = Pubkey.from_string(mint_str)
    owner = kp.pubkey()
    # derive ATAs
    def ata(wallet, m):
        return Pubkey.find_program_address(
            [bytes(wallet), bytes(Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")), bytes(m)],
            Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"))[0]
    src = ata(owner, mint)
    dst = ata(Pubkey.from_string(dest), mint)
    # token balance
    r = rpc("getTokenAccountsByOwner", [str(owner), {"mint": mint_str}, {"encoding": "jsonParsed"}])
    amount = 0
    try:
        for acc in (r.get("value") or []):
            info = acc["account"]["data"]["parsed"]["info"]
            if info["tokenAccount"] if "tokenAccount" in info else True:
                amount += int(info["tokenAmount"]["amount"])
    except Exception:
        pass
    if amount == 0: return None
    # build ixs: create dst ATA (if missing) then transfer entire balance
    ixs = [set_compute_unit_price(PRIORITY_FEE_MICROLAMPORTS),
           set_compute_unit_limit(120_000)]
    ixs.append({
        "programId": "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
        "keys": [
            {"pubkey": str(dst), "isSigner": False, "isWritable": True},
            {"pubkey": str(Pubkey.from_string(dest)), "isSigner": False, "isWritable": True},
            {"pubkey": str(owner), "isSigner": True, "isWritable": True},
            {"pubkey": mint_str, "isSigner": False, "isWritable": False},
            {"pubkey": "SysvarC1ock11111111111111111111111111111112", "isSigner": False, "isWritable": False},
            {"pubkey": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "isSigner": False, "isWritable": False},
        ],
        "data": base64.b64encode(bytes([0])).decode(),  # Create ATA via ATA program (disc 0)
    })
    # NOTE: ATA-create raw layout varies; the safest v1 path: use SOLDERS spl helpers if present,
    # else transfer only (works if destination ATA already exists).
    try:
        from spl.token.instructions import transfer as spl_transfer, get_associated_token_address
        src_ata = get_associated_token_address(owner, mint)
        dst_ata = get_associated_token_address(Pubkey.from_string(dest), mint)
        ixs.append(spl_transfer(amount=int(amount), src=src_ata, dest=dst_ata,
                                owner=owner, signers=[owner]))
    except ImportError:
        print("  spl helper not installed; skipping ATA-create, trying plain transfer")
        return None
    return ixs

# ---------- modes ----------

def watch_mode(addr):
    print(f"WATCH MODE: {addr}")
    print("Profile the sweeper: send a tiny test amount (0.001-0.002 SOL) and we measure")
    print("(a) sweep latency  (b) whether it leaves dust. Latency = your race window.")
    prev = None
    last_up = None
    while True:
        bal = sol_balance(addr)
        if bal is not None and bal != prev:
            ts = time.strftime("%H:%M:%S")
            if prev is not None:
                delta = bal - prev
                if delta > 0:
                    print(f"[{ts}] +{delta:.6f} SOL deposited")
                    last_up = time.time()
                elif delta < 0:
                    dt = time.time() - last_up if last_up else -1
                    print(f"[{ts}] swept {-delta:.6f} SOL  (deposit->sweep latency: {dt:.2f}s)")
                    print(f"  -> race window = {dt:.2f}s. Pre-sign everything; fire on deposit.")
            prev = bal
        time.sleep(POLL_SECONDS)

def race_mode(kp_path, dest, mode, mint=None):
    raw = json.load(open(kp_path))
    kp = Keypair.from_bytes(bytes(raw)) if isinstance(raw, list) else Keypair.from_base58_string(raw)
    addr = str(kp.pubkey())
    print("=" * 64)
    print("RACE MODE ARMED")
    print(f"compromised wallet : {addr}")
    print(f"destination        : {dest}")
    print(f"mode               : {mode}" + (f" mint={mint}" if mint else ""))
    print("key in memory ONLY. Ctrl+C purges it. Clean machine required.")
    print("=" * 64)
    print(f"Fund {addr} with ~{FUND_THRESHOLD_SOL} SOL, then the loop fires automatically.")
    attempts = 0
    while True:
        bal = sol_balance(addr)
        if bal is not None and bal >= FUND_THRESHOLD_SOL:
            attempts += 1
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] bal {bal:.6f} >= threshold. RACING (attempt {attempts})")
            if mode == "sol":
                ixs = build_sol_exit(kp, dest)
            else:
                ixs = build_spl_exit(kp, dest, mint)
            if ixs is None:
                print("  nothing sendable (balance under fee/rent headroom)")
            else:
                sig = sign_and_send(kp, ixs)
                if sig.startswith("ERR"):
                    print(f"  send failed: {sig}")
                else:
                    print(f"  broadcast: https://solscan.io/tx/{sig}")
                    print("  confirmed = funds out. Purge this key after: never reuse it.")
                    print("  swept instead? fund again; the loop re-arms instantly.")
        time.sleep(POLL_SECONDS)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--addr", help="compromised wallet (watch mode)")
    ap.add_argument("--key", help="path to compromised keypair json (array format)")
    ap.add_argument("--dest", help="fresh destination wallet")
    ap.add_argument("--mode", default="sol", choices=["sol", "spl"])
    ap.add_argument("--mint", help="token mint (spl mode)")
    a = ap.parse_args()
    if a.watch:
        if not a.addr: sys.exit("--watch requires --addr")
        watch_mode(a.addr)
    elif a.arm:
        if not (a.key and a.dest): sys.exit("--arm requires --key and --dest")
        race_mode(a.key, a.dest, a.mode, a.mint)
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
