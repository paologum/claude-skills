---
name: pr-video
description: Records a Unity Editor UI/gameplay clip and embeds it as an inline playable video in the current Pull Request. Primary path uses Unity Recorder (H.264 MP4 via UnityMediaEncoder — no ffmpeg) + `gh attach` (Addono/gh-attach, browser-session auth) to upload to the `github.com/user-attachments/assets/*` CDN — the only URL scheme GitHub server-side-renders as a real `<video>` element with play/scrub/fullscreen. Automatic fallback to a GIF (Unity Recorder → gifski) committed under `docs/pr-videos/` when the MP4 exceeds 10 MB, the upload fails, or `gh attach login` hasn't been run. Verifies every step end-to-end — file exists and has non-zero duration, upload URL returns HTTP 200, PR body's rendered HTML actually contains a `<video>` tag pointing at the uploaded asset. Never leaves a broken PR. Use when the user asks to record a PR video, capture a Unity video for the PR, add a video demo to the PR, screencast the change for review, "show the reviewer the animation", or "attach a video to this PR".
allowed-tools: "Bash(git *) Bash(gh *) Bash(gh attach *) Bash(mkdir *) Bash(ls *) Bash(rm *) Bash(du *) Bash(brew *) Bash(which *) Bash(gifski *) Bash(ffmpeg *) Bash(ffprobe *) Bash(curl *) Bash(stat *) Read Write Edit"
argument-hint: "[duration-seconds] [PR-number]"
---

## Context

**Repo root:**
```
!`git rev-parse --show-toplevel 2>/dev/null || pwd`
```

**Current branch:**
```
!`git rev-parse --abbrev-ref HEAD`
```

**Target PR (arg or auto-detect from branch):**
```
!`gh pr view --json number,title,url,headRepositoryOwner,headRepository 2>/dev/null || echo "no PR yet — will save clip locally and print embed snippet"`
```

**Owner/repo (for gh attach --target):**
```
!`gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "not in a gh-recognized repo"`
```

**Prerequisites installed?**
```
!`printf "gh attach: "; gh attach --version 2>/dev/null || echo "MISSING — install: gh extension install Addono/gh-attach"; printf "gifski: "; which gifski || echo "MISSING — install: brew install gifski (only needed for GIF fallback)"; printf "ffprobe: "; which ffprobe || echo "MISSING — install: brew install ffmpeg (used to verify duration)"`
```

