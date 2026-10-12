
const dlmmPkg = require("@meteora-ag/dlmm");
const { Connection, PublicKey } = require("@solana/web3.js");
const conn = new Connection("https://api.mainnet-beta.solana.com", "confirmed");
const pairAddr = "6a8JPVVhLmTLbX9GduJgZi9t5g6TTZFTwUrv2uHrDJxT";
async function main() {
  const client = await dlmmPkg.create(conn, new PublicKey(pairAddr));
  const ab = client.getActiveBin();
  console.log("activeBin:", JSON.stringify(ab, (k,v) => typeof v === "bigint" ? v.toString() : v).slice(0,300));
  console.log("tokenX:", client.lbPair.tokenXMint?.toString?.());
  console.log("tokenY:", client.lbPair.tokenYMint?.toString?.());
  console.log("binStep:", client.lbPair.binStep);
}
main().catch(e => console.error("ERROR:", e.message.slice(0,200)));
