#!/usr/bin/env python3
"""Rayls capacity and fee probe: what the chain's own parameters say about throughput, usage and cost.

Read-only, standard library only, sends no transactions. Steps:
  1. identity      chain id, client version, newest block (gas limit, gas used, base fee)
  2. fee history   eth_feeHistory for the last 1024 blocks: base fee and gas-used ratio per block
  3. block sample  the newest N blocks one by one: transactions, gas used, gas limit, timestamp
  4. history       gas limit and base fee at epoch boundaries across the chain's life (rayls_epochRecord)
Then it calculates a throughput ceiling from the gas limit and block pace, observed usage, and the fee per transfer.
Output: a folder with raw logs, CSVs, RESULTS.md and SHA256SUMS.txt.
Example: python3 rayls_fee_probe.py
"""
import argparse, csv, hashlib, json, math, os, platform, re, statistics, sys, time, urllib.request
from datetime import datetime, timezone

VERSION = "3.0"
DEFAULT_RPC = "https://mainnet-rpc.rayls.com"


def iso(t=None):
    t = time.time() if t is None else t
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


class Rpc:
    """Minimal JSON-RPC client that logs every request and response."""

    def __init__(self, url, log_path, timeout=20):
        self.url, self.timeout, self.n = url, timeout, 0
        self.log = open(log_path, "w", encoding="utf-8")

    def call(self, method, params=None):
        self.n += 1
        body = {"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or []}
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "rayls-finality-probe/" + VERSION})
        t_wall, t0 = time.time(), time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                text = r.read().decode("utf-8", "replace")
            try:
                resp = json.loads(text)
            except ValueError:
                resp = {"non_json_response": text[:300]}
        except Exception as e:  # network or HTTP error
            resp = {"transport_error": repr(e)}
        rtt = time.perf_counter() - t0
        self.log.write(json.dumps({"t_utc": iso(t_wall), "rtt_s": round(rtt, 4),
                                   "request": body, "response": resp}) + "\n")
        self.log.flush()
        return resp, rtt


def ok(resp):
    return isinstance(resp, dict) and resp.get("result") is not None


def to_int(x):
    try:
        return int(x, 16) if isinstance(x, str) and x.startswith("0x") else int(x)
    except (TypeError, ValueError):
        return None


A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58decode(text):
    n = 0
    for ch in text:
        n = n * 58 + A58.index(ch)
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(text) - len(text.lstrip("1"))) + body


def roaring_positions(b):
    """Decode a portable Roaring bitmap made of array containers (what a small signer set uses)."""
    try:
        if int.from_bytes(b[0:4], "little") != 12346:
            return None
        size, pos, desc = int.from_bytes(b[4:8], "little"), 8, []
        for _ in range(size):
            desc.append((int.from_bytes(b[pos:pos + 2], "little"), int.from_bytes(b[pos + 2:pos + 4], "little") + 1))
            pos += 4
        offs = []
        for _ in range(size):
            offs.append(int.from_bytes(b[pos:pos + 4], "little"))
            pos += 4
        out = []
        for (key, card), off in zip(desc, offs):
            if card > 4096:
                return None
            out += [(key << 16) | int.from_bytes(b[off + 2 * i:off + 2 * i + 2], "little") for i in range(card)]
        return sorted(out)
    except Exception:
        return None


def parse_epoch(resp):
    res = resp.get("result") if isinstance(resp, dict) else None
    rec = cert = None
    for it in (res if isinstance(res, list) else [res]):
        if isinstance(it, dict):
            rec = it if "committee" in it else rec
            cert = it if "signed_authorities" in it else cert
    return rec, cert


def newest_epoch(rpc, cap=20000):
    def exists(e):
        return parse_epoch(rpc.call("rayls_epochRecord", [e])[0])[0] is not None
    if not exists(1):
        return None
    lo, hi = 1, 2
    while hi < cap and exists(hi):
        lo, hi = hi, hi * 2
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if exists(mid) else (lo, mid)
    return lo




VERSION = "1.0"
DEFAULT_RPC = "https://mainnet-rpc.rayls.com"
PLAIN_GAS, ERC20_GAS, CLAIMED_TPS = 21000, 65000, 15000


def block(rpc, n):
    tag = n if isinstance(n, str) else hex(n)
    r, _ = rpc.call("eth_getBlockByNumber", [tag, False])
    b = r.get("result") if isinstance(r, dict) else None
    if not isinstance(b, dict):
        return None
    return {"number": to_int(b.get("number")), "timestamp": to_int(b.get("timestamp")),
            "gas_limit": to_int(b.get("gasLimit")), "gas_used": to_int(b.get("gasUsed")),
            "base_fee": to_int(b.get("baseFeePerGas")), "txs": len(b.get("transactions") or [])}


def write_csv(path, rows, cols):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def mmm(vals):
    return [min(vals), round(statistics.median(vals), 6), max(vals)] if vals else None