**`gh attach` session valid?** (uses `gh auth token` — you're set if `gh` itself works)
```
!`gh attach login --status 2>/dev/null || echo "NOT AUTHENTICATED — run: gh attach login (no browser — just refreshes from 'gh auth token')"`
```

**Existing pr-videos directory (used only by the GIF fallback):**
```
!`ls -la docs/pr-videos 2>/dev/null || echo "(will create on first fallback)"`
```

**Is Unity MCP available?** Confirm `mcp__UnityMCP__execute_code` and `mcp__UnityMCP__manage_editor` are in your tool list this session. Do NOT trust `.mcp.json`'s presence — verify by calling `mcp__UnityMCP__manage_editor` with `action: "get_state"`. If genuinely absent, refuse and point the user at `/unity-mcp-setup` — this skill needs the live Editor.

**Unity Recorder package installed?** Check `Packages/manifest.json` for `com.unity.recorder`. If missing, tell the user how to add it (Window → Package Manager → `+` → Add package by name → `com.unity.recorder`) and stop — do NOT try to install it via `manage_packages` unsupervised.

## Task

Record a `$ARGUMENTS[0]`-second clip (default: 8 seconds; hard cap: 30 seconds — anything longer will blow past the 10 MB attachment limit) of the running Unity Editor and embed it as an inline playable video in the Demo section of the current PR (or the PR given as `$ARGUMENTS[1]`).

The pipeline has three tracks. Do them in order — each track's failure is what triggers the next. **Never skip verification gates.** A successful skill run means the reviewer clicks Play in the PR body and the clip plays. Anything less is a failure the skill must report honestly.

---

## Track A — Fluid MP4 via Unity Recorder + gh-attach (PRIMARY)

### A1. Precheck

- `gh attach login --status` must exit 0 (authenticated). If it exits 2, run `gh attach login` — it's a non-interactive wrapper around `gh auth token`, safe to run unattended. If `gh auth token` itself fails, the user needs to run `gh auth login` first (that one IS interactive).
- `owner/repo` must be resolvable (from `gh repo view` above).
- A PR must exist on this branch. If not, do steps A2–A7 anyway, save the MP4 to `Temp/pr-video.mp4`, and print the exact `![](URL)` snippet the user can paste when they open the PR.

### A2. Enter Play mode

```
mcp__UnityMCP__manage_editor({ action: "get_state" })
```
- If `isPlaying: true`, do NOT enter Play mode again (already running — user probably staged the scene). Just proceed to A3.
- If `isCompiling: true`, wait — poll every 2s, max 60s.
- If any Play-mode test job is active, refuse — killing it via a Recorder start can leave the Editor in a bad state.
- Otherwise: `manage_editor({ action: "play" })`, wait 1s, re-check state.

### A3. Start recording via Unity Recorder API

Compute the target path first (absolute, project-local):
```
Temp/pr-video-<PR>-<slug>.mp4
```
where `<slug>` is a short kebab-case description of the change (derived from the branch name or the PR title). Announce the exact path before recording so the user knows where to look if a step later fails.

Then run this via `mcp__UnityMCP__execute_code` — verbatim, do NOT modify field names, the Recorder API is picky:

```csharp
using UnityEditor.Recorder;
using UnityEditor.Recorder.Input;

var outputAbs = System.IO.Path.GetFullPath(System.IO.Path.Combine(
    UnityEngine.Application.dataPath, "..", "Temp", "pr-video-<PR>-<slug>.mp4"));
System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(outputAbs));

var settings = ScriptableObject.CreateInstance<RecorderControllerSettings>();
settings.SetRecordModeToManual();
settings.FrameRate = 30;
settings.CapFrameRate = true;

var movie = ScriptableObject.CreateInstance<MovieRecorderSettings>();
movie.name = "PR Video";
movie.Enabled = true;
movie.OutputFormat = MovieRecorderSettings.VideoRecorderOutputFormat.MP4;
movie.VideoBitRateMode = UnityEditor.VideoBitrateMode.Medium;
movie.ImageInputSettings = new GameViewInputSettings {
    OutputWidth  = 1280,
    OutputHeight = 720,
};
movie.OutputFile = outputAbs.Replace(".mp4", "");   // Recorder appends the extension itself
movie.AudioInputSettings.PreserveAudio = false;

settings.AddRecorderSettings(movie);

var controller = new RecorderController(settings);
controller.PrepareRecording();
controller.StartRecording();
UnityEngine.Debug.Log("PR_VIDEO_RECORDER_STARTED path=" + outputAbs);

// Stash the controller on a hidden GameObject so the Stop call can find it later
var host = new GameObject("__PR_VIDEO_HOST__");
host.hideFlags = HideFlags.HideAndDontSave;
var holder = host.AddComponent<PRVideoHolder>();
holder.Controller = controller;
```

You will need to define `PRVideoHolder` in an Editor script the FIRST time this skill runs against a project — put it under `Assets/Editor/PRVideoHolder.cs`:

```csharp
using UnityEditor.Recorder;
using UnityEngine;
public class PRVideoHolder : MonoBehaviour {
    public RecorderController Controller;
}
```

If that file doesn't exist yet, create it BEFORE running the record snippet, and wait ~2s for Unity to compile it (poll `get_state` for `isCompiling: false`).

### A4. Let the recording run

- Wait `duration` seconds using an explicit `wait` (do NOT rely on the `SetRecordModeToManual` timer — it's less predictable than an external wait).
- During the wait, the user's Editor is playing normally. If the user asked for a specific interaction to be recorded, drive it via other `mcp__UnityMCP__` calls (button clicks via `manage_ui`, scene changes via `manage_scene`, etc.) — but keep the interaction bounded to `duration - 1` seconds so the tail of the clip isn't dead.

### A5. Stop recording

```csharp
var host = GameObject.Find("__PR_VIDEO_HOST__");
var holder = host?.GetComponent<PRVideoHolder>();
holder?.Controller.StopRecording();
GameObject.DestroyImmediate(host);
UnityEngine.Debug.Log("PR_VIDEO_RECORDER_STOPPED");
```

Then `manage_editor({ action: "stop" })` to exit Play mode.

### A6. Verify the MP4 exists and is valid

```bash
stat -f%z "Temp/pr-video-<PR>-<slug>.mp4"          # size in bytes; must be > 0
ffprobe -v error -show_entries format=duration \
        -of default=noprint_wrappers=1:nokey=1 \
        "Temp/pr-video-<PR>-<slug>.mp4"             # duration seconds; must be > 0
```

Fail A → fall to B when:
- File missing / size 0 → the Recorder didn't write. Usually means Recorder package isn't installed, or `PRVideoHolder.cs` didn't compile.
- Duration 0 or missing → container is corrupt.
- Size > 10485760 (10 MB) → will fail the free-plan attachment limit. Fall to B (GIF).

### A7. Upload via gh attach

```bash
gh attach upload "Temp/pr-video-<PR>-<slug>.mp4" \
  --target "<owner>/<repo>#<PR>" \
  --strategy browser-session \
  --format url
```

Capture stdout — it's the bare URL (looks like `https://github.com/user-attachments/assets/<uuid>`).

Fail A → fall to B when: exit code non-zero, or output doesn't match the `user-attachments/assets/` pattern.

### A8. Verify the URL is reachable

```bash
curl -sI -L -o /dev/null -w "%{http_code}" "<the-url>"
```
Must be `200`. `404` or `403` → fall to B.

### A9. Edit the PR body

Do NOT try to inline-`sed` into `--body`. Use the temp-file pattern:

```bash
gh pr view <PR> --json body -q .body > /tmp/pr-body.md
```

Open `/tmp/pr-body.md` with the `Edit` tool. Find `_drag screenshot here_`, `_drag video here_`, or the entire `## Demo` section (whichever exists). Replace with:

```markdown
## Demo

<the-url>
```

**Pasting the bare URL on its own line is what triggers GitHub's inline `<video>` renderer.** Do NOT wrap it in `![]()` — for user-attachments video, the bare URL is the correct form; markdown image syntax turns it into an `<img>` and it won't play.

Then:
```bash
gh pr edit <PR> --body-file /tmp/pr-body.md
```

### A10. Verify the PR body actually renders as `<video>`

```bash
gh api "repos/<owner>/<repo>/pulls/<PR>" --header "Accept: application/vnd.github.html+json" --jq .body_html | grep -c "<video"
```

Must be `1` (or greater). If `0`, the URL was written but GitHub didn't recognize it as a video — this is the failure mode where the reviewer sees a plain hyperlink. Fall to B and rewrite the body with the GIF instead.

### A11. Report

Print:
```
✓ Recorded  Temp/pr-video-<PR>-<slug>.mp4 (<size> MB, <duration>s)
✓ Uploaded  <the-url>
✓ Embedded  in PR #<PR> Demo section
✓ Verified  rendered as <video> element
```

Delete the local `Temp/pr-video-<PR>-<slug>.mp4` — the source of truth is now the GitHub CDN, and stale local MP4s aren't useful.

---

## Track B — GIF fallback

Triggered when any A-gate fails. Runs from whatever intermediate state we're in.

### B1. Ensure we have a source frame stream

Two entry points into B:

- **B-from-A** — an MP4 exists from A3–A5 but was too big / didn't upload / didn't render. Reuse it.
- **B-from-scratch** — Recorder never wrote a valid MP4 (A6 failed). Re-run A2–A6 but change `movie.OutputFormat = MovieRecorderSettings.VideoRecorderOutputFormat.MP4` to also lower to `OutputWidth = 960, OutputHeight = 540`. If it STILL fails, use `mcp__UnityMCP__execute_code` to write PNG frames via `ScreenCapture.CaptureScreenshot` inside an `EditorApplication.update` loop for `duration` seconds — brutish but works when Recorder is broken.

### B2. Convert to GIF via gifski

```bash
mkdir -p docs/pr-videos
ffmpeg -y -i "Temp/pr-video-<PR>-<slug>.mp4" -vf fps=24 -f image2pipe -vcodec ppm - \
  | gifski -o "docs/pr-videos/pr-<PR>-<slug>.gif" --fps 24 --quality 90 --width 960 -
```

If the resulting GIF is > 10 MB, retry with `--quality 70 --width 720`. If still > 10 MB, retry with `--fps 15`. Report each downgrade to the user.

### B3. Commit and push

```bash
git add "docs/pr-videos/pr-<PR>-<slug>.gif"
git commit -m "docs: PR video for #<PR>"
git push
```

If the branch has no upstream, `git push -u origin <branch>` first. If push fails (rebase needed, hook fails), stop and report — do NOT force-push.

### B4. Edit the PR body

Same temp-file → Edit → `gh pr edit --body-file` dance as A9. Replace the Demo section content with:

```markdown
## Demo

![](docs/pr-videos/pr-<PR>-<slug>.gif)
```

Relative paths in PR body markdown resolve against the head SHA of the PR — this is the only reliably-rendering form for a committed image.

### B5. Verify

```bash
curl -sI -L -o /dev/null -w "%{http_code}" \
  "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/docs/pr-videos/pr-<PR>-<slug>.gif"
```
Must be `200`. Then confirm the rendered HTML has an `<img` with matching src:

```bash
gh api "repos/<owner>/<repo>/pulls/<PR>" --header "Accept: application/vnd.github.html+json" --jq .body_html | grep -c "pr-videos/pr-<PR>-<slug>.gif"
```

### B6. Report

```
✓ Recorded  MP4 (<size> MB) — fallback triggered because <reason>
✓ Converted docs/pr-videos/pr-<PR>-<slug>.gif (<size> MB, <fps> fps, <width>px)
✓ Committed and pushed to <branch>
✓ Embedded  in PR #<PR> Demo section as animated image
```

---

## Track C — Last resort

If Track B also fails (git push blocked, gifski broken, ffmpeg missing), commit the MP4 to `docs/pr-videos/`, embed it as `![](docs/pr-videos/pr-<PR>-<slug>.mp4)`, and **explicitly tell the user**:

> Committed MP4 as `docs/pr-videos/pr-<PR>-<slug>.mp4`. GitHub will render this as a download link, not an inline video. If you want an inline video, drag the MP4 into the PR body manually — GitHub's web UI is the fallback for the fallback.

Then stop. Do not pretend the goal was achieved.

---

## Rules

- **Verify every step**. This skill's whole reason for existing is to not ship broken PRs. Every gate is mandatory — do not "assume it worked".
- **Never enter Play mode without checking `get_state` first.** Killing an active test job or stomping on the user's staged scene is a bad experience.
- **Never keep the local MP4** after a successful A-track upload — it's just clutter.
- **Never commit an MP4 unless Track C is triggered.** Committed MP4s bloat the repo history without giving a good PR experience.
- **Refuse cleanly** if any prereq is missing (Recorder package, gh-attach, browser-session login) — print the exact one-line install/setup command and stop. Do not try to install packages unsupervised.
- **Do NOT use `sed` on PR bodies.** Always the temp-file + Edit + `--body-file` pattern. PR bodies routinely contain characters that break shell substitution.
- **Do NOT wrap the user-attachments URL in `![]()`** — for video attachments, the bare URL on its own line is the form GitHub renders inline. Markdown image syntax turns it into an `<img>` that won't play.
- **Respect the size cap.** 10 MB free / 100 MB paid — the skill doesn't know which the user is on, so treat 10 MB as the hard ceiling for Track A and fall to B when exceeded.
- **Duration cap.** Hard-refuse `> 30` seconds — clips longer than that are (a) way over the attachment limit at 720p, (b) not what reviewers watch. Suggest breaking the demo into multiple PRs if the user pushes back.
