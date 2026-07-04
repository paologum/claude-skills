#!/usr/bin/env bash
# PreToolUse safety hook for the claude-skills plugin.
# Hard-blocks irreversible/destructive Bash commands so the deny list travels
# with the plugin (plugin settings.json cannot carry `permissions`). The
# authoritative rules also live in the user's ~/.claude/settings.json via the
# /harden-permissions skill; this hook is defense-in-depth that auto-applies
# wherever the plugin is enabled.
#
# Contract: read the PreToolUse JSON on stdin, and either
#   - print a deny decision as JSON and exit 0, or
#   - exit 0 with no output (defer to the normal permission flow).
# Fails open (never blocks legitimate work) if it cannot parse the input.

set -euo pipefail

input="$(cat)"

# Extract the command string. Prefer jq, fall back to python3, else fail open.
if command -v jq >/dev/null 2>&1; then
  cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"
elif command -v python3 >/dev/null 2>&1; then
  cmd="$(printf '%s' "$input" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"
else
  exit 0
fi

[ -z "$cmd" ] && exit 0

deny() {
  # $1 is a plain-ASCII reason with no characters that need JSON escaping.
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$1"
  exit 0
}

# Patterns mirror the deny list applied by /harden-permissions. Heuristic by
# design — the settings-level deny rules are the exact backstop.
grep -Eiq '(^|[^[:alnum:]])rm[[:space:]]+-[a-z]*(rf|fr|r[[:space:]]*-[a-z]*f|f[[:space:]]*-[a-z]*r)' <<<"$cmd" \
  && deny "Blocked: recursive/forced rm. Delete specific paths explicitly, or run it yourself if intended."
grep -Eiq '(^|[^[:alnum:]])sudo[[:space:]]' <<<"$cmd" \
  && deny "Blocked: sudo. Run privileged commands yourself in your own terminal."
grep -Eiq 'git[[:space:]]+push([[:space:]].*)?(--force|--force-with-lease|[[:space:]]-f([[:space:]]|$))' <<<"$cmd" \
  && deny "Blocked: force-push. Force-pushing rewrites remote history; do it manually if you must."
grep -Eiq 'git[[:space:]]+reset([[:space:]].*)?--hard' <<<"$cmd" \
  && deny "Blocked: git reset --hard discards uncommitted work. Stash or commit first."
grep -Eiq 'git[[:space:]]+clean([[:space:]].*)?-[a-z]*f' <<<"$cmd" \
  && deny "Blocked: git clean -f permanently deletes untracked files. Review with 'git clean -n' first."
grep -Eiq 'chmod[[:space:]]+-[a-z]*R[a-z]*[[:space:]]+777' <<<"$cmd" \
  && deny "Blocked: chmod -R 777 makes files world-writable. Use a tighter mode."
grep -Eiq '(^|[^[:alnum:]])dd[[:space:]]+' <<<"$cmd" \
  && deny "Blocked: dd can overwrite disks/devices. Run it yourself if intended."

exit 0
