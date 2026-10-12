const dlmmPkg = require("@meteora-ag/dlmm");
const { Connection, PublicKey } = require("@solana/web3.js");
const conn = new Connection("https://api.mainnet-beta.solana.com", "confirmed");
const pairAddr = "6a8JPVVhLmTLbX9GduJgZi9t5g6TTZFTwUrv2uHrDJxT";
async function main() {
  const d = await dlmmPkg.create(conn, new PublicKey(pairAddr));
  await d.refetchStates();
  const ab = d.getActiveBin();
  console.log("refetched activeBin:", JSON.stringify(ab, (k,v) => typeof v === "bigint" ? v.toString() : v));
  const activeId = d.lbPair.activeId;
  console.log("activeId:", activeId ? activeId.toString() : "?");
  const binStep = d.lbPair.binStep;
  // calculate price manually
  const price = Math.pow(1 + binStep/10000, activeId - 2147483648);
  console.log("calculated price:", price);
  const bins = await d.getBinsAroundActiveBin(1);
  console.log("binsAround:", JSON.stringify(bins, (k,v) => typeof v === "bigint" ? v.toString() : v).slice(0,300));
}
main().catch(e => console.error("MAIN ERROR:", e.message.slice(0,200)));
