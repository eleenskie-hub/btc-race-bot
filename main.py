"""Dip-bounce bot for the make.fun BTC race (agent-fun/bars-replay/v1).

Strategy (long only, single symbol CBBTC, all-in/all-out):
  - Stay in cash. When the close has fallen at least 0.70% over the last
    40 one-minute bars, buy with all cash at the next open.
  - While holding, sell everything at the next open when any of these hits:
    gain >= +1.10% versus the average fill price (fees included),
    loss <= -1.50%, or 360 bars (6 hours) have passed since the fill.
  - After an exit the same dip rule may re-enter on a later bar.

Rationale: on the published dev window BTC drifted down ~1% with repeated
sharp dips that bounced; trend-following and buy-and-hold both lost money
there after the ~26 bps full-size round-trip cost, while deep-dip entries
(0.6-0.7% over 35-45 bars) with a 1.0-1.2% take-profit were consistently
positive across the whole parameter neighbourhood. Deterministic: no clock,
no randomness, no network, standard library only.
"""

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, "vendor"))
sys.path.insert(0, _here)
import makefun_bars

SYMBOL = "CBBTC"
LOOKBACK = 40            # bars for the dip measurement
DIP = 0.0070             # buy when trailing return <= -0.70%
TAKE_PROFIT = 0.0110     # sell at +1.10% over average fill price (cost incl. fees)
STOP_LOSS = 0.0150       # sell at -1.50%
MAX_HOLD = 360           # sell after 360 bars regardless
MAX_SLIPPAGE_BPS = 10_000

_closes = []             # latest close per batch (scaled ints), in order
_entry_seq = None        # batch seq at which the current position appeared


def _avg_entry_price(state, holding):
    """Average fill price (scaled int units) implied by the position's cost."""
    quote_scale = int(state.hello["capital"]["quote_scale"])
    sym = state.symbols[SYMBOL]
    factor = 10 ** (int(sym["qty_scale"]) + int(sym["price_scale"]) - quote_scale)
    return holding.cost * factor / holding.qty


def on_batch(state, batch):
    global _entry_seq
    close = state.close(SYMBOL)
    if close is None:
        return []
    _closes.append(close)

    holding = state.positions.get(SYMBOL)
    if holding is not None and _entry_seq is None:
        _entry_seq = state.seq

    if holding is None:
        _entry_seq = None
        if len(_closes) > LOOKBACK and state.cash >= 1_000_000:
            then = _closes[-1 - LOOKBACK]
            if then and close / then - 1.0 <= -DIP:
                return [{
                    "side": "buy",
                    "symbol": SYMBOL,
                    "notional_quote_units": state.cash,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }]
        return []

    gain = close / _avg_entry_price(state, holding) - 1.0
    held = state.seq - (_entry_seq if _entry_seq is not None else state.seq)
    if gain >= TAKE_PROFIT or gain <= -STOP_LOSS or held >= MAX_HOLD:
        return [{
            "side": "sell",
            "symbol": SYMBOL,
            "qty": holding.qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]
    return []


if __name__ == "__main__":
    makefun_bars.run(on_batch)
