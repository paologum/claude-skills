#!/usr/bin/env bash
# PreToolUse Bash hook — deny shell polling loops for the Unity MCP bridge.
# Rationale: waiting for the Coplay MCP bridge to come up should use
# ScheduleWakeup, not `until lsof/curl/pgrep; do sleep; done` in Bash.
# See memory feedback_no_bash_polls_for_mcp.
#
# Fires only on the loop pattern; lone `lsof`, `curl`, `pgrep` calls are fine.

set -o pipefail

payload=$(cat)
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$cmd" ] && exit 0

# Combined trigger: `until` loop + any of the known bridge-readiness signals.
if printf '%s' "$cmd" | grep -qiE 'until.*(lsof.*8080|curl.*(127\.0\.0\.1:8080|localhost:8080|:8080/mcp)|mcp-for-unity|Library/MCPForUnity/RunState)'; then
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Polling loops for the Unity MCP bridge are blocked. Use ScheduleWakeup(60-90s) with a self-contained resume prompt instead — the harness will re-invoke you when the wakeup fires, and you can call ReadMcpResourceTool on mcpforunity://instances directly at that point. See memory feedback_no_bash_polls_for_mcp."}}
JSON
fi

exit 0
