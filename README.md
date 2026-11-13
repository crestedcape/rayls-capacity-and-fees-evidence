# Rayls evidence: finality and capacity

Read-only measurements of Rayls mainnet taken on 4, 5, 9, 11 and 12 November 2026, with the scripts that produced them.

Articles: (add the links here after you publish them)

## What is here

**Finality probe (4 and 5 November)**

- `rayls_finality_probe.py`, `rayls_finality_probe_v2.py`, `rayls_finality_probe_v3.py`: three versions of the same script. Each run is read-only and sends no transactions unless you pass `--send`.
- One folder (or a zip of it) per run, named `rayls_probe_<UTC timestamp>`:
  - Run 1, 4 November, about 05:17 UTC (v1): 30 seconds of block pace and committees for epochs 1, 50, 100 and 150.
  - Run 2, 4 November, about 14:56 UTC (v2): 60 seconds of block pace and a scan of 21 epochs.
  - Run 3, 5 November, about 00:35 UTC (v3): adds block timestamps at epoch boundaries and samples the newest 16 epochs.

**Capacity and fee probe (9, 11 and 12 November)**

- `rayls_fee_probe.py`: read-only. Reads the fee history of the newest 1,024 blocks, the newest 300 blocks one by one, and the blocks at 12 epoch boundaries.
- One folder (or a zip of it) per run, named `rayls_fee_probe_<UTC timestamp>`: 9 November about 14:38 UTC, 11 November about 11:13 UTC, 12 November about 03:08 UTC.

Each run folder holds `RESULTS.md` (summary), `raw_rpc_log.jsonl` (every request and response with timings), CSV files, and `SHA256SUMS.txt`. The finality runs also hold the epoch records as JSON.

## Headline results: finality

| Measurement | Result |
| --- | --- |
| Block pace in three live windows | One block every 1.36 s, 1.27 s and 1.37 s |
| Epoch length (block timestamps at 35 epoch boundaries) | 86,400 or 86,401 seconds in all 16 consecutive pairs |
| Block pace over time | 1.31 s per block (epochs 0 to 130), 0.75 s (130 to 160), 1.34 s (160 to 188) |
| Committee | The same 7 keys from epoch 0 to 170, then 8 members from epoch 172 or 173 |
| Signers per epoch record | 5 to 8, and all 35 records meet the quorum for their committee size |

## Headline results: capacity and fees

| Measurement | Result |
| --- | --- |
| Gas limit | 500,000,000 in all 900 blocks read and at all 36 epoch-boundary reads |
| Block pace | 0.742, 0.746 and 0.749 blocks per second |
| Base fee | 48 gwei in all 3,072 blocks of fee history and at all boundary reads (epochs 0 to 195) |
| Usage | 20 transactions in 1,203 seconds; 887 of 900 blocks held no transaction |
| Gas per transaction | 17 of 20 between 37,965 and 40,552; 3 at about 255,000 |
| Throughput ceiling (gas limit x blocks per second / gas per transaction) | About 17,800 per second at 21,000 gas, 9,800 at 38,000 gas, 1,500 at 255,000 gas |

## Check the files

- Windows: run `certutil -hashfile <file> SHA256` and compare the result with the line for that file in `SHA256SUMS.txt`.
- Mac or Linux: run `sha256sum -c SHA256SUMS.txt` inside a run folder.

The checksums show the files were not changed after the script wrote them. They do not prove the chain data is true. To check that, repeat the queries yourself against `https://mainnet-rpc.rayls.com`.

## Limits

- One public RPC endpoint, one machine, one connection. The finality runs are three short windows; the capacity runs are three samples of about seven minutes.
- Signer positions assume the bitmap follows the order of the committee list. No signature was verified.
- No transactions were sent, so there is no submit-to-receipt latency here.
- `rayls_latestHeader` returned an internal error, so commit pace was not measured directly.
- The throughput ceiling is an upper bound from the gas limit. It is not a load test, and it says nothing about how fast nodes can execute full blocks.
- Fee figures assume the gas token has 18 decimals and that one USDr is worth one dollar. Neither was tested.
