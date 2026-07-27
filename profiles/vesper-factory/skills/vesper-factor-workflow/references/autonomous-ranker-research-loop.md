# Autonomous Cross-Sectional Ranker Research

Use this reference when the user asks what Vesper should actually train with an autoresearch-style loop.

## Answer the investment question first

Do not lead with Codex installation, generic autoresearch architecture, or overnight-loop mechanics. Name the Vesper target in the first sentence:

> Train Vesper's cross-sectional transformer ranker to order equities by 21-session forward total return.

Only explain tooling after the target is understood.

## Recommended target

- Existing substrate: `deploy/src/na/transformer_training.py` and the `deploy/nova.py train` command.
- Input window: 60 sessions.
- Label horizon: 21 sessions, consistent with Vesper's 10-21d evidence horizon rather than the legacy one-day control plan.
- Objective: `pairwise_rank`, already implemented by Vesper.
- Inputs: split-adjusted Massive OHLCV through `fetch_adjusted_ohlcv_rows`, plus expanded cross-sectional relative features.
- Research metric: held-out mean daily Spearman rank IC, higher is better.
- Final economic gate: purged walk-forward evidence and Fama-MacBeth/Newey-West; rank IC alone never promotes a model.
- Output: a challenger score only. No registry mutation, production checkpoint replacement, broker access, scheduler change, or order authority.

## Autoresearch adaptation

The reusable mechanism is code evolution, not continued checkpoint training:

1. Freeze dataset construction, chronological splits, labels, evaluator, seed, and locked test set.
2. Permit the agent to modify one candidate model/training file only.
3. Give each experiment a fixed GPU budget.
4. Train from scratch, evaluate validation rank IC, retain improved code, and revert regressions/crashes.
5. Keep the locked test unseen during the loop; evaluate it only after candidate selection.
6. Log commit, source/data/evaluator hashes, runtime, peak VRAM, validation metric, and disposition.
7. Compare real labels against shuffled labels and a simple tree-ranker control.

Repeated adaptive validation can overfit the validation set. The locked test and final Newey-West gate are mandatory, not optional polish.

## Environment separation

For WSL GPU work, use an isolated WSL-native clone or worktree and copied frozen research inputs. Never run an autonomous editor against the dirty production `D:/vesper` workspace. The source data copy should include the Massive S&P SQLite file, split-adjustment map, PIT membership, current ticker list, and sector map. Any missing removed-constituent OHLCV must be disclosed as survivor-cohort limitation.

## Codex versus training

Be explicit early:

- A direct Python training command uses local PyTorch/CUDA and does not require OpenAI.
- The autonomous modify/train/evaluate/revert loop requires a coding agent such as Codex and therefore Codex authentication.
- `program.md` is read by the coding agent; it is not executed by `train.py`.

## User-facing command sequencing

When commands require leaving or changing a directory, put that navigation command first, before installation, cloning, authentication, or training steps. Use exact commands without copying shell prompt prefixes. Keep the explanation brief and provide one recommended path rather than a menu.

Before giving a Vesper command, inspect the tracked CLI parser and current board. Do not invent flags or rely on stale plans when the executable contract is discoverable in code.
