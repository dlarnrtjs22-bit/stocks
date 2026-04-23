from __future__ import annotations

from dataclasses import dataclass

from engine.config import Grade, SignalConfig


@dataclass
class PositionPlan:
    entry_price: float
    stop_price: float
    target_price: float
    r_value: float
    position_size: float
    quantity: int
    r_multiplier: float


class PositionSizer:
    def __init__(self, capital: float, config: SignalConfig):
        self.capital = capital
        self.config = config

    def calculate(self, price: float, grade: Grade) -> PositionPlan:
        entry = float(price)
        # Design Ref: Design §5 Module B — trader_style에 따라 손절/익절 폭 선택
        style = str(getattr(self.config, "trader_style", "default") or "default").lower()
        if style == "scalper":
            stop_pct = float(getattr(self.config, "scalper_stop_loss_pct", self.config.stop_loss_pct))
            target_pct = float(getattr(self.config, "scalper_take_profit_pct", self.config.take_profit_pct))
        else:
            stop_pct = self.config.stop_loss_pct
            target_pct = self.config.take_profit_pct
        stop = round(entry * (1.0 - stop_pct), 2)
        target = round(entry * (1.0 + target_pct), 2)

        risk_per_share = max(entry - stop, 1e-6)
        r_value = self.capital * self.config.r_ratio
        r_multiplier = self.config.grade_configs[grade].r_multiplier
        risk_budget = r_value * r_multiplier

        quantity = int(risk_budget / risk_per_share) if risk_budget > 0 else 0
        position_size = round(quantity * entry, 2)

        return PositionPlan(
            entry_price=round(entry, 2),
            stop_price=stop,
            target_price=target,
            r_value=round(r_value, 2),
            position_size=position_size,
            quantity=max(quantity, 0),
            r_multiplier=r_multiplier,
        )

