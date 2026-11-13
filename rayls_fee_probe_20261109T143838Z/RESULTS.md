# Rayls capacity and fee probe results

- Run started: 2026-11-09T14:38:38.190Z
- Run finished: 2026-11-09T14:40:36.120Z
- Endpoint: https://mainnet-rpc.rayls.com
- Chain ID: 72957
- Client version: 1.4.2 (b19896a12cfc1f1f775c33196c940f3345c00ede)
- Script: rayls_fee_probe.py v1.0, Python 3.14.8

## Fee history (last blocks)

```
{
 "blocks": 1024,
 "first_block": 14160161,
 "last_block": 14161184,
 "distinct_base_fee_values": 1,
 "base_fee_changes_between_consecutive_blocks": 0,
 "base_fee_wei_min_median_max": [
  48000000000,
  48000000000.0,
  48000000000
 ],
 "gas_used_ratio_mean": 3e-06,
 "gas_used_ratio_max": 0.0005094,
 "blocks_with_zero_gas_used": 1006
}
```

## Block sample (newest blocks, one by one)

```
{
 "blocks_read": 300,
 "first_block": 14160885,
 "last_block": 14161184,
 "timestamp_span_s": 403,
 "distinct_gas_limits": [
  500000000
 ],
 "blocks_per_second": 0.7419,
 "total_transactions": 8,
 "transactions_per_second": 0.0199,
 "transactions_per_block_mean_max": [
  0.027,
  3
 ],
 "blocks_with_zero_transactions": 296,
 "gas_used_ratio_mean_max": [
  4e-06,
  0.000509
 ]
}
```

## Gas limit and base fee at epoch boundaries

```
{
 "newest_epoch": 192,
 "boundary_blocks_read": 12,
 "distinct_gas_limits_over_time": [
  500000000
 ],
 "distinct_base_fees_over_time": 1,
 "base_fee_wei_min_median_max": [
  48000000000,
  48000000000.0,
  48000000000
 ]
}
```

## Calculations

```
{
 "gas_limit_newest_block": 500000000,
 "base_fee_wei_newest_block": 48000000000,
 "base_fee_gwei_newest_block": 48.0,
 "blocks_per_second_in_sample": 0.7419,
 "max_plain_transfer_21000_gas_per_block": 23809,
 "max_plain_transfer_21000_gas_tps_at_sample_block_pace": 17664,
 "max_erc20_transfer_65000_gas_assumed_per_block": 7692,
 "max_erc20_transfer_65000_gas_assumed_tps_at_sample_block_pace": 5707,
 "gas_per_second_capacity": 370950000,
 "gas_per_second_needed_for_15000_plain_transfers": 315000000,
 "capacity_as_multiple_of_15000_tps_plain": 1.1776,
 "block_pace_needed_for_15000_plain_tps_at_this_gas_limit_blocks_per_s": 0.63,
 "fee_for_21000_gas_native_units_if_18_decimals": 0.001008,
 "fee_for_65000_gas_native_units_if_18_decimals": 0.00312
}
```

## Assumptions and limits

- Throughput ceiling = gas limit x blocks per second / gas per transaction. It is an upper bound set by the gas limit;
  network, storage and execution speed can make the real limit lower.
- A plain transfer uses 21,000 gas. The 65,000 gas figure for a token transfer is an assumption, not a measurement.
- Fees assume the native gas token has 18 decimals. Whether 1 USDr equals 1 USD is not tested here.
- Usage figures come from one short window and one quiet or busy moment, not the chain's whole history.
- Block timestamps are whole seconds, so rates over short spans carry rounding error.
