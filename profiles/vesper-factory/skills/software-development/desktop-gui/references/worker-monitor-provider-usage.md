# Provider account usage in read-only desktop monitors

## Use when

A native operator or worker monitor needs compact OpenAI/OpenRouter usage for reference without turning provider accounting into the dominant dashboard surface.

## Source and scope contract

Keep these scopes explicit; they are not interchangeable:

1. **OpenAI Codex account quota** — session/weekly rate-limit windows and reset times returned for the authenticated Codex account.
2. **OpenRouter account/key state** — dollar credit balance, key usage, and optional key quota.
3. **Hermes local history** — session/model token totals from `hermes insights`; useful for historical activity, but not proof of provider quota or account balance.
4. **Application-local receipts** — only requests attributed by the application. Zero local receipts does not mean zero provider activity.

For Hermes-backed monitors, prefer the installed account-usage API rather than scraping rendered CLI text:

```python
from agent.account_usage import fetch_account_usage, render_account_usage_lines

codex = fetch_account_usage("openai-codex")
openrouter = fetch_account_usage("openrouter")
```

Resolve the installed Hermes source/venv dynamically. On Windows, `Path.home() / "AppData/Local/hermes/hermes-agent"` is a fallback; never hard-code a username. Test the import with the same interpreter used by the Desktop shortcut. If that interpreter cannot import Hermes dependencies, run a small helper with the Hermes venv and return a credential-free JSON snapshot.

## Display semantics

- `used_percent` is already **used**, not remaining. Display `remaining = max(0, 100 - used_percent)`.
- Render only windows actually returned. If OpenAI returns a session window but no weekly window, show session only; do not synthesize weekly usage.
- A compact always-visible summary can use:

  ```text
  OAI 74% S · OR $44.22
  ```

  where `S` is session and `W` is weekly. Keep an expanded block in a command palette or secondary panel with provider name, plan, reset, balance, and daily/weekly/monthly spend.
- OpenRouter dollars must not be converted to a percentage unless the API provides a trustworthy positive limit/remaining denominator.
- Missing, malformed, or failed provider data renders as `unavailable`, never `0`.
- Never display or log API keys, OAuth tokens, account IDs, emails, or credential-pool metadata.
- Label the block as a read-only snapshot and name the refresh cadence.

## Refresh architecture

Provider requests are slower and less reliable than local board reads. Give them a separate cadence:

1. Poll local worker/Kanban state on its normal short interval (for example two seconds).
2. Fetch provider usage in a daemon/background thread on startup and then approximately every five minutes.
3. Return `(summary, detail_lines)` through the existing Tk queue and update `StringVar` values only on the Tk main thread.
4. Preserve the last successful snapshot while a refresh runs. Do not blank the app bar or palette with `Loading…` after real data has appeared.
5. Add a manual `Refresh provider usage` command, guarded against concurrent fetches.
6. Track the provider `after()` callback ID and cancel it in the idempotent `WM_DELETE_WINDOW` close path.
7. Fail open: one provider may remain available while the other reports unavailable.

## Visual placement

Provider usage is reference metadata, not worker evidence. Preserve the Command Split hierarchy:

- Place a one-line summary in unused app-bar space near read-only/sync state.
- Make the summary clickable to open the existing command palette.
- Put verbose reset/spend lines in the palette, wrapping within a fixed width.
- Do not insert a large billing card between the worker rail, selected-task header, and terminal output.

## Verification

1. Run a direct usage probe and print only the formatted, credential-free snapshot.
2. Compile and run the monitor's live smoke path with the launcher interpreter.
3. Launch the actual Desktop shortcut and capture the titled HWND with Win32 `PrintWindow`; confirm the compact line does not clip or shift existing app-bar controls.
4. Capture the palette `Toplevel` by its Tk `winfo_id()` and verify long reset/monthly lines wrap without overlap.
5. Send a real `WM_CLOSE` and confirm all monitor PIDs created by the probe are gone.
6. Test unavailable formatting by injecting a failed/empty snapshot; it must say unavailable rather than zero.

## Pitfalls

- `hermes insights` aggregates token history by model and platform; it does not replace provider-account quota/balance APIs.
- Parsing already-rendered usage text couples the monitor to punctuation and localization. Use snapshot fields for the compact summary; rendered lines are acceptable only for the expanded reference block.
- Running provider queries on the same two-second loop as Kanban polling creates unnecessary network load and UI instability.
- Treating OpenRouter balance, OpenAI quota, and local receipts as one unlabeled `usage` number produces false accounting.
- A successful `.lnk` icon or source-level compile is not visual proof; inspect the actual shortcut-launched window and palette.
