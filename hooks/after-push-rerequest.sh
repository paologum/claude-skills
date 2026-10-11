#!/usr/bin/env bash
# PostToolUse Bash hook — after a successful `git push` to a branch whose open PR
# already has reviews from other people, remind the model to post a summary comment
# and re-request those reviewers. Users otherwise end up typing "rerequest X" and
# "did you rerequest?" after nearly every review round.
#
# Never blocks: any failure (no jq/gh, no PR, offline) exits 0 silently.

set -u

payload="$(cat)"
command -v jq >/dev/null 2>&1 || exit 0
command -v gh >/dev/null 2>&1 || exit 0

cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null)"
# `git push` in command position only — not inside a commit message or an echo.
printf '%s' "$cmd" | grep -Eq '(^|[;&|(])[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+push([[:space:]]|$)' || exit 0
printf '%s' "$cmd" | grep -Eq -- 'push[^;&|]*[[:space:]](--dry-run|-n)([[:space:]]|$)' && exit 0

out="$(printf '%s' "$payload" | jq -r '.tool_response | if type == "object" then ((.stdout // "") + "\n" + (.stderr // "")) else tostring end' 2>/dev/null)"
# Failed or no-op pushes aren't a new round. Line-anchored so branch names and
# unrelated output in a compound command don't suppress a real push.
printf '%s\n' "$out" | grep -Eq '^[[:space:]]*! \[(rejected|remote rejected)\]|^error: failed to push|^fatal:|^Everything up-to-date' && exit 0

# macOS ships no `timeout`; fall back to running unbounded rather than never running.
t() { if command -v timeout >/dev/null 2>&1; then timeout "$@"; elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$@"; else shift; "$@"; fi; }

cwd="$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)"
[ -n "$cwd" ] && cd "$cwd" 2>/dev/null
# Follow `git -C <dir> push` / `cd <dir> && git push` so we query the pushed repo.
dir="$(printf '%s' "$cmd" | sed -nE 's/.*git[[:space:]]+-C[[:space:]]+([^[:space:]]+)[[:space:]]+push.*/\1/p' | head -1)"
[ -z "$dir" ] && dir="$(printf '%s' "$cmd" | sed -nE 's/^[[:space:]]*cd[[:space:]]+([^[:space:];&]+)[[:space:]]*&&.*/\1/p' | head -1)"
dir="${dir//\"/}"; dir="${dir//\'/}"; dir="${dir/#\~/$HOME}"
[ -n "$dir" ] && cd "$dir" 2>/dev/null

# The pushed branch, from git's "<src> -> <dst>" line; else the checked-out branch.
branch="$(printf '%s\n' "$out" | grep -v '^remote:' | sed -nE 's/.*[[:space:]]->[[:space:]]+([^[:space:]]+).*/\1/p' | head -1)"

pr_json="$(t 10 gh pr view ${branch:+"$branch"} --json number,state,reviews,reviewRequests 2>/dev/null)" || exit 0
[ "$(printf '%s' "$pr_json" | jq -r '.state')" = "OPEN" ] || exit 0

me="$(t 5 gh api user --jq .login 2>/dev/null)"
[ -n "$me" ] || exit 0
reviewers="$(printf '%s' "$pr_json" | jq -r --arg me "$me" '
  [.reviews[].author.login | select(. != null and . != $me and (endswith("[bot]") | not))] | unique | join(", ")' 2>/dev/null)"
[ -n "$reviewers" ] || exit 0

pending="$(printf '%s' "$pr_json" | jq -r '[.reviewRequests[] | (.login // .slug // .name)] | map(select(. != null)) | join(", ")' 2>/dev/null)"
num="$(printf '%s' "$pr_json" | jq -r '.number')"

msg="You just pushed to PR #${num}, which has been reviewed by: ${reviewers}."
if [ -n "$pending" ]; then
  msg="${msg} Review is currently requested from: ${pending}."
fi
msg="${msg} If this push addresses review feedback, finish the round before reporting done: post one PR comment mapping each review point to its fix (commit SHA) or follow-up issue, then re-request review (gh pr edit ${num} --add-reviewer <login>) from anyone not already requested. /claude-skills:address-review does the whole round."

jq -n --arg msg "$msg" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $msg}}'
exit 0
