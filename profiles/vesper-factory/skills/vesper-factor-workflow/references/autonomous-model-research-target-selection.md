# Autonomous Model Research Target Selection

## Trigger

Use this when the user asks how an autoresearch-style continuous experiment loop should improve Vesper, or asks what Vesper should train.

## Response order

1. Name one concrete Vesper model target in the first sentence.
2. State its inputs, label/horizon, objective, and output in compact form.
3. Explain why that target is the current bottleneck using live repository evidence.
4. Only then describe how an autonomous agent would iterate it.

Do not lead with sandbox architecture, governance machinery, generic reuse of the experiment loop, or a list of possible projects. The user is asking for an investment/research target, not an infrastructure lecture.

## Preferred target discovered in the 2026-07-16 review

Vesper already contains a cross-sectional transformer training substrate in `deploy/src/na/transformer_training.py`:

- chronological sequence construction;
- cross-sectional relative features;
- a `pairwise_rank` training objective;
- `pairwise_rank_loss` over forward-return ordering;
- GPU-backed PyTorch training.

The concrete target is a **21-session cross-sectional stock-ranking transformer**:

- input: trailing split-adjusted OHLCV, volatility, liquidity, and cross-sectional features from a frozen Vesper snapshot;
- label: 21-session forward total-return ordering within each as-of-date cross-section;
- objective: `pairwise_rank`;
- output: one challenger score per admitted stock.

Why: dated project evidence reported weak transformer rank skill (average rank IC about `0.002333`) and performance below equal weight. Re-inspect current receipts before quoting those numbers because they are a dated snapshot.

Use the tree ranker (`HistGradientBoostingRegressor`) as a simple control, not as the primary overnight GPU target. Existing tree-ranker planning currently names a 1-day label; Vesper evidence says the durable cross-sectional edge is generally 10–21 days, so do not inherit the 1-day target without a fresh justification.

## Autoresearch adaptation

Separate four components explicitly:

1. **Workload:** Vesper ranker training on local frozen financial data.
2. **Research agent:** Codex/Claude/etc. edits permitted model/training code.
3. **Bounded run:** each candidate trains from scratch under the same budget.
4. **Evaluator:** immutable held-out daily rank IC first; FM/Newey-West, costs, and portfolio evidence remain final governance gates.

A single training command does not create the autonomous loop. Conversely, the training workload itself does not call OpenAI; the coding agent does. Never answer an autonomous-loop question with only “no OpenAI is required.”

## Boundaries

- Research output is challenger evidence, not an order signal by default.
- Keep production checkpoints, registry weights, scheduler authority, broker access, and target/risk policy closed.
- Use split-adjusted data and point-in-time admission where available; state survivor-cohort limitations honestly.
- Do not optimize final-test FM statistics inside the agent loop. Use a frozen validation objective, then run final FM/Newey-West once on untouched evidence.
