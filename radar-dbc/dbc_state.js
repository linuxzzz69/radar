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


// simple sequential RPC fallback wrapper
const RPCS = (process.env.RPC_URLS || "https://api.mainnet-beta.solana.com,https://api.mainnet-beta.solana.com,https://solana-rpc.publicnode.com")
  .split(",").map(s => s.trim()).filter(Boolean);
let rpcIdx = 0;
async function withClient(fn) {
  let lastErr;
  for (let i = 0; i < RPCS.length; i++) {
    try {
      const connection = new Connection(RPCS[rpcIdx], "confirmed");
      const client = new DynamicBondingCurveClient(connection, "confirmed");
      return await fn(client, connection);
    } catch (e) {
      lastErr = e;
      const msg = String(e.message || e);
      if (msg.includes("413") || msg.includes("429") || msg.includes("allowance") || msg.includes("Too Many")) {
        rpcIdx = (rpcIdx + 1) % RPCS.length;
        continue;
      }
      throw e;
    }
  }
  throw lastErr;
}

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

app.get("/health", (_req, res) => res.json({ ok: true, rpcs: RPCS }));

app.get("/state", async (req, res) => {
  const mint = req.query.mint;
  if (!mint) return res.status(400).json({ error: "missing ?mint=" });
  try {
    const baseMint = new PublicKey(mint);
    const pool = await withClient((c) => c.state.getPoolByBaseMint(baseMint));
    if (!pool) return res.status(404).json({ error: "no DBC pool for this mint" });

    const vAddr = pool.publicKey;
    const ps = pool.account.poolState;

    // config details
    let config = null;
    try {
      config = await withClient((c) => c.state.getPoolConfig(ps.config));
    } catch (e) {
      config = { error: String(e.message || e) };
    }

    // curve progress (quote side) 0..1
    let curveProgress = null;
    try {
      curveProgress = await withClient((c) => c.state.getPoolQuoteTokenCurveProgress(vAddr));
    } catch (e) {
      curveProgress = null;
    }

    // fee metrics
    let feeMetrics = null;
    try {
      feeMetrics = await withClient((c) => c.state.getPoolFeeMetrics(vAddr));
    } catch (e) {
      feeMetrics = null;
    }

    // activation as unix timestamp (DBC stores it as seconds or slots per activationType)
    const cfg0 = config && !config.error ? config : {};
    const activationType = cfg0.activationType; // 0 = slot, 1 = timestamp
    let activationTs = null;
    const apRaw = ps.activationPoint;
    if (apRaw !== undefined && apRaw !== null) {
      const apNum = Number(apRaw.toString ? apRaw.toString() : apRaw);
      if (activationType === 0) {
        // slot-based: convert with recent slot perf (approx 400ms/slot)
        try {
          const cur = await connection.getSlot();
          activationTs = Math.floor(Date.now() / 1000) + (apNum - cur) * 0.4;
        } catch (_) { activationTs = apNum; }
      } else {
        activationTs = apNum; // already unix seconds
      }
    }
    const activationTypeVal = activationType;

    res.json({
      mint,
      poolAddress: vAddr.toString(),
      configAddress: ps.config?.toString?.() ?? String(ps.config),
      creator: ps.creator?.toString?.() ?? null,
      baseMint: ps.baseMint?.toString?.() ?? null,
      quoteMint: ps.quoteMint?.toString?.() ?? null,
      isMigrated: !!ps.isMigrated,
      migrationProgress: ps.migrationProgress?.toString?.() ?? null,
      poolType: ps.poolType,
      sqrtPrice: ps.sqrtPrice?.toString?.() ?? null,
      activationPoint: activationTs,
      activationType: activationTypeVal,
      curveProgress,
      poolFees: jsonNumbers(cfg0.poolFees ?? null),
      migrationOption: cfg0.migrationOption,
      collectFeeMode: cfg0.collectFeeMode,
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
  console.log(`dbc_state.js listening on :${PORT} (rpcs: ${RPCS.join(", ")})`);
});
