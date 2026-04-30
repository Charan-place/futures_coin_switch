"""
StrategyAgent — online contextual-bandit learner for the trading bot
─────────────────────────────────────────────────────────────────────
Purpose:
    Make the bot smarter after every closed trade by tracking which
    (strategy, symbol) combinations have an edge and which do not, then
    multiplying each strategy's raw confidence by a learned factor when
    the confluence engine evaluates a new setup.

Why bandit instead of "deep RL" (DQN/PPO)?
    • Deep RL needs tens of thousands of episodes to converge and is
      famously fragile on noisy financial data — it'll overfit to one
      regime and break in the next.
    • Bandits with EWMA priors are the textbook tool for "online
      decision-making with delayed reward and few samples". They are
      the same family of algorithms used in production ad-ranking,
      slot-machine auto-tuning, and trade-routing.
    • This implementation is fully transparent — you can read every
      number it has learned in `data/agent_state.json` and audit it.

Reward signal:
    R = pnl_after_costs / (RISK_PER_TRADE_PCT × balance_at_entry)
    i.e. the trade's R-multiple (e.g. +1.8R, −1.0R). This is
    cost-aware (pnl already has fees+TDS deducted by the executor).

Edge metric (per arm):
    score = α · ewma_R + β · (ewma_winrate − 0.5)
    where ewma_R is the exponentially-weighted average R-multiple and
    ewma_winrate is the EWMA win rate. Both updated with a half-life
    set in the agent state.

Confidence multiplier:
    After at least `MIN_TRIALS` closed trades on an arm, the multiplier
    is `1 + clip(score, -1, +1) × MAX_BOOST`. Cold-start multiplier is
    1.0 (no information ⇒ no opinion).
"""
from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Optional

from monitoring.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ArmState:
    trials: int = 0
    wins: int = 0
    losses: int = 0
    ewma_winrate: float = 0.5    # neutral prior
    ewma_r_multiple: float = 0.0  # neutral prior (no edge)
    last_update: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class StrategyAgent:
    """
    Online learner. Keys arms by (strategy_name, symbol). Persisted to
    `state_path` (JSON) so learning survives restarts.
    """

    # Tunables — exposed as attributes so settings can override at construct.
    MIN_TRIALS_FOR_BOOST = 5      # below this, multiplier stays 1.0
    EWMA_ALPHA = 0.30             # higher = react faster, more variance
    MAX_BOOST = 0.40              # max ±40% nudge to confidence
    SCORE_R_WEIGHT = 0.7          # α
    SCORE_WIN_WEIGHT = 0.3        # β

    def __init__(self, state_path: str = "data/agent_state.json"):
        self._lock = threading.Lock()
        self.state_path = state_path
        self.arms: Dict[str, ArmState] = {}
        self.global_trades: int = 0
        self.global_pnl: float = 0.0
        self.created_at: str = datetime.utcnow().isoformat() + "Z"
        self._load()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not os.path.isfile(self.state_path):
            logger.info(f"agent: fresh state, no prior at {self.state_path}")
            return
        try:
            with open(self.state_path, "r") as f:
                payload = json.load(f)
            self.created_at = payload.get("created_at", self.created_at)
            self.global_trades = int(payload.get("global_trades", 0))
            self.global_pnl   = float(payload.get("global_pnl", 0.0))
            for k, v in (payload.get("arms") or {}).items():
                self.arms[k] = ArmState(**v)
            logger.info(f"agent: loaded {len(self.arms)} arms, "
                        f"{self.global_trades} trades from {self.state_path}")
        except Exception as e:
            logger.warning(f"agent: load failed ({e}); starting fresh")

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        with self._lock:
            payload = {
                "created_at": self.created_at,
                "saved_at": datetime.utcnow().isoformat() + "Z",
                "global_trades": self.global_trades,
                "global_pnl": round(self.global_pnl, 4),
                "arms": {k: v.as_dict() for k, v in self.arms.items()},
            }
            tmp = self.state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, self.state_path)

    # ── lookup / update ──────────────────────────────────────────────────────

    @staticmethod
    def _arm_key(strategy: str, symbol: str) -> str:
        return f"{strategy}::{symbol}"

    def _get(self, strategy: str, symbol: str) -> ArmState:
        key = self._arm_key(strategy, symbol)
        if key not in self.arms:
            self.arms[key] = ArmState()
        return self.arms[key]

    def confidence_multiplier(self, strategy: str, symbol: str) -> float:
        """Multiplier in roughly [1 − MAX_BOOST, 1 + MAX_BOOST]."""
        arm = self._get(strategy, symbol)
        if arm.trials < self.MIN_TRIALS_FOR_BOOST:
            return 1.0
        score = (
            self.SCORE_R_WEIGHT * math.tanh(arm.ewma_r_multiple)
            + self.SCORE_WIN_WEIGHT * (arm.ewma_winrate - 0.5) * 2
        )
        score = max(-1.0, min(1.0, score))
        return 1.0 + score * self.MAX_BOOST

    def record_outcome(
        self,
        strategy: str,
        symbol: str,
        r_multiple: float,
        pnl: float,
    ) -> None:
        """
        Call once per CLOSED trade. `r_multiple` should be
        pnl / risk_amount, e.g. +1.5 for a clean 1:1.5 winner. This
        method is cost-aware iff `pnl` is already net of fees+TDS.
        """
        with self._lock:
            arm = self._get(strategy, symbol)
            arm.trials += 1
            won = pnl > 0
            if won:
                arm.wins += 1
            else:
                arm.losses += 1
            a = self.EWMA_ALPHA
            arm.ewma_winrate = (1 - a) * arm.ewma_winrate + a * (1.0 if won else 0.0)
            arm.ewma_r_multiple = (1 - a) * arm.ewma_r_multiple + a * r_multiple
            arm.last_update = datetime.utcnow().isoformat() + "Z"
            self.global_trades += 1
            self.global_pnl += pnl

        try:
            self.save()
        except Exception as e:
            logger.warning(f"agent: save failed ({e})")

        # Audit line in the bot log
        mult = self.confidence_multiplier(strategy, symbol)
        logger.info(
            f"agent: learned {strategy}|{symbol} R={r_multiple:+.2f} pnl={pnl:+.4f} "
            f"→ wr={arm.ewma_winrate:.2f} ewmaR={arm.ewma_r_multiple:+.2f} mult={mult:.2f}"
        )

    # ── inspection ───────────────────────────────────────────────────────────

    def top_arms(self, n: int = 5) -> list:
        items = []
        for key, arm in self.arms.items():
            if arm.trials < self.MIN_TRIALS_FOR_BOOST:
                continue
            score = (
                self.SCORE_R_WEIGHT * math.tanh(arm.ewma_r_multiple)
                + self.SCORE_WIN_WEIGHT * (arm.ewma_winrate - 0.5) * 2
            )
            items.append((key, arm, score))
        items.sort(key=lambda x: x[2], reverse=True)
        return items[:n]

    def summary(self) -> dict:
        return {
            "arms_total": len(self.arms),
            "arms_learned": sum(
                1 for a in self.arms.values() if a.trials >= self.MIN_TRIALS_FOR_BOOST
            ),
            "global_trades": self.global_trades,
            "global_pnl": round(self.global_pnl, 4),
        }


_singleton: Optional[StrategyAgent] = None


def get_agent() -> StrategyAgent:
    global _singleton
    if _singleton is None:
        _singleton = StrategyAgent()
    return _singleton
