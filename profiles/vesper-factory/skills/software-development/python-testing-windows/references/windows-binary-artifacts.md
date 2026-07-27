# Windows Binary-Safe Immutable Artifact Writes

Use when a Windows test reports that an exact replay changed an immutable JSON, receipt, ledger, or hash-bound artifact even though the Python payload is identical.

## Symptom

A writer uses `os.open(..., os.O_WRONLY)` followed by `os.write(fd, b"...\n")`. The first call succeeds, but an immediate byte comparison against the same encoded payload fails. Reading the file shows `\r\n` where the encoded bytes contained `\n`.

## Root cause

On Windows, an `os.open` descriptor can inherit text-mode newline translation unless `O_BINARY` is present. `os.write` is low-level, but the descriptor mode still matters. This is especially dangerous for content-addressed receipts because the persisted bytes no longer equal the bytes that were hashed or replay-checked.

## Portable fix

```python
flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
fd = os.open(path, flags, 0o600)
try:
    os.write(fd, encoded_bytes)
    os.fsync(fd)
finally:
    os.close(fd)
```

`getattr` keeps the code portable on platforms that do not define `O_BINARY`.

## Regression test

1. Encode deterministic JSON with at least one newline.
2. Write it through the exact production helper.
3. Assert `path.read_bytes() == encoded_bytes`.
4. Replay the same payload and require a no-op.
5. Change one semantic field and require immutable-mutation rejection.

Do not normalize line endings during validation; exact-byte identity is the contract. Normal text files written through `Path.write_text` may intentionally follow text conventions, but hash-bound artifacts need an explicit byte contract.
