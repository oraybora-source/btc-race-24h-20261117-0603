[![make.fun](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/oraybora-source/btc-race-24h-20261117-0603/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/oraybora-source/btc-race-24h-20261117-0603/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603)

# DipBuyer — cbBTC mean-reversion bot

Entry for the [make.fun bounty btc-race-24h-20261117-0603](https://make.fun/bounty/btc-race-24h-20261117-0603): race a BTC trading bot live for 24 hours. The bot trades cbBTC (Bitcoin on Solana) against USDC on a 1-minute bar feed, long only, one position at most, no leverage, no shorts.

## Strategy

Rule-based, model-free, deterministic. No network, no wall clock, no randomness. Python 3.13, standard library only, plus the kit's vendored SDK shim under `vendor/` (copied byte-for-byte, excluded from authorship).

**Why mean reversion, not trend following.** The previous BTC race bot waited for a 3% dip that never came and made 0 trades ($0). A trend-following version of this bot (EMA crossover) lost money in backtesting: on this market, momentum does NOT persist — after a 30-minute rise of 100 bps or more, the next 30 minutes average −122 bps. After a 30-minute fall of 80 bps or more, the next 30 minutes average +21 bps (median +33 bps, 84% of cases recover). Sharp moves revert; they do not continue. So this bot buys the dip and rides the recovery with a trailing stop.

**Rules** (all in 1-minute bars / basis points):
- **Buy** when the 30-minute return is at or below −80 bps (a deep dip, not a shallow wobble). Spends 99% of cash.
- **Sell** when the close falls 80 bps below the highest close since entry (trailing stop — lets winners run, cuts the reversal), or the unrealised loss reaches −100 bps (hard stop-loss), or after 480 bars (8 hours) at most.
- No take-profit and no recovery exit: the trailing stop decides.
- After an exit, wait 15 bars before re-entering.
- `max_slippage_bps` is 150, so a normal 1-minute gap never rejects an order.

## Backtest (24h dev window, kit dataset, local replay driver)

| Metric | Value |
|---|---|
| Net PnL (after all fees) | **+$21.95 USDC** |
| Trades | 4 (2 round trips, both winners) |
| Win rate (round trips) | 100% |
| Max drawdown | 1.48% |
| Dev gate (PnL > 0, ≥1 trade, max DD ≤ 25%) | **PASS** |

Trade log: buy $64,087.51 → sell $64,838.39 (+$9.51); buy $64,295.01 → sell $65,225.78 (+$12.44). Two runs produce byte-identical action logs (deterministic). The parameter neighbourhood around the chosen values (trailing stop 70–100 bps, max hold 240–720 bars) is also profitable, so this is a robust region, not a single sharp peak.

## Risks and limits

- The bot only trades on deep dips (30-minute return ≤ −80 bps). On a quiet day with no such dip it may make few or no trades; the dev window had two such dips. A shallower dip threshold trades more often but was unprofitable in backtesting, so the deep threshold was kept.
- The live race window is a different 24 hours: past recoveries do not guarantee future ones. The trailing stop (80 bps) and hard stop-loss (−100 bps) cap the loss on any single trade, and max drawdown on the dev window was 1.48% (limit 25%).
- The official `grade-local` runner could not be run locally for this Python bot (it needs Docker, which is not available on this machine); the numbers above come from a local replay driver that re-implements the harness fill model (next-open fill, 4 bps fee, 2 bps slippage, constant-product impact vs the bar's open depth, final flatten at the last close).

## Files

- `main.py` — the bot (entry point, `python3 -P -s main.py`).
- `vendor/makefun_bars.py` — the kit's SDK shim, byte-for-byte copy.
- `LICENSE` — MIT.
- `.makefun/owner.json` — payout wallet.

## License

MIT. See `LICENSE`.
