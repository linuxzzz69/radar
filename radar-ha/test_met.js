const dlmmPkg = require("@meteora-ag/dlmm");
const { Connection, PublicKey } = require("@solana/web3.js");
const conn = new Connection("https://api.mainnet-beta.solana.com", "confirmed");
const pairAddr = "AsSyvUnbfaZJPRrNh3kUuvZTeHKoMVWEoHz86f4Q5D9x";
async function main() {
  const d = await dlmmPkg.create(conn, new PublicKey(pairAddr));
  await d.refetchStates();
  const ab = d.getActiveBin();
  console.log("MET/SOL activeBin:", JSON.stringify(ab, (k,v) => typeof v === "bigint" ? v.toString() : v).slice(0,300));
  const bins = await d.getBinsAroundActiveBin(3);
  const withLiq = bins.bins.filter(b => {
    const x = b.amountX ? Number(b.amountX.toString()) : 0;
    const y = b.amountY ? Number(b.amountY.toString()) : 0;
    return x > 0 || y > 0;
  });
  console.log("bins with liquidity:", withLiq.length, "/", bins.bins.length);
  console.log("binStep:", d.lbPair.binStep);
  console.log("activeId:", d.lbPair.activeId ? d.lbPair.activeId.toString() : "?");
  console.log("tokenX:", d.lbPair.tokenXMint ? d.lbPair.tokenXMint.toString().slice(0,16) : "?");
  console.log("tokenY:", d.lbPair.tokenYMint ? d.lbPair.tokenYMint.toString().slice(0,16) : "?");
}
main().catch(e => console.error("ERROR:", e.message.slice(0,200)));
