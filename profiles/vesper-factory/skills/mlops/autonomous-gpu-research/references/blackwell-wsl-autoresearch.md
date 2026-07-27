# WSL2 / Blackwell bring-up reference

## Scenario

A Windows host with an NVIDIA RTX 5070 Ti was used through Ubuntu WSL2. CUDA became available in WSL2, but the original autoresearch training script failed at startup with:

```text
CUDA error ... flash_fwd_launch_template.h ...
no kernel image is available for execution on the device
```

The model initialized successfully, so this was a custom Flash Attention 3 binary/compute-capability mismatch, not a missing PyTorch CUDA install.

## Recovery sequence

1. Work in the WSL2 terminal, not the Windows/MSYS terminal:
   ```bash
   wsl
   cd ~/autoresearch
   ```
2. Do not paste the prompt prefix or Python source directly into Bash/PowerShell. If PowerShell shows `>>`, press `Ctrl+C`; at `PS ...>` type only `wsl`.
3. Remove the repository's Flash Attention 3 import block:
   ```bash
   sed -i '/^from kernels import get_kernel$/,/^fa3 = get_kernel(repo).flash_attn_interface$/d' train.py
   ```
4. Replace the FA3 call with PyTorch SDPA. The replacement must transpose attention tensors from `[B,T,H,D]` to `[B,H,T,D]`, call causal SDPA, then transpose back:
   ```bash
   perl -0pi -e 's|        y = fa3\.flash_attn_func\(q, k, v, causal=True, window_size=window_size\)|        sdpa_q = q.transpose(1, 2)\n        sdpa_k = k.transpose(1, 2)\n        sdpa_v = v.transpose(1, 2)\n        y = F.scaled_dot_product_attention(sdpa_q, sdpa_k, sdpa_v, is_causal=True)\n        y = y.transpose(1, 2).contiguous()|' train.py
   ```
5. Verify before spending five minutes on a run:
   ```bash
   grep -n "fa3\|kernels\|scaled_dot\|SDPA" train.py
   uv run python -m py_compile train.py
   ```

## Important limitation

The SDPA fallback above is correct for the local full-attention baseline (`WINDOW_PATTERN = "L"`). It ignores the repository's `window_size` argument, so it must not be presented as equivalent if later experiments restore sliding-window (`S`) layers. For that case, implement and verify an equivalent attention mask or find a kernel that supports the GPU.

## Experiment record

Record the fallback and hardware configuration with the baseline: GPU model, VRAM, compute capability, PyTorch version, sequence length, depth, device batch size, total batch size, attention implementation, metric, peak VRAM, and run duration.
