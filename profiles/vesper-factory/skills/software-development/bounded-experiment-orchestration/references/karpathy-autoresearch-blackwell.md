# Karpathy autoresearch on RTX 5070 Ti / WSL2

Session-specific reference for adapting `karpathy/autoresearch` to a Blackwell-class NVIDIA GPU.

## Environment boundary

The repo was run in a separate Ubuntu WSL2 terminal, not the Windows host terminal. The agent could not directly inspect or edit the WSL checkout. Commands had to be run by the user at the WSL prompt. When PowerShell showed a continuation prompt (`>>`), `Ctrl+C` recovered it; entering only `wsl` returned to Ubuntu. The user then ran `cd ~/autoresearch`.

Never paste prompt text such as `brennan@Holmes:~/autoresearch$` or `PS C:\Users\...>` into the shell. Never paste Python source as if it were a shell command.

## Kernel compatibility fix

The initial run reached model setup but failed with:

```text
CUDA error ... no kernel image is available for execution on the device
```

The repo selected a precompiled Flash Attention 3 kernel that did not support the GPU architecture. The working fallback removed the `kernels`/`get_kernel`/`fa3` import block and replaced:

```python
y = fa3.flash_attn_func(q, k, v, causal=True, window_size=window_size)
```

with native SDPA using the required layout conversion:

```python
sdpa_q = q.transpose(1, 2)
sdpa_k = k.transpose(1, 2)
sdpa_v = v.transpose(1, 2)
y = F.scaled_dot_product_attention(sdpa_q, sdpa_k, sdpa_v, is_causal=True)
y = y.transpose(1, 2).contiguous()
```

Run `uv run python -m py_compile train.py` before starting a long run. This fallback is appropriate for the tested `WINDOW_PATTERN = "L"` configuration; if short-window patterns are reintroduced, preserve/test their masking semantics separately.

## Hardware adaptation and observed trials

Upstream defaults target an H100. The tested working setup used `MAX_SEQ_LEN = 1024`, `DEPTH = 4`, and native SDPA. Keep this deviation documented because it is not directly comparable to upstream runs.

Recorded five-minute trials:

| Configuration | val_bpb | peak VRAM | tokens | Verdict |
|---|---:|---:|---:|---|
| depth 4, device batch 16, total batch `2**16` | 1.153107 | 1039.8 MB | 258.7M | smoke baseline |
| depth 4, device batch 64, total batch `2**16` | 1.139864 | 3679.3 MB | 407.4M | improved |
| depth 4, device batch 128, total batch `2**17` | 1.134276 | 7241.8 MB | 437.3M | best confirmed |
| depth 6, device batch 128, total batch `2**17` | 1.181836 | 13657.6 MB | 57.8M | discard: too slow |
| depth 4, device batch 192, total batch `3*2**17` | 1.143315 | 10839.1 MB | 432.9M | discard |

The best restored configuration was:

```text
WINDOW_PATTERN = "L"
TOTAL_BATCH_SIZE = 2**17
DEPTH = 4
DEVICE_BATCH_SIZE = 128
```

Under a fixed wall-clock budget, do not assume that more parameters or more VRAM usage improves the metric. Record validation BPB, VRAM, tokens, parameter count, and the exact configuration; restore the last confirmed-good state after a worse trial. Ensure:

```text
TOTAL_BATCH_SIZE % (DEVICE_BATCH_SIZE * MAX_SEQ_LEN) == 0
```

The script’s MFU is calculated against an H100 reference and should not be treated as the 5070 Ti’s actual utilization.
