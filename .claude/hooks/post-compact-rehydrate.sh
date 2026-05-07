#!/usr/bin/env bash
# .claude/hooks/post-compact-rehydrate.sh
#
# Fires from .claude/settings.json on every SessionStart event (matchers
# startup|resume|compact). Stdout is automatically injected into Claude's
# context window per the SessionStart hook contract:
#   https://code.claude.com/docs/en/hooks
#
# Purpose: counter-measure for Anthropic's context-compaction algorithm,
# which reliably preserves task progress but reliably discards load-bearing
# operational invariants (the "this is a fork, --repo is mandatory" /
# "this is production, never DROP TABLE" class of fact). Re-injects the
# canonical project knowledge files verbatim so a freshly-resumed Claude
# starts every turn with the same baseline as a Claude that has been in
# the conversation from the beginning.
#
# What gets re-injected, in priority order:
#   1. CLAUDE.md (always; the load-bearing instruction file)
#   2. Every memory file under
#      ~/.claude/projects/-home-dell-github-ShadNygren-servicenow-mcp/memory/
#   3. .github/SECURITY.md (compact security policy + audit status)
#   4. DEPLOYMENT.md (deployment guide; matters for prod-state mistakes)
#   5. README.md (full user-facing manual)
#   6. ANALYSIS_OF_*.md (the four planning docs, the project's strategic
#      context — fork survey, PR/issue review, original architecture)
#
# Each file is dumped verbatim with a delimiter so Claude can navigate.
#
# Approximate cost: ~60k tokens (~6% of a 1M context). The user's stated
# target is "10–20% of context with valuable content"; we sit comfortably
# below that ceiling. If files grow past the budget, this script should
# switch the largest ANALYSIS files to head + heading-map mode.
#
# Hook contract notes (verified 2026-05-06 against the docs):
#   - Working dir: $CLAUDE_PROJECT_DIR (project root)
#   - Stdout is injected into Claude's context for SessionStart only
#     (not for PostCompact, which is debug-log only).
#   - Exit code 0 = success; non-zero output goes to debug log only.
#   - The script must be fast (<1s ideally) — it runs on every session
#     start, including normal resume.

set -euo pipefail

# CLAUDE_PROJECT_DIR is set by Claude Code to the project root. Fall back
# to the script's parent-of-parent for direct testing (e.g.
# `bash .claude/hooks/post-compact-rehydrate.sh` from the project root).
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

# Memory dir lives outside the repo, in Claude Code's per-project state.
# Slug is the project root path with / -> -.
PROJECT_SLUG="$(echo "$PROJECT_DIR" | sed 's|/|-|g')"
MEMORY_DIR="$HOME/.claude/projects/${PROJECT_SLUG}/memory"

emit_file() {
    local label="$1"
    local path="$2"
    if [[ ! -f "$path" ]]; then
        echo "<!-- ${label}: ${path} not found, skipping -->"
        return
    fi
    echo
    echo "================================================================================"
    echo "=== ${label}: ${path}"
    echo "================================================================================"
    cat "$path"
    echo
}

cat <<'HEADER'
================================================================================
=== BEGIN POST-COMPACTION REHYDRATION
=== Fired by SessionStart hook (.claude/hooks/post-compact-rehydrate.sh).
=== If you can read this, the hook ran. The files below are the canonical
=== project knowledge — read every word before your next tool call.
=== Pay special attention to any "STOP" sections in CLAUDE.md.
================================================================================
HEADER

# 1. CLAUDE.md — the most important file
emit_file "CLAUDE.md (project instructions, MUST READ)" "$PROJECT_DIR/CLAUDE.md"

# 2. Memory files — lessons learned, feedback, project state
if [[ -d "$MEMORY_DIR" ]]; then
    # MEMORY.md first (the index), then everything else
    if [[ -f "$MEMORY_DIR/MEMORY.md" ]]; then
        emit_file "MEMORY.md (memory index)" "$MEMORY_DIR/MEMORY.md"
    fi
    for f in "$MEMORY_DIR"/*.md; do
        [[ -f "$f" ]] || continue
        [[ "$(basename "$f")" == "MEMORY.md" ]] && continue
        emit_file "memory: $(basename "$f")" "$f"
    done
else
    echo "<!-- memory dir $MEMORY_DIR not found, skipping memory files -->"
fi

# 3. SECURITY policy
emit_file "SECURITY.md (security policy)" "$PROJECT_DIR/.github/SECURITY.md"

# 4. Deployment guide
emit_file "DEPLOYMENT.md (deployment + ops)" "$PROJECT_DIR/DEPLOYMENT.md"

# 5. README — user-facing manual
emit_file "README.md (user-facing docs)" "$PROJECT_DIR/README.md"

# 6. The four planning docs — strategic context
for f in "$PROJECT_DIR"/ANALYSIS_OF_*.md; do
    [[ -f "$f" ]] || continue
    emit_file "$(basename "$f") (planning doc)" "$f"
done

cat <<'FOOTER'

================================================================================
=== END POST-COMPACTION REHYDRATION
=== Re-confirm all safety invariants from the STOP section in CLAUDE.md
=== before any external-state tool calls (gh, git push, kubectl, DROP, rm).
================================================================================
FOOTER
