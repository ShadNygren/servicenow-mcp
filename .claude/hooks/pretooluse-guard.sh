#!/usr/bin/env bash
# .claude/hooks/pretooluse-guard.sh
#
# Fires from .claude/settings.json on PreToolUse (matcher: Bash). Reads the tool-call
# JSON on stdin and BLOCKS (exit 2) a small, unambiguous set of catastrophic or
# irreversible shell patterns before they run; everything else is allowed (exit 0).
#
# Deliberately conservative: this guards against irreversible mistakes (and the
# fork-history-leak class of error this repo has hit before), NOT normal development.
# Hook contract: https://code.claude.com/docs/en/hooks
#   exit 0 -> allow ;  exit 2 -> block the tool call and return stderr to the model.
set -uo pipefail

payload="$(cat)"

# Pull the command string out of the PreToolUse payload. Prefer jq; fall back to
# python3 (always present in this repo); fall back to scanning the raw payload.
if command -v jq >/dev/null 2>&1; then
  cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // ""' 2>/dev/null || true)"
elif command -v python3 >/dev/null 2>&1; then
  cmd="$(printf '%s' "$payload" | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("command", ""))
except Exception:
    print("")' 2>/dev/null || true)"
else
  cmd="$payload"
fi

[ -z "${cmd:-}" ] && exit 0

# Catastrophic / irreversible patterns (case-insensitive). Tune as the repo evolves.
deny_re='rm[[:space:]]+-[a-z]*r[a-z]*f?[[:space:]]+(/|~|\$HOME|\*)'        # recursive force-delete of a root-ish path
deny_re="$deny_re"'|:\(\)[[:space:]]*\{[[:space:]]*:[[:space:]]*\|'         # fork bomb :(){ :|:& };:
deny_re="$deny_re"'|mkfs|>[[:space:]]*/dev/sd|dd[[:space:]].*of=/dev/'      # disk wipe
deny_re="$deny_re"'|chmod[[:space:]]+-R[[:space:]]+777[[:space:]]+/'        # chmod -R 777 /
deny_re="$deny_re"'|(curl|wget)[[:space:]][^|]*\|[[:space:]]*(sudo[[:space:]]+)?(ba)?sh'  # curl|sh
deny_re="$deny_re"'|git[[:space:]]+push[[:space:]][^&|;]*--force[^&|;]*(upstream|echelon)' # force-push to upstream

if printf '%s' "$cmd" | grep -Eiq "$deny_re"; then
  echo "PreToolUse guard: refused a destructive/irreversible command pattern." >&2
  echo "If this is genuinely intended, run it yourself outside the agent." >&2
  exit 2
fi
exit 0
