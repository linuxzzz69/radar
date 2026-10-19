/**
 * dlmm_fee.js - Public DLMM pool params for farm_pl.py
 * Usage: node dlmm_fee.js <PAIR1> [PAIR2 ...]
 * Prints: [{"pair": "...", "ok": true, "binStep": 20, "baseFeeBps": 100,
 *           "protocolShare": 1000, "activeId": 583}]
 * Source: Meteora DLMM LbPair account via @meteora-ag/dlmm (radar-ha/node_modules)
 */
const path = require("path");
let create, Connection, PublicKey;
try {
  ({ create } = require(path.join(__dirname, "radar-ha", "node_modules", "@meteora-ag", "dlmm")));
  ({ Connection, PublicKey } = require(path.join(__dirname, "radar-ha", "node_modules", "@solana", "web3.js")));
} catch (e) {
  ({ create } = require("@meteora-ag/dlmm"));
  ({ Connection, PublicKey } = require("@solana/web3.js"));
}
const RPC = process.env.RPC_URL || "https://api.mainnet-beta.solana.com";
const conn = new Connection(RPC, "confirmed");

async function one(pair) {
  try {
    const d = await create(conn, new PublicKey(pair));
    await d.refetchStates();
    const lp = d.lbPair;
    const st = lp.parameters || lp.staticParameters || {};
    const num = (v) => v == null ? null : (v._isBN || typeof v === "object" ? Number(v.toString()) : Number(v));
    return {
      pair, ok: true,
      binStep: lp.binStep,
      baseFeeBps: num(st.baseFactor) != null && st.baseFactor !== undefined ? num(st.baseFactor) / 100 : null,
      protocolShare: st.protocolShare !== undefined ? num(st.protocolShare) : null,
      activeId: lp.activeId ? lp.activeId.toString() : null,
    };
  } catch (e) {
    return { pair, ok: false, error: String(e.message).slice(0, 120) };
  }
}

async function main() {
  const pairs = process.argv.slice(2);
  if (!pairs.length) { console.error("usage: node dlmm_fee.js <PAIR...>"); process.exit(1); }
  const out = [];
  for (const p of pairs) {
    out.push(await one(p));
    process.stderr.write("."); 
  }
  process.stderr.write("\n");
  console.log(JSON.stringify(out));
}
main().catch(e => { console.error("FATAL:", e.message.slice(0, 200)); process.exit(1); });
