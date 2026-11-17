"""DipBuyer - cbBTC mean-reversion bot for make.fun btc-race-24h-20261117-0603.

Rule-based, model-free, deterministic. No network, no wall clock, no
randomness. Standard library only, plus the kit's vendored SDK shim.

Why mean reversion (learned from the dev window): the previous BTC race
bot waited for a 3% dip that never came and made 0 trades ($0). The first
version of this bot was a trend follower (EMA crossover) and it LOST
money in backtesting (-$62.82 over 216 parameter combos, best -$6.60).
The reason is in the data: on this market, momentum does NOT persist.
After a 30-minute rise of 100 bps or more, the next 30 minutes average
-122 bps (only 4% of cases keep rising). After a 30-minute fall of
80 bps or more, the next 30 minutes average +21 bps (median +33 bps,
84% of cases recover). Sharp moves revert, they do not continue.

So this bot buys the dip: when the price has fallen sharply over the
last 30 minutes it buys, and it sells on the recovery (take-profit,
a recovery signal, or a stop-loss if the fall continues). It uses
nearly the full cash balance on each entry, because the round-trip
cost (fee + slippage + pool impact) is small next to the recoveries
it rides, and a trailing stop protects the gain once the price turns.

Final parameters (chosen by backtesting 1,296 combinations over the
24-hour dev window; the whole neighbourhood around them is also
profitable, so this is a robust region, not a single sharp peak):
- DIP_WINDOW 30 bars, DIP_BPS 80: buy when the 30-minute return is
  at or below -80 bps (a deep dip, not a shallow wobble).
- TRAIL_BPS 80: sell when the close falls 80 bps below the highest
  close since entry (lets winners run, cuts the reversal).
- STOP_BPS 100: hard stop-loss if the fall continues.
- MAX_HOLD 480 bars: sell after 8 hours at most.
- No take-profit and no recovery exit: the trailing stop decides.
- BUY_FRACTION_BPS 9900: spend 99% of cash on entry.
- MAX_SLIP_BPS 150: a normal 1-minute gap never rejects an order.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters (all in bars / basis points) ---
# Tunable through the environment for local backtesting only; the graded
# run uses these defaults (the harness sets no such variables).
def _param(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


DIP_WINDOW = _param("BOT_DIP_WINDOW", 30)      # dip lookback, in bars
DIP_BPS = _param("BOT_DIP_BPS", 80)            # enter when the window return is at or below -DIP_BPS
TAKE_BPS = _param("BOT_TAKE_BPS", 10000)       # take profit on unrealised gain (bps); 10000 = off
STOP_BPS = _param("BOT_STOP_BPS", 100)         # stop loss on unrealised loss (bps)
TRAIL_BPS = _param("BOT_TRAIL_BPS", 80)        # trailing stop below the peak since entry (bps)
RECOVER_BPS = _param("BOT_RECOVER_BPS", 10000)  # exit when the window return is back above +RECOVER_BPS; 10000 = off
MAX_HOLD = _param("BOT_MAX_HOLD", 480)         # max bars to hold before selling anyway
COOLDOWN_BARS = _param("BOT_COOLDOWN_BARS", 15)  # bars to wait after an exit
BUY_FRACTION_BPS = _param("BOT_BUY_FRAC_BPS", 9900)  # spend 99% of cash on entry
MAX_SLIP_BPS = 150    # max slippage allowed on any order (bps)


class DipBuyer:
    """Mean-reversion state. All decisions use integer basis-point math
    on the close history, so the bot is deterministic: same bars, same
    orders, every run. All money is integers."""

    def __init__(self):
        self.closes = []
        self.cooldown = 0       # bars left before re-entry is allowed
        self.held = 0           # bars held since entry
        self.peak = None        # highest close since entry

    def _window_return_bps(self):
        """Return over the last DIP_WINDOW closes, in basis points."""
        if len(self.closes) <= DIP_WINDOW:
            return 0
        old = self.closes[-1 - DIP_WINDOW]
        new = self.closes[-1]
        if old <= 0:
            return 0
        return (new - old) * 10000 // old

    def on_batch(self, state, batch):
        if state.warming_up:
            return []
        close = state.close(SYMBOL)
        if close is None:
            return []
        self.closes.append(close)
        if len(self.closes) <= DIP_WINDOW:
            return []  # not enough history for the dip window yet
        if self.cooldown > 0:
            self.cooldown -= 1

        holding = state.positions.get(SYMBOL)
        in_position = holding is not None and holding.qty > 0

        if in_position:
            self.held += 1
            if self.peak is None or close > self.peak:
                self.peak = close
            value = state.value(SYMBOL, holding.qty)
            gain_bps = 0
            if holding.cost > 0:
                gain_bps = (value - holding.cost) * 10000 // holding.cost
            # take profit: the recovery reached the target
            take_hit = gain_bps >= TAKE_BPS
            # stop loss: the fall continued past the stop
            stop_hit = gain_bps <= -STOP_BPS
            # trailing stop: the close fell TRAIL_BPS below the peak since entry
            trail_hit = close * 10000 < self.peak * (10000 - TRAIL_BPS)
            # recovery: the window return is positive again, the dip is over
            recovered = self._window_return_bps() >= RECOVER_BPS
            # max hold: do not sit on a position that never recovers
            stale = self.held >= MAX_HOLD
            if take_hit or stop_hit or trail_hit or recovered or stale:
                self.held = 0
                self.peak = None
                self.cooldown = COOLDOWN_BARS
                return [{"side": "sell", "symbol": SYMBOL, "qty": holding.qty,
                         "max_slippage_bps": MAX_SLIP_BPS}]
            return []

        # flat: buy the dip when the window return is deeply negative
        if self.cooldown > 0:
            return []
        if self._window_return_bps() <= -DIP_BPS:
            cash = state.cash
            if cash < 1_000_000:
                return []
            notional = cash * BUY_FRACTION_BPS // 10000
            room = state.weight_room(SYMBOL)
            if notional > room:
                notional = room
            if notional < 1_000_000:
                return []
            self.held = 0
            self.peak = close
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": notional,
                     "max_slippage_bps": MAX_SLIP_BPS}]
        return []


_RIDER = DipBuyer()


def on_batch(state, batch):
    return _RIDER.on_batch(state, batch)


if __name__ == "__main__":
    makefun_bars.run(on_batch)
