
const { Connection, PublicKey } = require("@solana/web3.js");
const { DLMM } = require("@meteora-ag/dlmm");
(async () => {
  const connection = new Connection("https://solana-rpc.publicnode.com", "confirmed");
  const PAIR = "ASfqo2u2aSVhgNp8DShvcfvajweJHRSf2mY3D9RMRkNd";
  try {
    const dlmm = await DLMM.create(connection, new PublicKey(PAIR));
    console.log("DLMM created OK");
    const activeBin = dlmm.getActiveBin();
    console.log("activeBin:", JSON.stringify(activeBin).slice(0,200));
  } catch (e) {
    console.error("ERROR:", e.message.slice(0, 300));
    if (e.stack) console.error(e.stack.split("\n").slice(0,4).join("\n"));
  }
})();
