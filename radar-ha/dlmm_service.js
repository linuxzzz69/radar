/**
 * dlmm_service.js — Heart Attack module
 * Opens/closes/claims Meteora DLMM positions programmatically.
 * HTTP API on :8078 consumed by watcher.py.
 *
 * Endpoints:
 *   GET  /health
 *   GET  /pool-info?pair=<DLMM_PAIR>          -> price, binStep, activeBin
 *   POST /open                                 -> open Curve position
 *        {pair, solAmount, bins(3-5)}
 *   POST /close                                -> withdraw all + claim fees
 *        {pair, positionMint}
 *   GET  /position?pair=&position=             -> live PnL data
 */
const express = require("express");
const { Connection, PublicKey, Keypair } = require("@solana/web3.js");
const { DLMM } = require("@meteora-ag/dlmm");
const bs58 = require("bs58");

const PORT = process.env.PORT || 8078;
const RPC = process.env.RPC_URL || "https://api.mainnet-beta.solana.com";
const connection = new Connection(RPC, "confirmed");
const app = express();
app.use(express.json());

let BOT_KEYPAIR = null;
try {
  const w = JSON.parse(require("fs").readFileSync("/app/.bot_wallet.json", "utf8"));
  BOT_KEYPAIR = Keypair.fromSecretKey(require("bs58").default.decode(w.secret_b58));
} catch (e) { /* wallet not loaded yet */ }

function getDlmm(pairAddress) {
  return DLMM.create(connection, new PublicKey(pairAddress));
}

app.get("/health", (_req, res) => res.json({
  ok: true, wallet: BOT_KEYPAIR ? BOT_KEYPAIR.publicKey.toString() : null
}));

app.get("/pool-info", async (req, res) => {
  try {
    const dlmm = await getDlmm(req.query.pair);
    await dlmm.refetchStates();  // populate internal state (WITHOUT this, getActiveBin returns {})
    const activeBin = dlmm.getActiveBin();
    if (!activeBin || !activeBin.price) {
      return res.status(500).json({
        error: "pool has no liquidity at the active bin. The pool may be dead, drained, or a different token than expected. Verify the pair on meteora.ag."
      });
    }
    res.json({
      activeBinPrice: activeBin.price,
      binStep: dlmm.lbPair.binStep,
      activeBinId: activeBin.binId,
      price: activeBin.price.toString(),
    });
  } catch (e) { res.status(500).json({ error: e.message.slice(0, 150) }); }
});

app.post("/open", async (req, res) => {
  if (!BOT_KEYPAIR) return res.status(400).json({ error: "bot wallet not loaded" });
  const { pair, solAmount, bins } = req.body;
  try {
    const dlmm = await getDlmm(pair);
    await dlmm.refetchStates();
    const binStep = dlmm.lbPair.binStep;
    // curve: 3-5 bins centered on active bin (spread both sides)
    const total = bins || 5;
    const half = Math.floor(total / 2);
    const minBin = activeBin.binId - half;
    const maxBin = activeBin.binId + (total - half);
    // Curve strategy: balanced 50/50 both-sided (molu's heart attack uses curve tight)
    const totalSol = solAmount * 1e9;
    const slippage = 10; // bps equivalent for positioning
    const tx = await dlmm.addLiquidityByStrategy({
      position: null, // auto-create new position
      user: BOT_KEYPAIR.publicKey,
      totalXAmount: "0", // computed by strategy
      totalYAmount: totalSol.toString(),
      distribution: "CURVE", // curve strategy
      activeBinId: activeBin.binId,
      minBinId: minBin,
      maxBinId: maxBin,
      slippageBps: slippage,
    });
    // sign + send
    const sig = await connection.sendTransaction(tx, [BOT_KEYPAIR]);
    res.json({ ok: true, signature: sig, minBin, maxBin, bins: total });
  } catch (e) {
    res.status(500).json({ error: e.message.slice(0, 200) });
  }
});

app.post("/close", async (req, res) => {
  if (!BOT_KEYPAIR) return res.status(400).json({ error: "bot wallet not loaded" });
  const { pair, positionMint } = req.body;
  try {
    const dlmm = await getDlmm(pair);
    await dlmm.refetchStates();
    const position = new PublicKey(positionMint);
    const positionData = await dlmm.getUserPositions(BOT_KEYPAIR.publicKey);
    const pos = positionData.find(p =>
      p.publicKey.toString() === positionMint
    );
    if (!pos) return res.status(404).json({ error: "position not found" });
    // remove ALL liquidity from all bins + claim fees
    const removeTx = await dlmm.removeAllLiquidityAndClaim(position);
    const sig = await connection.sendTransaction(removeTx, [BOT_KEYPAIR]);
    res.json({ ok: true, signature: sig });
  } catch (e) {
    res.status(500).json({ error: e.message.slice(0, 200) });
  }
});

app.get("/position", async (req, res) => {
  const { pair, positionMint } = req.query;
  try {
    const dlmm = await getDlmm(pair);
    await dlmm.refetchStates();
    const positions = await dlmm.getUserPositions(BOT_KEYPAIR.publicKey);
    const pos = positions.find(p => p.publicKey.toString() === positionMint);
    if (!pos) return res.json({ found: false });
    const activeBin = dlmm.getActiveBin();
    // compute position value + fees from bins data
    res.json({
      found: true,
      inRange: pos.positionData.positionBinData.some(b =>
        b.binId >= activeBin.binId - 2 && b.binId <= activeBin.binId + 2
      ),
      fees: pos.positionData.claimableRewards || [],
      bins: pos.positionData.positionBinData.length,
    });
  } catch (e) {
    res.status(500).json({ error: e.message.slice(0, 200) });
  }
});

app.listen(PORT, () => console.log(`dlmm_service on :${PORT}`));
