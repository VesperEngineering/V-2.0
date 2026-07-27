# Terminal HUD and representation-research checklist

## HUD must answer

- Is the process alive?
- Which script and phase are active?
- Is the GPU actually working?
- What happens after the final printed epoch?
- What was learned versus rejected?

## Minimal stable layout

```text
STATUS RUNNING | SCRIPT experiment.py | PHASE encoding
GPU 2.1 / 16.0 GiB | 82% | ELAPSED 4m12s
NN [input] -> [encoder] -> [latent] -> [predictor]
EVIDENCE baseline delta [bar] value verdict
ACTIVITY last five factual lines
```

Use an alternate-screen/live renderer rather than clearing the console in a loop. Keep the model chart at the top so small terminal windows cannot crop it away.

## Interpretation guardrails

- A dimension index is not a concept label across random seeds.
- Sign flips and rotations are expected in unconstrained encoders.
- Test a full embedding with a held-out probe or alignment before claiming it encodes an observable.
- State whether an association is contemporaneous, descriptive, or predictive.
- A replication that invalidates an attractive explanation must replace the old HUD/README claim immediately.

## Post-epoch checklist

If output stops after the final epoch, check in order:

1. process has not exited;
2. GPU utilization/memory or CPU work indicates activity;
3. expected JSON/checkpoint artifact does not yet exist or is changing;
4. code has known post-training stages: embedding extraction, probe fitting, statistical inference, serialization.

Then add explicit phase messages before the next run; do not leave users guessing whether a process is hung.
