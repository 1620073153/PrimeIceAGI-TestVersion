from copy import deepcopy
from dataclasses import dataclass, field


@dataclass(slots=True)
class RoundContext:
    current_round: int
    strategy: dict = field(default_factory=dict)
    token_budget_ratio: float | None = None

    def __post_init__(self) -> None:
        self.strategy = deepcopy(self.strategy)

    def snapshot(self) -> dict:
        return {
            "current_round": self.current_round,
            "strategy": deepcopy(self.strategy),
            "token_budget_ratio": self.token_budget_ratio,
        }
