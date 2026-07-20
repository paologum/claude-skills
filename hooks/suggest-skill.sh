#!/usr/bin/env bash
# PreToolUse (Bash) + UserPromptSubmit hook for the claude-skills plugin.
# Scans the tool command or the user prompt against ${CLAUDE_PLUGIN_ROOT}/hooks/
# skill-triggers.json and, on match, injects a system-reminder nudging the model
# to invoke a plugin skill instead of hand-rolling the workflow inline.
#
# Data-driven: all patterns live in skill-triggers.json — this script is
# intentionally dumb about which command maps to which skill so tuning the map
# never requires a shell diff.
#
# Contract:
#   - PreToolUse:      read .tool_input.command from stdin
#   - UserPromptSubmit: read .user_prompt from stdin
#   - On match: emit hookSpecificOutput.additionalContext JSON, exit 0.
#   - On no match / parse failure / missing jq: exit 0 silently. NEVER blocks.

set -u  # NB: no -e / -o pipefail — this hook must fail open, always.

# Determine event from Claude Code's hook wiring. The event name is passed in the
# JSON payload as hookSpecificOutput.hookEventName in the request Claude Code
# builds — but the caller shape differs per event. Read raw stdin once.
input="$(cat)"

# jq is required. If missing, silently no-op (never block user work).
command -v jq >/dev/null 2>&1 || exit 0

event="$(printf '%s' "$input" | jq -r '.hook_event_name // empty' 2>/dev/null)"

triggers_file="${CLAUDE_PLUGIN_ROOT:-.}/hooks/skill-triggers.json"
[ -f "$triggers_file" ] || exit 0

case "$event" in
  PreToolUse)
    subject="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)"
    map_key="bash_command"
    ;;
  UserPromptSubmit)
    subject="$(printf '%s' "$input" | jq -r '.prompt // .user_prompt // empty' 2>/dev/null)"
    map_key="user_prompt"
    ;;
  *)
    # Some Claude Code versions omit hook_event_name; heuristic fallback.
    if printf '%s' "$input" | jq -e '.tool_name == "Bash"' >/dev/null 2>&1; then
      subject="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)"
      map_key="bash_command"
    elif printf '%s' "$input" | jq -e '.prompt // .user_prompt' >/dev/null 2>&1; then
      subject="$(printf '%s' "$input" | jq -r '.prompt // .user_prompt // empty' 2>/dev/null)"
      map_key="user_prompt"
    else
      exit 0
    fi
    ;;
esac

[ -n "$subject" ] || exit 0

# Match each rule's pattern against subject. Collect hits (skill + why).
# The pattern is treated as an extended regex (grep -E). Case-insensitive is
# encoded per-rule in the pattern itself with (?i)… when needed for user_prompt.
matches="$(jq -c --arg key "$map_key" '.[$key] // []' "$triggers_file")"

hits="$(printf '%s' "$matches" | jq -c '.[]' 2>/dev/null | while read -r rule; do
  pattern="$(printf '%s' "$rule" | jq -r '.pattern')"
  # Strip a leading (?i) inline flag — bash regex has no equivalent inline flag,
  # so treat that as "match case-insensitively".
  if [[ "$pattern" == '(?i)'* ]]; then
    pat="${pattern#(?i)}"
    if printf '%s' "$subject" | grep -Eiq -- "$pat"; then
      printf '%s\n' "$rule"
    fi
  else
    if printf '%s' "$subject" | grep -Eq -- "$pattern"; then
      printf '%s\n' "$rule"
    fi
  fi
done)"

[ -n "$hits" ] || exit 0

# Deduplicate by skill (multiple regex might match the same skill).
uniq_hits="$(printf '%s\n' "$hits" | jq -sc 'unique_by(.skill)')"

# Build a human-readable bullet list. Include ~why~ when present.
bullets="$(printf '%s' "$uniq_hits" | jq -r '.[] | "- **claude-skills:\(.skill)** — \(.why // "matches this action")"')"

reminder=$(cat <<EOF
**Plugin skill match — prefer skill invocation over inline reimplementation.**

The following plugin skill(s) match what you were about to do:
$bullets

Inline reimplementation of these workflows typically costs 5–15 tool calls plus footguns the skill has already encoded (e.g. the 30-min curl-hang for MCP bridge readiness, or forgetting the PR Demo section embed step). Skill invocation is one call.

If you have a specific reason not to use the skill for this instance — say it out loud — otherwise invoke it via the Skill tool.
EOF
)

# Emit as PreToolUse additionalContext (matches Claude Code's hook schema).
# jq handles the JSON escaping so the reminder can contain any characters.
jq -n --arg ev "$event" --arg msg "$reminder" \
  '{hookSpecificOutput: {hookEventName: $ev, additionalContext: $msg}}'
exit 0
