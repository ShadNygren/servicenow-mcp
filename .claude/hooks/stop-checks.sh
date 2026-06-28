#!/usr/bin/env bash
# .claude/hooks/stop-checks.sh
#
# Fires from .claude/settings.json on Stop (session end). Read-only, informational
# session-end verification: WARNS (does not block) if obvious secrets or debug
# artifacts are staged for commit. Always exits 0 so it can never wedge a close.
# Hook contract: https://code.claude.com/docs/en/hooks
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
command -v git >/dev/null 2>&1 || exit 0

warn() { echo "stop-check: $*" >&2; }

# 1) staged changes that look like secrets/credentials
staged="$(git diff --cached -U0 2>/dev/null || true)"
if [ -n "$staged" ] && printf '%s' "$staged" \
    | grep -Eiq '(aws_secret_access_key|api[_-]?key|secret[_-]?key|client[_-]?secret|password[[:space:]]*=|bearer[[:space:]]+[a-z0-9._-]{16,}|-----BEGIN[[:space:]]+(RSA|OPENSSH|EC|DSA|PRIVATE))'; then
  warn "staged diff may contain a secret/credential — review before committing."
fi

# 2) leftover debug artifacts in staged Python
if git diff --cached --name-only 2>/dev/null | grep -q '\.py$'; then
  if git diff --cached 2>/dev/null | grep -Eq '^\+[[:space:]]*(print\(|breakpoint\(\)|import[[:space:]]+pdb\b)'; then
    warn "staged Python adds print()/pdb/breakpoint — remove debug artifacts before committing."
  fi
fi

exit 0
