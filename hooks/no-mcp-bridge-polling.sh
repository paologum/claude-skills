#!/usr/bin/env bash
# PreToolUse Bash hook — deny shell polling loops for the Unity MCP bridge.
# Rationale: waiting for a Unity Editor to register on the stdio bridge should use
# ScheduleWakeup, not a `until lsof/cat/pgrep; do sleep; done` loop in Bash.
# See memory feedback_no_bash_polls_for_mcp.
#
# Fires only on the loop pattern; lone `lsof`, `cat`, `pgrep` calls are fine.

set -o pipefail

payload=$(cat)
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$cmd" ] && exit 0

# Authoring these skills embeds the patterns below as documentation text. Exempt only a
# command that is *nothing but* running a script file — deliberately narrow, because an
# exemption that matches part of a compound command fails open on the rest of it. To edit
# a file containing these patterns, put the edit in a script and run it.
if printf '%s' "$cmd" | grep -qE '^[[:space:]]*(python3?|node)[[:space:]]+[^;&|]+\.(py|js)[[:space:]]*$'; then
  exit 0
fi

# Combined trigger: a wait loop + any of the known bridge-readiness signals.
# stdio-era signals: the Editor's socket (6400+) and the status files it publishes.
if printf '%s' "$cmd" | grep -qiE '(until|while).*(lsof.*(640[0-9]|8080)|curl.*(127\.0\.0\.1|localhost):(6[45]0[0-9]|8080)|unity-mcp-status|mcp-for-unity|Library/MCPForUnity/RunState)'; then
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Polling loops for the Unity MCP bridge are blocked. Use ScheduleWakeup(60-90s) with a self-contained resume prompt instead — the harness will re-invoke you when the wakeup fires, and you can call ReadMcpResourceTool on mcpforunity://instances directly at that point. See memory feedback_no_bash_polls_for_mcp."}}
JSON
fi

exit 0
