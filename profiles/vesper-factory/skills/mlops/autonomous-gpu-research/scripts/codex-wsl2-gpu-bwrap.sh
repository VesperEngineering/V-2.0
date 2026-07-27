#!/usr/bin/env bash
set -euo pipefail

# Required: absolute WSL-native workspace path.
ROOT="${CODEX_GPU_WORKSPACE:?Set CODEX_GPU_WORKSPACE to the absolute project path}"
MODEL="${CODEX_MODEL:-gpt-5.6-sol}"
MODE="${1:-test}"
RUNTIME="${CODEX_GPU_RUNTIME:-$HOME/.cache/codex-gpu-bwrap-runtime}"

[[ "$ROOT" = /* && -d "$ROOT/.git" ]] || {
  printf 'ERROR: CODEX_GPU_WORKSPACE must be an absolute Git repository path\n' >&2
  exit 1
}
[[ -e /dev/dxg ]] || { printf 'ERROR: /dev/dxg is missing\n' >&2; exit 1; }
command -v bwrap >/dev/null || { printf 'ERROR: bubblewrap is missing\n' >&2; exit 1; }
command -v codex >/dev/null || { printf 'ERROR: codex is missing\n' >&2; exit 1; }

mkdir -p "$RUNTIME"
chmod 700 "$RUNTIME"

ARGS=(
  --die-with-parent
  --ro-bind / /
  --dev-bind /dev /dev
  --proc /proc
  --tmpfs /tmp
  --bind "$ROOT" "$ROOT"
  --bind "$RUNTIME" "$RUNTIME"
  --tmpfs /mnt
  --chdir "$ROOT"
  --setenv CODEX_HOME "$RUNTIME"
  --setenv UV_CACHE_DIR /tmp/uv-cache
  --setenv XDG_CACHE_HOME /tmp/cache
  --setenv PIP_CACHE_DIR /tmp/cache/pip
  --setenv NPM_CONFIG_CACHE /tmp/cache/npm
)

MASKS=("$HOME/.codex" "$HOME/.ssh" "$HOME/.aws" "$HOME/.azure" "$HOME/.config/gcloud")
if [[ -n "${CODEX_MASK_PATHS:-}" ]]; then
  IFS=: read -r -a EXTRA_MASKS <<<"$CODEX_MASK_PATHS"
  MASKS+=("${EXTRA_MASKS[@]}")
fi

ACTIVE_MASKS=()
for path in "${MASKS[@]}"; do
  if [[ -d "$path" && "$path" != "$ROOT" && "$ROOT" != "$path/"* ]]; then
    ARGS+=(--tmpfs "$path")
    ACTIVE_MASKS+=("$path")
  fi
done
MASK_LIST="$(IFS=:; printf '%s' "${ACTIVE_MASKS[*]}")"
ARGS+=(--setenv CODEX_OUTER_MASKS "$MASK_LIST")

run_test() {
  bwrap "${ARGS[@]}" sh -lc '
    set -eu
    probe=.outer-bwrap-write-probe
    : > "$probe" && rm -f "$probe"
    echo workspace=writable

    if ( : > "$HOME/.outer-bwrap-escape-probe" ) 2>/dev/null; then
      rm -f "$HOME/.outer-bwrap-escape-probe"
      echo "ERROR: outside-workspace write succeeded" >&2
      exit 1
    fi
    echo outside-workspace=read-only

    test ! -e /mnt/d || { echo "ERROR: Windows mounts visible" >&2; exit 1; }
    echo windows-mounts=masked

    old_ifs=$IFS; IFS=:
    for path in $CODEX_OUTER_MASKS; do
      if find "$path" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null | grep -q .; then
        echo "ERROR: mask is not empty: $path" >&2
        exit 1
      fi
    done
    IFS=$old_ifs
    echo configured-paths=masked

    test ! -e "$HOME/.codex/auth.json" || {
      echo "ERROR: real Codex auth is visible" >&2
      exit 1
    }
    echo real-codex-home=masked

    printf "dxg="
    test -e /dev/dxg && echo present || { echo missing; exit 1; }
    nvidia-smi --query-gpu=name --format=csv,noheader
  '
}

run_launch() {
  [[ -f "$HOME/.codex/auth.json" ]] || {
    printf 'ERROR: standalone Codex auth is missing\n' >&2
    exit 1
  }
  install -m 600 "$HOME/.codex/auth.json" "$RUNTIME/auth.json"
  exec bwrap "${ARGS[@]}" \
    codex --cd "$ROOT" --model "$MODEL" --dangerously-bypass-approvals-and-sandbox
}

run_resume() {
  # Non-interactive autonomous resume of the most recent Codex session.
  # Used after a WSL2 crash to restart without losing session context.
  # See references/wsl2-crash-recovery.md for the full procedure.
  [[ -f "$HOME/.codex/auth.json" ]] || {
    printf 'ERROR: standalone Codex auth is missing\n' >&2
    exit 1
  }
  install -m 600 "$HOME/.codex/auth.json" "$RUNTIME/auth.json"
  # CRITICAL: --cd, --model, --dangerously-bypass-approvals-and-sandbox are
  # exec-level flags and must come BEFORE the `resume` subcommand, not after.
  exec bwrap "${ARGS[@]}" \
    codex exec \
      --cd "$ROOT" \
      --model "$MODEL" \
      --dangerously-bypass-approvals-and-sandbox \
      resume --last \
      "${CODEX_RESUME_PROMPT:-Resume the autonomous experiment loop. Continue proposing one hypothesis at a time, edit only the training file, commit, run, extract the metric, log to results, keep or discard, and continue without pausing.}"
}

case "$MODE" in
  test) run_test ;;
  launch) run_launch ;;
  resume) run_resume ;;
  *) printf 'Usage: %s [test|launch|resume]\n' "$0" >&2; exit 2 ;;
esac
