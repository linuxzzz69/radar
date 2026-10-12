const dlmmPkg = require("@meteora-ag/dlmm");
const { Connection, PublicKey } = require("@solana/web3.js");
const conn = new Connection("https://api.mainnet-beta.solana.com", "confirmed");
const pools = [
  { name: "HeeHaw", addr: "6a8JPVVhLmTLbX9GduJgZi9t5g6TTZFTwUrv2uHrDJxT" },
  { name: "MET/SOL", addr: "AsSyvUnbfaZJPRrNh3kUuvZTeHKoMVWEoHz86f4Q5D9x" },
  { name: "CARDS/SOL", addr: "2N1KNuLSt167P6p9P8HYcisTvTTv4vYTM8QJBbtv1xYU" },
  { name: "EMBER/SOL", addr: "5tb9fNLKr2wdJRSTNYRu39kGTjnYVseWo2bGyNgxnLHS" },
];
async function main() {
  for (const p of pools) {
    try {
      const d = await dlmmPkg.create(conn, new PublicKey(p.addr));
      await d.refetchStates();
      const ab = d.getActiveBin();
      const hasLiq = ab && ab.price && Object.keys(ab).length > 0;
      const bins = await d.getBinsAroundActiveBin(2);
      const withLiq = (bins.bins || []).filter(b => {
        const x = b.amountX ? Number(b.amountX.toString()) : 0;
        const y = b.amountY ? Number(b.amountY.toString()) : 0;
        return x > 0 || y > 0;
      });
      const status = hasLiq ? "\u2705 HAS LIQUIDITY" : "\u274c EMPTY";
      console.log(p.name + " | " + status + " | bins with liq: " + withLiq.length + "/" + (bins.bins||[]).length + " | activeBin: " + (ab?.price || "empty"));
    } catch (e) {
      console.log(p.name + " | ERROR: " + e.message.slice(0,80));
    }
  }
}
main();
