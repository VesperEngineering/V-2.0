# Factor vs Nova Model Comparison

Pattern for comparing a factor-based ranking model against an existing
ensemble model (Vesper's `working_nova`). Used when evaluating whether
research findings actually improve decisions.

## Workflow

1. **Parse historical picks** from no-order reports — extract ticker basket
   per date from the daily no-order report markdown files using regex
   pattern `| \x60([A-Z]+)\x60 |.*selected by`. Store as JSON.
2. **Compute daily factor scores** from the feature panel — entropy + hurst
   + realized_vol_z60_lag1 + news_sentiment, equal-weighted
3. **Select top 5** by factor score each day
4. **Compare overlap** between factor picks and nova picks
5. **Forward-return attribution**: for each date, measure both models'
   10d forward returns. Track win rate, Sharpe, drawdown.
6. **Disagreement analysis**: when models pick different baskets, which
   one wins?

## Vesper Results (2026-07, 7 periods)

- Factor Sharpe -5.26 vs Nova -3.85 — both negative on noisy daily data
- **Factor wins 60% of periods**
- **Overlap only 9%** — completely different selection methodology
- When they disagree (5/7 periods), factor wins 60%
- Recommendation: nova_outperforms on Sharpe (lower variance)

## Key Insight: Orthogonal Signals

The 9% overlap means the two models select from completely different
logic — nova uses transformer ensemble consensus, factor uses entropy
+ sentiment + hurst. They're orthogonal, which means combining them
(factor-rescored nova candidates) should improve both. Factor tilt
within ensemble consensus preserves diversification while adding edge.

## Pareto Optimization Opportunity

- Factor model: higher win rate (60%), higher variance (worse Sharpe)
- Nova: lower win rate (40%), lower variance (better Sharpe)
- Combined: keep nova's candidates, rescore via factor ranks to tilt
  weights toward factor-favored names — gets the edge without the variance

## Parsing No-Order Reports

`scripts/_parse_nova_picks.py` extracts ticker baskets from all
`artifacts/evals/daily_no_order_report_*.md` files and writes
`data/nova_picks.json`. Run once to refresh pick history.
