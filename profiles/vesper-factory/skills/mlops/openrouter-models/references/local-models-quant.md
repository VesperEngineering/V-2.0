# Local Models for Quant Work (July 2026)

## Hardware

- **GPU**: RTX 5070 Ti 16GB GDDR7
- **CPU**: Ryzen 7 7700X
- **RAM**: 32GB DDR5
- **OS**: Windows 11 (Ollama with git-bash)

## Models Tested

| Model | Size | Ollama ID | Context |
|-------|------|-----------|---------|
| Qwen3 | 14B | `qwen3:14b` | 131,072 |
| Qwen2.5 | 14B | `qwen2.5:14b` | 32,768 |

## Coding Test

**Prompt**: Write a function `compute_intraday_range_factor` that computes (high-low)/close, 5-day rolling mean, normalizes by 20-day rolling std, returns series.

### qwen3:14b — ✓ Pass

```python
import pandas as pd

def compute_intraday_range_factor(df):
    daily_range = (df['high'] - df['low']) / df['close']
    rolling_5_mean = daily_range.rolling(window=5).mean()
    rolling_20_std = daily_range.rolling(window=20).std()
    result = (daily_range - rolling_5_mean) / rolling_20_std
    return pd.Series(result, index=df.index)
```

- Does NOT mutate the input DataFrame
- Preserves original index via `pd.Series(result, index=df.index)`
- Returns NaNs for first 19 rows (correct — not enough data for 20-day std)

### qwen2.5:14b — ⚠️ Issues

```python
import pandas as pd

def compute_intraday_range_factor(df):
    df['daily_range'] = (df['high'] - df['low']) / df['close']
    rolling_mean = df['daily_range'].rolling(window=5).mean()
    rolling_std = df['daily_range'].rolling(window=20).std()
    normalized_series = (df['daily_range'] - rolling_mean) / rolling_std
    return normalized_series.dropna()
```

- **Mutates the input** — adds `df['daily_range']` column as a side-effect
- **Unwanted `.dropna()`** — silently drops first 19 rows without asking
- No error handling, no docstring

## Reasoning Test

**Prompt**: Mean-reversion signal:
- Return < -2% + volume > 1.5x avg → predict +0.5%
- Return > +2% + volume > 1.5x avg → predict -0.5%
- Otherwise 0

Questions: (1) Sharpe ratio shape assumption? (2) Catastrophic failure regime? (3) Improve with intraday?

### qwen3:14b — ✓ Depth + Accuracy

1. **Assumes normally distributed returns with consistent volatility** — explicitly calls out skewness/kurtosis blind spot
2. **Fails in trending markets** where prices persist instead of reverting
3. **Use intraday volatility, order flow, time-of-day patterns** — specific, actionable

### qwen2.5:14b — ⚠️ Shallow + Inaccurate

1. Said "assumes a negative Sharpe ratio shape" — this is incorrect (mean-reversion signals typically have positive Sharpe with non-normal distribution)
2. Correctly identified trending markets as failure regime
3. Generic "refine entry/exit timing" — weak on specifics

## JSON Output

Both models produce valid JSON naturally at temperature ≤0.3 with just a schema description in the prompt. No special format constraint needed.

| Model | JSON Valid? | Quality |
|-------|-------------|---------|
| qwen3:14b | ✓ | Well-structured, appropriate confidence (0.65), concise reasoning |
| qwen2.5:14b | ✓ | Decent but verbose reasoning, confidence slightly high (0.75) |

## Speed Comparison

| Model | Simple query | Complex reasoning |
|-------|-------------|-------------------|
| qwen3:14b | ~6.6s | ~12s (1,258 tokens) |
| qwen2.5:14b | ~5.3s | ~4s (255 tokens) |

qwen2.5 is ~20% faster but generates less content. For equivalent output depth the gap narrows significantly.

## Qwen3 Quirk: Reasoning Token Budget

qwen3 emits reasoning inside `choices[0].message.reasoning` which counts toward `max_tokens`. At `max_tokens: 1000`, a coding prompt may get 800 reasoning + 200 code (truncated). Mitigations:
- Raise `max_tokens` to 1500-2000
- Use system prompt: "Output ONLY the code, no reasoning" (reduces but doesn't eliminate reasoning — depends on task complexity)
- System prompt: "You are a quant Python developer. Write clean, production-ready code." triggers useful reasoning that leads to better output

## Verdict

**qwen3:14b** is the clear winner for both Vesper Swing (real-time signal analysis) and quant Vesper (factor research):

1. Better reasoning depth — useful for signal logic analysis and statistical questions
2. Better code quality — no mutation side-effects, production-ready
3. JSON mode works naturally
4. The extra reasoning tokens are actually an asset for quant work, not overhead to eliminate

Use qwen2.5:14b only as a fallback when qwen3 is unavailable or when maximum speed is critical.
