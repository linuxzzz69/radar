/**
 * dbc_state.js - DBC on-chain state microservice
 * Part of Radar: on-chain insider detection for Solana LPs
 *
 * Exposes a tiny HTTP JSON API over the official Meteora DBC SDK:
 *   GET /state?mint=<BASE_MINT>   -> virtual pool + config state for a launch
 *
 * Run:  node dbc_state.js   (listens on :8077)
 * Python consumes http://127.0.0.1:8077/state?mint=...
 */
const express = require("express");
const { Connection, PublicKey } = require("@solana/web3.js");
const {
  DynamicBondingCurveClient,
} = require("@meteora-ag/dynamic-bonding-curve-sdk");

const PORT = process.env.PORT || 8077;
const RPCS = (process.env.RPC_URL || "https://solana-rpc.publicnode.com,https://api.mainnet-beta.solana.com").split(",");
let RPC = RPCS[0];
// note: SDK client binds one connection; multi-RPC fallback handled by restart or env


const connection = new Connection(RPC, "confirmed");
const client = new DynamicBondingCurveClient(connection, "confirmed");
const app = express();

function jsonNumbers(o) {
  // convert BN/bigint to strings for safe JSON transport
  if (typeof o === "bigint") return o.toString();
  if (o && o.toString && o._bn) return o.toString(); // BN / PublicKey
  if (Array.isArray(o)) return o.map(jsonNumbers);
  if (o && typeof o === "object") {
    const out = {};
    for (const [k, v] of Object.entries(o)) out[k] = jsonNumbers(v);
    return out;
  }
  return o;
}

app.get("/health", (_req, res) => res.json({ ok: true, rpc: RPC }));

app.get("/state", async (req, res) => {
  const mint = req.query.mint;
  if (!mint) return res.status(400).json({ error: "missing ?mint=" });
  try {
    const baseMint = new PublicKey(mint);
    const pool = await client.state.getPoolByBaseMint(baseMint);
    if (!pool) return res.status(404).json({ error: "no DBC pool for this mint" });

    const vpa = pool; // ProgramAccount<VirtualPool>
    const vAddr = vpa.publicKey;
    const acc = vpa.account;

    // config details
    let config = null;
    try {
      config = await client.state.getPoolConfig(acc.config);
    } catch (e) {
      config = { error: String(e.message || e) };
    }

    // curve progress (quote side) 0..1
    let curveProgress = null;
    try {
      curveProgress = await client.state.getPoolQuoteTokenCurveProgress(vAddr);
    } catch (e) {
      curveProgress = null;
    }

    // fee metrics (base fee scheduler behavior)
    let feeMetrics = null;
    try {
      feeMetrics = await client.state.getPoolFeeMetrics(vAddr);
    } catch (e) {
      feeMetrics = null;
    }

    res.json({
      mint,
      poolAddress: vAddr.toString(),
      virtualPool: jsonNumbers(acc),
      config: jsonNumbers(config),
      curveProgress,
      feeMetrics: jsonNumbers(feeMetrics),
      fetchedAt: new Date().toISOString(),
    });
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
});

// all DBC pools for a config (useful for scanning whole launchpads)
app.get("/pools-by-config", async (req, res) => {
  const config = req.query.config;
  if (!config) return res.status(400).json({ error: "missing ?config=" });
  try {
    const pools = await client.state.getPoolsByConfig(new PublicKey(config));
    res.json({
      config,
      pools: pools.map((p) => ({
        address: p.publicKey.toString(),
        creator: p.account.creator?.toString?.() ?? null,
        baseMint: p.account.baseMint?.toString?.() ?? null,
        quoteMint: p.account.quoteMint?.toString?.() ?? null,
        poolState: p.account.poolState ?? null,
        activationPoint:
          p.account.activationPoint?.toString?.() ?? null,
      })),
      fetchedAt: new Date().toISOString(),
    });
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
});

app.listen(PORT, () => {
  console.log(`dbc_state.js listening on :${PORT} (rpc: ${RPC})`);
});