def fee_history(rpc, count, outdir):
    r, _ = rpc.call("eth_feeHistory", [hex(count), "latest", []])
    res = r.get("result") if isinstance(r, dict) else None
    if not isinstance(res, dict) or not res.get("gasUsedRatio"):
        return {"error": r.get("error") or r}
    oldest = to_int(res.get("oldestBlock"))
    ratios = [float(x) for x in res["gasUsedRatio"]]
    fees = [to_int(x) for x in (res.get("baseFeePerGas") or [])][: len(ratios)]
    rows = [{"block": oldest + i, "base_fee_wei": fees[i] if i < len(fees) else "", "gas_used_ratio": ratios[i]}
            for i in range(len(ratios))]
    write_csv(os.path.join(outdir, "fee_history.csv"), rows, ["block", "base_fee_wei", "gas_used_ratio"])
    fv = [x for x in fees if x is not None]
    changes = sum(1 for a, b in zip(fv, fv[1:]) if a != b)
    return {"blocks": len(ratios), "first_block": oldest, "last_block": oldest + len(ratios) - 1,
            "distinct_base_fee_values": len(set(fv)), "base_fee_changes_between_consecutive_blocks": changes,
            "base_fee_wei_min_median_max": mmm(fv),
            "gas_used_ratio_mean": round(statistics.mean(ratios), 6), "gas_used_ratio_max": max(ratios),
            "blocks_with_zero_gas_used": sum(1 for x in ratios if x == 0)}


def sample_blocks(rpc, n, outdir):
    latest = block(rpc, "latest")
    if not latest or latest["number"] is None:
        return {"error": "could not read the newest block"}, None
    rows = []
    for k in range(n):
        b = block(rpc, latest["number"] - k)
        if b:
            rows.append(b)
    rows.sort(key=lambda x: x["number"])
    write_csv(os.path.join(outdir, "block_sample.csv"), rows, ["number", "timestamp", "gas_limit", "gas_used", "base_fee", "txs"])
    span = rows[-1]["timestamp"] - rows[0]["timestamp"] if len(rows) > 1 else 0
    txs = [r["txs"] for r in rows]
    ratios = [r["gas_used"] / r["gas_limit"] for r in rows if r["gas_limit"] and r["gas_used"] is not None]
    out = {"blocks_read": len(rows), "first_block": rows[0]["number"], "last_block": rows[-1]["number"],
           "timestamp_span_s": span, "distinct_gas_limits": sorted(set(r["gas_limit"] for r in rows)),
           "blocks_per_second": round((len(rows) - 1) / span, 4) if span else None,
           "total_transactions": sum(txs), "transactions_per_second": round(sum(txs) / span, 4) if span else None,
           "transactions_per_block_mean_max": [round(statistics.mean(txs), 3), max(txs)],
           "blocks_with_zero_transactions": sum(1 for t in txs if t == 0),
           "gas_used_ratio_mean_max": [round(statistics.mean(ratios), 6), round(max(ratios), 6)] if ratios else None}
    return out, latest


def boundary_history(rpc, step, outdir):
    newest = newest_epoch(rpc)
    if newest is None:
        return {"error": "rayls_epochRecord gave no usable answer"}
    epochs = sorted(set([0, 1, newest] + list(range(step, newest + 1, step))))
    rows = []
    for e in epochs:
        rec, _ = parse_epoch(rpc.call("rayls_epochRecord", [e])[0])
        num = (rec.get("parent_state") or {}).get("number") if rec else None
        b = block(rpc, num) if isinstance(num, int) else None
        if b:
            rows.append({"epoch": e, **b})
    write_csv(os.path.join(outdir, "epoch_boundary_blocks.csv"), rows, ["epoch", "number", "timestamp", "gas_limit", "gas_used", "base_fee", "txs"])
    gl = [r["gas_limit"] for r in rows if r["gas_limit"] is not None]
    bf = [r["base_fee"] for r in rows if r["base_fee"] is not None]
    return {"newest_epoch": newest, "boundary_blocks_read": len(rows),
            "distinct_gas_limits_over_time": sorted(set(gl)), "distinct_base_fees_over_time": len(set(bf)),
            "base_fee_wei_min_median_max": mmm(bf)}


