# Factor Architecture Reference

## BaseFactor ABC (app/factors/base.py)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import pandas as pd

@dataclass
class FactorResult:
    scores: dict[str, float]          # ticker → z-scored value
    metadata: dict[str, Any]          # status, date, scored_count, params
    diagnostics: dict[str, Any] | None = None

class BaseFactor(ABC):
    name: str = "abstract_factor"
    required_data: list[str] = ["ohlcv"]

    @abstractmethod
    def _compute(self, **kwargs) -> FactorResult: ...

    def compute(self, **kwargs) -> FactorResult:
        result = self._compute(**kwargs)
        result.metadata.setdefault("factor_name", self.name)
        return result

    @staticmethod
    def zscore(scores: dict[str, float]) -> dict[str, float]:
        series = pd.Series(scores)
        if series.std() == 0: return {k: 0.0 for k in scores}
        return ((series - series.mean()) / series.std()).to_dict()
```

## Registry (app/factors/registry.py)

```python
from app.factors.registry import Registry, get_registry

reg = get_registry()
reg.register(MyFactor())
results = reg.run_all(root=".", date_stamp="20260705")
# results = {"technical": FactorResult, "sentiment": FactorResult, ...}
```

## Adding a new factor

1. Create `app/factors/myfactor.py`
2. Subclass `BaseFactor`, implement `_compute()`
3. Import and register in `app/factors/registry.py` (both `_default.register_all(...)`)
4. Run `ruff check --fix` on new file

## Existing factors

| Name | Class | Source | Features |
|------|-------|--------|----------|
| technical | `TechnicalFactor` | `_feature_matrix()` | entropy, hurst, realized_vol_z60_lag1 |
| sentiment | `SentimentFactor` | WebZ + FinViz JSON | dictionary-based news scores |
| insider | `InsiderFactor` | `data/insider_trades/insider_scores.json` | SEC Form 4 buy/sell ratio |

## Path resolution warning

Factors in `app/factors/` may need `sys.path.insert(0, "deploy")` because the `src.na.features` module lives under `deploy/`. This is resolved by setting PYTHONPATH in the cron wrapper scripts, but when running `python -c` inline, prepend both `"."` and `"deploy"` to sys.path.