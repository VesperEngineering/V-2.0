#!/usr/bin/env bash
# Diagnose Hermes TUI gateway crashes on Windows.
# Run from bash (git-bash/MSYS) on the Windows host.
#
# Usage: bash diagnose-tui-crashes.sh

set -u

CRASH_LOG="$HOME/AppData/Local/hermes/logs/tui_gateway_crash.log"
PROCESSES_JSON="$HOME/AppData/Local/hermes/processes.json"
HERMES_BIN="$HOME/AppData/Local/hermes/hermes-agent/venv/Scripts/hermes.exe"

echo "=== Hermes TUI Gateway Crash Diagnosis ==="
echo "Date: $(date)"
echo

# --- Crash log exists? ---
if [ ! -f "$CRASH_LOG" ]; then
  echo "✗ No crash log found at $CRASH_LOG"
  echo "  → No TUI gateway crashes recorded."
  exit 0
fi

# --- Crash count and codes ---
CRASH_COUNT=$(grep -c "child exit" "$CRASH_LOG" 2>/dev/null || echo 0)
echo "Total child exits: $CRASH_COUNT"
echo

# --- Breakdown by exit code ---
echo "--- Child exits by exit code ---"
grep "child exit" "$CRASH_LOG" 2>/dev/null | \
  sed -n 's/.*exitCode=\([0-9]*\).*/\1/p' | \
  sort | uniq -c | sort -rn | while read -r count code; do
    hex=$(python -c "print(hex($code))" 2>/dev/null || echo "?")
    echo "  $count × $code ($hex)"
  done
echo

# --- 0xC000013A (STATUS_CONTROL_C_EXIT) specific ---
CTRL_C_COUNT=$(grep -c "exitCode=3221225786" "$CRASH_LOG" 2>/dev/null || echo 0)
if [ "$CTRL_C_COUNT" -gt 0 ]; then
  echo "⚠️  $CTRL_C_COUNT crashes with 0xC000013A (STATUS_CONTROL_C_EXIT)"
  echo "   → Console control event killing the gateway child."
  echo "   → See references/exit-code-0xC000013A-control-c-exit.md for the fix."
  echo
  echo "   Last 5 such crashes:"
  grep "exitCode=3221225786" "$CRASH_LOG" | tail -5 | sed 's/^/     /'
  echo
else
  echo "✓ No 0xC000013A (STATUS_CONTROL_C_EXIT) crashes."
fi
echo

# --- EPIPE precursor crashes ---
EPIPE_COUNT=$(grep -c "write EPIPE" "$CRASH_LOG" 2>/dev/null || echo 0)
if [ "$EPIPE_COUNT" -gt 0 ]; then
  echo "ℹ️  $EPIPE_COUNT 'write EPIPE' precursors (symptom of 0xC000013A, not separate cause)"
fi
echo

# --- Is the fix applied? ---
echo "--- Fix status ---"
ENTRY_JS="$HOME/AppData/Local/hermes/hermes-agent/ui-tui/dist/entry.js"
SRC_TS="$HOME/AppData/Local/hermes/hermes-agent/ui-tui/src/gatewayClient.ts"
if [ -f "$ENTRY_JS" ]; then
  if grep -q "detached: true" "$ENTRY_JS" 2>/dev/null; then
    echo "✓ Fix applied in dist/entry.js (takes effect on next TUI launch)"
  else
    echo "✗ Fix NOT applied in dist/entry.js"
  fi
else
  echo "? dist/entry.js not found"
fi
if [ -f "$SRC_TS" ]; then
  if grep -q "detached: true" "$SRC_TS" 2>/dev/null; then
    echo "✓ Fix applied in src/gatewayClient.ts (source)"
  else
    echo "✗ Fix NOT applied in src/gatewayClient.ts (source)"
  fi
else
  echo "? src/gatewayClient.ts not found"
fi
echo

# --- Current background processes ---
echo "--- Current processes ---"
if [ -f "$PROCESSES_JSON" ]; then
  PROC_COUNT=$(grep -c '"' "$PROCESSES_JSON" 2>/dev/null || echo 0)
  if [ "$PROC_COUNT" -le 2 ]; then
    echo "  processes.json: empty (no background terminal sessions active)"
  else
    echo "  processes.json: $PROC_COUNT entries"
  fi
fi

# --- Scheduled-task gateway status ---
echo
echo "--- Scheduled-task gateway status ---"
if [ -f "$HERMES_BIN" ]; then
  "$HERMES_BIN" gateway status 2>&1 | head -5 | sed 's/^/  /'
fi