def calculations(latest, sample):
    G, bf = latest.get("gas_limit"), latest.get("base_fee")
    B = sample.get("blocks_per_second") if isinstance(sample, dict) else None
    out = {"gas_limit_newest_block": G, "base_fee_wei_newest_block": bf,
           "base_fee_gwei_newest_block": round(bf / 1e9, 9) if bf is not None else None,
           "blocks_per_second_in_sample": B}
    if G and B:
        for label, gas in (("plain_transfer_21000_gas", PLAIN_GAS), ("erc20_transfer_65000_gas_assumed", ERC20_GAS)):
            out[f"max_{label}_per_block"] = G // gas
            out[f"max_{label}_tps_at_sample_block_pace"] = round(G // gas * B)
        out["gas_per_second_capacity"] = round(G * B)
        out["gas_per_second_needed_for_15000_plain_transfers"] = CLAIMED_TPS * PLAIN_GAS
        out["capacity_as_multiple_of_15000_tps_plain"] = round(G * B / (CLAIMED_TPS * PLAIN_GAS), 4)
        out["block_pace_needed_for_15000_plain_tps_at_this_gas_limit_blocks_per_s"] = round(CLAIMED_TPS * PLAIN_GAS / G, 4)
    if bf is not None:
        out["fee_for_21000_gas_native_units_if_18_decimals"] = bf * PLAIN_GAS / 1e18
        out["fee_for_65000_gas_native_units_if_18_decimals"] = bf * ERC20_GAS / 1e18
    return out


def write_manifest(outdir):
    lines = []
    for name in sorted(os.listdir(outdir)):
        p = os.path.join(outdir, name)
        if name != "SHA256SUMS.txt" and os.path.isfile(p):
            with open(p, "rb") as f:
                lines.append(f"{sha256_bytes(f.read())}  {name}")
    with open(os.path.join(outdir, "SHA256SUMS.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


def write_results(outdir, args, started, ident, fh, bs, hist, calc):
    def blk(title, obj):
        return [f"## {title}", "", "```", json.dumps(obj, indent=1), "```", ""]
    L = ["# Rayls capacity and fee probe results", "", f"- Run started: {started}", f"- Run finished: {iso()}",
         f"- Endpoint: {args.rpc}", f"- Chain ID: {ident.get('chain_id_decimal')}",
         f"- Client version: {ident.get('client_version')}",
         f"- Script: {os.path.basename(sys.argv[0])} v{VERSION}, Python {platform.python_version()}", ""]
    L += blk("Fee history (last blocks)", fh) + blk("Block sample (newest blocks, one by one)", bs)
    L += blk("Gas limit and base fee at epoch boundaries", hist) + blk("Calculations", calc)
    L += ["## Assumptions and limits", "",
          "- Throughput ceiling = gas limit x blocks per second / gas per transaction. It is an upper bound set by the gas limit;",
          "  network, storage and execution speed can make the real limit lower.",
          "- A plain transfer uses 21,000 gas. The 65,000 gas figure for a token transfer is an assumption, not a measurement.",
          "- Fees assume the native gas token has 18 decimals. Whether 1 USDr equals 1 USD is not tested here.",
          "- Usage figures come from one short window and one quiet or busy moment, not the chain's whole history.",
          "- Block timestamps are whole seconds, so rates over short spans carry rounding error.", ""]
    with open(os.path.join(outdir, "RESULTS.md"), "w") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rpc", default=DEFAULT_RPC)
    ap.add_argument("--out", default=None, help="output folder (default: rayls_fee_probe_<UTC time>)")
    ap.add_argument("--fee-blocks", type=int, default=1024, help="blocks of eth_feeHistory to request")
    ap.add_argument("--blocks", type=int, default=300, help="newest blocks to read one by one (about 0.3 s each)")
    ap.add_argument("--history-step", type=int, default=20, help="sample every Nth epoch boundary (0 = skip)")
    args = ap.parse_args()
    started = iso()
    outdir = args.out or "rayls_fee_probe_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    os.makedirs(outdir, exist_ok=True)
    rpc = Rpc(args.rpc, os.path.join(outdir, "raw_rpc_log.jsonl"))
    print("1/4 identity ...")
    ident = {}
    for key, method in (("chain_id", "eth_chainId"), ("client_version", "web3_clientVersion")):
        r, _ = rpc.call(method)
        ident[key] = r["result"] if ok(r) else {"error": r.get("error") or r}
    ident["chain_id_decimal"] = to_int(ident["chain_id"]) if isinstance(ident["chain_id"], str) else None
    print("   ", ident)
    print(f"2/4 fee history ({args.fee_blocks} blocks) ...")
    fh = fee_history(rpc, args.fee_blocks, outdir)
    print("   ", fh)
    print(f"3/4 reading the newest {args.blocks} blocks one by one (about {args.blocks * 0.3:.0f} s) ...")
    bs, latest = sample_blocks(rpc, args.blocks, outdir)
    print("   ", bs)
    hist = {"skipped": True}
    if args.history_step > 0:
        print("4/4 gas limit and base fee at epoch boundaries ...")
        hist = boundary_history(rpc, args.history_step, outdir)
        print("   ", hist)
    calc = calculations(latest, bs) if latest else {"error": "no newest block"}
    print("Calculations:", json.dumps(calc, indent=1))
    rpc.log.close()
    write_results(outdir, args, started, ident, fh, bs, hist, calc)
    write_manifest(outdir)
    print(f"\nDone. Results are in {os.path.abspath(outdir)} (start with RESULTS.md).")


if __name__ == "__main__":
    main()
