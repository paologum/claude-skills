---
name: pr-video
description: Records a Unity Editor UI/gameplay clip and embeds it as an inline playable video in the current Pull Request. Primary path uses Unity Recorder (H.264 MP4 via UnityMediaEncoder — no ffmpeg) + `gh attach` (Addono/gh-attach, browser-session auth) to upload to the `github.com/user-attachments/assets/*` CDN — the only URL scheme GitHub server-side-renders as a real `<video>` element with play/scrub/fullscreen. When browser-session is rejected (private-repo 422s, missing cookie), automatic fallback to a GIF via gifski uploaded through `gh attach --strategy release-asset` (hidden `_gh-attach-assets` release; renders inline as animated `<img>` on private repos, doesn't need the browser cookie, doesn't commit anything to the repo). Only then falls to chat-handoff (SendUserFile → drag-drop in web UI) or a committed GIF as last resorts. Verifies every step end-to-end — file exists and has non-zero duration, upload URL returns HTTP 200, PR body's rendered HTML actually contains a `<video>` or `<img>` tag pointing at the uploaded asset. Never leaves a broken PR. Use when the user asks to record a PR video, capture a Unity video for the PR, add a video demo to the PR, screencast the change for review, "show the reviewer the animation", or "attach a video to this PR".
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

**`gh attach` session valid?** (browser-session cookie must be logged in)
```
!`gh attach login --status 2>/dev/null || echo "NOT LOGGED IN — one-time setup: gh attach login (opens browser, saves cookie to keychain)"`
```

**Existing pr-videos directory (used only by the GIF fallback):**
```
!`ls -la docs/pr-videos 2>/dev/null || echo "(will create on first fallback)"`
```

**Is Unity MCP available?** Confirm `mcp__UnityMCP__execute_code` and `mcp__UnityMCP__manage_editor` are in your tool list this session. Do NOT trust `.mcp.json`'s presence — verify by calling `mcp__UnityMCP__manage_editor` with `action: "get_state"`. If genuinely absent, refuse and point the user at `/unity-mcp-setup` — this skill needs the live Editor.

**Unity Recorder package installed?** Check `Packages/manifest.json` for `com.unity.recorder`. If missing, either (a) tell the user how to add it via Package Manager, or (b) if they've asked you to install it, add `"com.unity.recorder": "5.1.2"` to `Packages/manifest.json`'s `dependencies` block, then call `mcp__UnityMCP__execute_code` with `UnityEditor.PackageManager.Client.Resolve();` and poll `Packages/packages-lock.json` until the entry appears (30–120s). The default is (a); only do (b) with explicit permission.

## Task

Record a `$ARGUMENTS[0]`-second clip (default: 8 seconds; hard cap: 30 seconds — anything longer will blow past the 10 MB attachment limit) of the running Unity Editor and embed it as an inline playable video in the Demo section of the current PR (or the PR given as `$ARGUMENTS[1]`).

**Two levels of ambition:**

- **Passive record** — just capture whatever the user has staged in the Editor for `duration` seconds. Use when the user says "record what I'm about to do" or the change is already visible without choreography.
- **Choreographed record** — spawn a `PRVideoDriver` MonoBehaviour that runs the full demo as a single coroutine (setup, interactions, waits, stop). Use when the demo needs to open a modal, click through a flow, hover something to prove it responds, etc. Deterministic timing, no round-trip races, no lost-controller-reference bugs. **Always prefer this shape when the demo has any state changes** — see A3-choreographed below.

The pipeline has five tracks. Do them in order — each track's failure is what triggers the next. **Never skip verification gates.** A successful skill run means the reviewer clicks Play (Track A) or sees the animation loop (Track A′) in the PR body without doing anything. Anything less is a failure the skill must report honestly.

Track summary:
- **Track A** — MP4 via `gh attach --strategy browser-session` → inline `<video>` player (best UX; requires `gh attach login` cookie AND a repo the endpoint accepts).
- **Track A′** — MP4→GIF via gifski → `gh attach --strategy release-asset` → inline animated `<img>` (fully automated fallback when browser-session returns 422 or no cookie; works on private repos without any browser dance).
- **Track B** — Chat handoff: SendUserFile the MP4, user drag-drops in the web UI (only when even release-asset is refused).
- **Track C** — GIF committed to `docs/pr-videos/` and embedded with a relative path (only when the project accepts committed images and there's no interactive user).
- **Track D** — Last-resort MP4 commit with an honest "this won't play inline" note.

---

## Track A — Fluid MP4 via Unity Recorder + gh-attach (PRIMARY)

### A1. Precheck

- `gh attach login --status` should report `authenticated as <user>` for Track A. If not, skip A directly to **Track A′** — release-asset upload works without the browser-session cookie. Do NOT refuse; the fallback is fully automated. (Note: `gh attach whoami` is NOT a real subcommand; earlier versions of this skill got that wrong.)
- `owner/repo` must be resolvable (from `gh repo view` above).
- A PR must exist on this branch. If not, do steps A2–A7 anyway, save the MP4 to `Temp/pr-video.mp4`, and print the exact URL snippet the user can paste when they open the PR (bare URL on its own line — NOT `![]()`; see A9).

### A2. Bootstrap `PRVideoHolder.cs` if missing

The Recorder controller reference has to survive between `execute_code` calls, so we stash it on a MonoBehaviour. **The script must live under `Assets/` root, NOT `Assets/Editor/`** — Editor-only scripts throw `Can't add script behaviour 'PRVideoHolder' because it is an editor script.` at `AddComponent<PRVideoHolder>()` in Play mode. The Recorder type lives in the `UnityEditor.Recorder` namespace which isn't available in Player builds, so guard it with `#if UNITY_EDITOR`:

Write to `Assets/PRVideoHolder.cs`:

```csharp
using UnityEngine;

// Temporary holder used by the pr-video skill to stash a RecorderController
// between the Start and Stop execute_code calls. Safe to delete after the run.
public class PRVideoHolder : MonoBehaviour
{
#if UNITY_EDITOR
    public UnityEditor.Recorder.RecorderController Controller;
#endif
}
```

If the file already exists from a prior run, reuse it. After creating or refreshing it, call `mcp__UnityMCP__refresh_unity` and wait for `isCompiling: false` (poll every 2s, max 30s).

### A3-passive. Start recording (no choreography)

Compute the target path first (absolute, project-local): `Temp/pr-video-<PR>-<slug>.mp4` where `<slug>` is a short kebab-case description of the change (derived from the branch name or PR title). Announce the path before recording.

Then run this via `mcp__UnityMCP__execute_code`. **The `codedom` compiler (default when Microsoft.CodeAnalysis isn't installed) rejects `using` directives inside method bodies with `Unexpected symbol 'UnityEditor', expecting '('`.** So fully-qualify every type — do NOT use `using`:

```csharp
if (HandManager.Instance == null && !UnityEngine.Application.isPlaying) return "not in Play mode";
var outputAbs = System.IO.Path.GetFullPath(System.IO.Path.Combine(
    UnityEngine.Application.dataPath, "..", "Temp", "pr-video-<PR>-<slug>.mp4"));
System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(outputAbs));

var settings = ScriptableObject.CreateInstance<UnityEditor.Recorder.RecorderControllerSettings>();
settings.SetRecordModeToManual();
settings.FrameRate = 30;
settings.CapFrameRate = true;

var movie = ScriptableObject.CreateInstance<UnityEditor.Recorder.MovieRecorderSettings>();
movie.name = "PR Video";
movie.Enabled = true;
movie.OutputFormat = UnityEditor.Recorder.MovieRecorderSettings.VideoRecorderOutputFormat.MP4;
movie.VideoBitRateMode = UnityEditor.VideoBitrateMode.Medium;
movie.ImageInputSettings = new UnityEditor.Recorder.Input.GameViewInputSettings {
    OutputWidth  = 1280,
    OutputHeight = 720,
};
movie.OutputFile = outputAbs.Replace(".mp4", "");   // Recorder appends the extension itself
if (movie.AudioInputSettings != null) movie.AudioInputSettings.PreserveAudio = false;
settings.AddRecorderSettings(movie);

var controller = new UnityEditor.Recorder.RecorderController(settings);
controller.PrepareRecording();
controller.StartRecording();

var host = new GameObject("__PR_VIDEO_HOST__");
host.hideFlags = HideFlags.HideAndDontSave;
var holder = host.AddComponent<PRVideoHolder>();
holder.Controller = controller;
UnityEngine.Debug.Log("PR_VIDEO_RECORDER_STARTED path=" + outputAbs);
return outputAbs;
```

**Known gotcha:** the very first `PrepareRecording()` call after entering Play mode can throw `NullReferenceException` if execute_code runs before Unity finishes wiring up the Recorder's internal callbacks. If you hit it, exit Play mode, wait 2s, re-enter, wait 5s, retry. Two-tick warm-up is usually enough.

Then wait `duration` seconds (explicit Bash `sleep`, not the `SetRecordModeToManual` timer — the manual timer is less predictable), then jump to A5.

### A3-choreographed. Start recording (with a driver coroutine)

For any demo that needs choreography (open modal, click button, wait for animation, hover cards, etc.), do NOT use the passive pattern above — the "start → Bash sleep → poke the scene via execute_code → Bash sleep → stop" dance is race-prone and the Controller reference can be lost across execute_code calls (domain reload, script recompile, holder GO destroyed early).

Instead, write a `PRVideoDriver` MonoBehaviour to `Assets/PRVideoDriver.cs` that owns the entire recording lifecycle in a single coroutine. Template:

```csharp
using System.Collections;
using UnityEngine;

// One-shot driver for the pr-video skill. Records a clip while running the demo
// as a single coroutine so timing is deterministic and the Recorder controller
// stays reachable for the Stop call. Delete after the run.
public class PRVideoDriver : MonoBehaviour
{
#if UNITY_EDITOR
    public UnityEditor.Recorder.RecorderController Controller;
#endif
    public string OutputPath;
    public bool Done;

    IEnumerator Start()
    {
        // Give Unity one frame after StartRecording so the first captured frame isn't blank.
        yield return null;

        // --- BEGIN project-specific choreography ---
        //   Open the modal, click the button, drive whatever state the demo needs to show.
        //   Use yield return new WaitForSeconds(...) for pacing; frames tick normally.
        //   Fire pointer events with UnityEngine.EventSystems.ExecuteEvents.Execute<T>(...).
        // --- END choreography ---

        yield return new WaitForSeconds(0.5f);   // let the final frame render

#if UNITY_EDITOR
        if (Controller != null) Controller.StopRecording();
#endif
        UnityEngine.Debug.Log("[PRVideoDriver] STOPPED path=" + OutputPath);
        Done = true;
    }
}
```

Then in ONE `execute_code` call: create the RecorderControllerSettings + MovieRecorderSettings as in A3-passive, `StartRecording()`, and instead of an inert `PRVideoHolder`, spawn:

```csharp
var driverGo = new GameObject("__PR_VIDEO_DRIVER__");
driverGo.hideFlags = HideFlags.HideAndDontSave;
var driver = driverGo.AddComponent<PRVideoDriver>();
driver.Controller = controller;
driver.OutputPath = outputAbs;
```

Then Bash-`sleep` for `duration + 2` seconds (choreography wall-clock + margin) and poll `driver.Done` via a small `execute_code`:

```csharp
var g = GameObject.Find("__PR_VIDEO_DRIVER__");
if (g == null) return "driver gone";
return "done=" + g.GetComponent<PRVideoDriver>().Done;
```

When `done=True`, jump straight to A6 — the driver has already called `StopRecording()`.

**Why this shape beats the passive one for anything choreographed:**
- One coroutine, one deterministic timeline. No Bash-sleep vs Unity-frame race.
- Controller reference stays reachable for `StopRecording()` even if intervening execute_code calls trigger a domain reload (the driver holds it as a serialized field on a live MonoBehaviour).
- The demo choreography lives in C# next to the scene code it drives, not smeared across N execute_code calls with Bash sleeps between them.
- Easy to re-run: delete + redeploy `PRVideoDriver.cs`, restart Play mode.

### A4. Let the recording run

- **A3-passive**: Bash `sleep <duration>`. During the wait you MAY drive the Editor via additional `mcp__UnityMCP__` calls, but every round-trip costs 100–300ms of wall clock and races the coroutine tick. Keep it to no more than 2–3 pokes.
- **A3-choreographed**: the driver runs on its own; just wait for `driver.Done` to flip. No additional pokes.

Either way, hard-cap `duration + safety` at 30 seconds. Longer clips blow past the 10 MB attachment limit at 720p Medium bitrate.

### A5. Stop recording (passive only — choreographed already did it)

```csharp
var host = GameObject.Find("__PR_VIDEO_HOST__");
var holder = host?.GetComponent<PRVideoHolder>();
holder?.Controller?.StopRecording();
if (host != null) GameObject.DestroyImmediate(host);
UnityEngine.Debug.Log("PR_VIDEO_RECORDER_STOPPED");
```

Then `manage_editor({ action: "stop" })` to exit Play mode. **Both patterns must exit Play mode** — the MP4's moov atom is only finalized when the Recorder's OnDisable/OnDestroy runs, which happens at Play mode exit (or explicit `StopRecording()` on the coroutine driver). If you skip this, `ffprobe` will report `moov atom not found` and Track A will fail A6.

### A6. Verify the MP4 exists and is valid

```bash
stat -f%z "Temp/pr-video-<PR>-<slug>.mp4"          # size in bytes; must be > 0
ffprobe -v error -show_entries format=duration \
        -of default=noprint_wrappers=1:nokey=1 \
        "Temp/pr-video-<PR>-<slug>.mp4"             # duration seconds; must be > 0
```

Fail A → fall to B when:
- File missing / size 0 → the Recorder didn't write. Usually means Recorder package isn't installed, or `PRVideoHolder.cs` / `PRVideoDriver.cs` didn't compile.
- `moov atom not found` from ffprobe → container is corrupt because Play mode wasn't exited. Redo from A2.
- Duration 0 or missing → recording never captured any frames.
- Size > 10485760 (10 MB) → will fail the free-plan attachment limit. Fall to B.

### A7. Upload via gh attach

```bash
gh attach upload "Temp/pr-video-<PR>-<slug>.mp4" \
  --target "<owner>/<repo>#<PR>" \
  --strategy browser-session \
  --format url
```

Capture stdout — it's the bare URL (looks like `https://github.com/user-attachments/assets/<uuid>`).

Fail A → fall to B when: exit code non-zero, or output doesn't match the `user-attachments/assets/` pattern.

**Known failure mode: `Error: Failed to get upload policy: Unprocessable Entity` (HTTP 422)** — the account/repo pair rejects the pre-flight upload-policy request even though `gh attach login --status` reports authenticated. Reproduces on 73-byte PNGs, so it's not a size/format issue; it's the endpoint refusing this token for this repo (private-repo permission model, missing enterprise flag, etc.). No amount of retry, re-login, or format tweak fixes it. Fall to **Track A′** immediately when you see 422 — the release-asset strategy uses a different endpoint that this same account/repo pair accepts.

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

## Track A′ — GIF via `gh attach --strategy release-asset` (automated fallback)

Triggered when Track A fails at A1 (no browser-session cookie) or A7 (422 / 403 from `browser-session`). The MP4 is valid; only the browser-session endpoint refuses it. `--strategy release-asset` uploads to a hidden `_gh-attach-assets` release on the repo — different endpoint, different auth path, and it works on private repos without a browser cookie. But **release-asset MP4 URLs do NOT render as inline `<video>`** (GitHub only server-side-renders `<video>` for `user-attachments/assets/` URLs). PNG and GIF URLs from release-asset DO render inline as `<img>`. So the play here is: convert MP4→GIF, upload the GIF via release-asset, embed as `![](URL)`.

Runs entirely from what Track A already produced — no re-recording.

### A′1. Convert MP4 → GIF via gifski

Gifski does not accept stdin as its documented use suggests (`error: Video files must be specified as a path on disk. Input via stdin is not supported`). Use a two-step pipeline through PNG frames:

```bash
mkdir -p /tmp/pr-video-frames && rm -f /tmp/pr-video-frames/*.png
ffmpeg -y -i "Temp/pr-video-<PR>-<slug>.mp4" -vf fps=24 /tmp/pr-video-frames/f%04d.png
gifski -o "Temp/pr-video-<PR>-<slug>.gif" \
       --fps 24 --quality 80 --width 960 \
       /tmp/pr-video-frames/*.png
rm -rf /tmp/pr-video-frames
```

Reference sizing: at 24 fps × 960 px × quality 80, a 12-second clip lands ≈ 850 KB. If the GIF is > 10 MB, retry with `--quality 70 --width 720`, then `--fps 15` if still too big.

### A′2. Upload the GIF via release-asset

```bash
URL=$(gh attach upload "Temp/pr-video-<PR>-<slug>.gif" \
  --target "<owner>/<repo>#<PR>" \
  --strategy release-asset \
  --format url)
echo "$URL"
```

URL shape: `https://github.com/<owner>/<repo>/releases/download/_gh-attach-assets/pr-video-<PR>-<slug>.gif`. If this fails too, fall to **Track B**.

### A′3. Verify the URL

```bash
curl -sI -L -o /dev/null -w "%{http_code}" "$URL"   # must be 200
```

### A′4. Edit the PR body

Same temp-file → Edit → `--body-file` pattern as A9. Replace the Demo section content with:

```markdown
## Demo

![Demo animation]($URL)
```

**Do use `![]()` here** — this is a GIF-as-image, not a user-attachments video. Bare URL would try to trigger the `<video>` renderer, which doesn't apply to release-asset URLs and leaves you with just a hyperlink.

### A′5. Verify the PR body actually renders as an inline `<img>`

```bash
gh api "repos/<owner>/<repo>/pulls/<PR>" \
  --header "Accept: application/vnd.github.html+json" \
  --jq .body_html \
  | grep -c "releases/download/_gh-attach-assets/pr-video-<PR>-<slug>.gif"
```

Must be `1` (or greater). If `0`, the URL was written but GitHub's renderer stripped it — check for accidental HTML entity escaping or a wrapping code fence.

### A′6. Report

```
✓ Recorded    Temp/pr-video-<PR>-<slug>.mp4 (<size> MB, <duration>s)
✓ Converted   Temp/pr-video-<PR>-<slug>.gif  (<size> MB, 24 fps, 960px)
✓ Uploaded    <URL>   [release-asset — browser-session was <reason>]
✓ Embedded    in PR #<PR> Demo section as animated <img>
✓ Verified    body_html contains the GIF URL
```

Delete both the local MP4 and GIF — release-asset upload is durable and the source of truth is now the release download URL.

---

## Track B — Chat handoff (when both CDN paths reject the upload)

Triggered when BOTH Track A (browser-session) and Track A′ (release-asset) fail. Rare — the two paths use different endpoints and auth, so a repo/account combo that refuses both usually has a broader policy issue that the user needs to know about. The MP4 is valid; both CDN uploads are blocked. The user's own browser session in the web UI can always drag-drop-upload to user-attachments. Hand off cleanly:

### B1. Send the MP4 to the user

```
SendUserFile({
  files: ["Temp/pr-video-<PR>-<slug>.mp4"],
  caption: "MP4 for PR #<PR>. gh-attach browser-session hit <error1>, release-asset hit <error2>. Drag this into the Demo section of the PR body — GitHub's web UI will upload to the user-attachments CDN and paste the URL that renders inline as <video>. Then reply 'done' and I'll verify.",
  status: "proactive"
})
```

### B2. Wait for the user

Do NOT commit anything, do NOT retry gh attach, do NOT go to Track C on your own. This is the point of the handoff — the user's browser session succeeds where the CLI can't.

### B3. Verify once the user says done

Re-run A10 to confirm the body now contains `<video`. If yes, print:
```
✓ Recorded  Temp/pr-video-<PR>-<slug>.mp4 (<size> MB, <duration>s)
✓ Handed off  MP4 to user (chat) — gh attach rejected with <error>
✓ User drag-dropped into PR #<PR> Demo section
✓ Verified  rendered as <video> element
```
and delete the local MP4.

If A10 still returns 0, the user probably dropped the file in wrong (attached as download link, or missed the Demo section). Show them the current body and point at what to change; retry verify.

---

## Track C — GIF committed to the repo (when the CDN and the chat handoff are both off the table)

Triggered when Track A′ AND Track B are both off the table — e.g. a headless run with no interactive user AND `gh attach --strategy release-asset` also failed (network offline, `_gh-attach-assets` release-write disabled by repo policy). Only take this route when the project permits committed demo images — see the "no images in the repo" guard below.

### C1. Ensure we have a source frame stream

Two entry points into C:

- **C-from-A** — an MP4 exists from A3–A5 but was too big / didn't upload / didn't render. Reuse it.
- **C-from-scratch** — Recorder never wrote a valid MP4 (A6 failed). Re-run A2–A6 but change `OutputWidth = 960, OutputHeight = 540` for a smaller MP4. If it STILL fails, use `mcp__UnityMCP__execute_code` to write PNG frames via `UnityEngine.ScreenCapture.CaptureScreenshot` inside an `EditorApplication.update` loop for `duration` seconds — brutish but works when Recorder is broken.

### C2. Convert to GIF via gifski

```bash
mkdir -p docs/pr-videos
ffmpeg -y -i "Temp/pr-video-<PR>-<slug>.mp4" -vf fps=24 -f image2pipe -vcodec ppm - \
  | gifski -o "docs/pr-videos/pr-<PR>-<slug>.gif" --fps 24 --quality 90 --width 960 -
```

If the resulting GIF is > 10 MB, retry with `--quality 70 --width 720`. If still > 10 MB, retry with `--fps 15`. Report each downgrade to the user.

### C3. Commit and push

```bash
git add "docs/pr-videos/pr-<PR>-<slug>.gif"
git commit -m "docs: PR video for #<PR>"
git push
```

If the branch has no upstream, `git push -u origin <branch>` first. If push fails (rebase needed, hook fails), stop and report — do NOT force-push.

**Check the project's memory / CLAUDE.md first** — some projects have a firm "no images in the repo" rule (e.g. `PR screenshots never in the repo`). If so, refuse Track C, back off to Track B (chat handoff), and let the user decide.

### C4. Edit the PR body

Same temp-file → Edit → `gh pr edit --body-file` dance as A9. Replace the Demo section content with:

```markdown
## Demo

![](docs/pr-videos/pr-<PR>-<slug>.gif)
```

Relative paths in PR body markdown resolve against the head SHA of the PR — this is the only reliably-rendering form for a committed image.

### C5. Verify

```bash
curl -sI -L -o /dev/null -w "%{http_code}" \
  "https://raw.githubusercontent.com/<owner>/<repo>/<branch>/docs/pr-videos/pr-<PR>-<slug>.gif"
```
Must be `200`. Then confirm the rendered HTML has an `<img` with matching src:

```bash
gh api "repos/<owner>/<repo>/pulls/<PR>" --header "Accept: application/vnd.github.html+json" --jq .body_html | grep -c "pr-videos/pr-<PR>-<slug>.gif"
```

### C6. Report

```
✓ Recorded  MP4 (<size> MB) — fallback triggered because <reason>
✓ Converted docs/pr-videos/pr-<PR>-<slug>.gif (<size> MB, <fps> fps, <width>px)
✓ Committed and pushed to <branch>
✓ Embedded  in PR #<PR> Demo section as animated image
```

---

## Track D — Last resort

If Track C also fails (git push blocked, gifski broken, ffmpeg missing, project forbids committing images), commit the MP4 to `docs/pr-videos/`, embed it as `![](docs/pr-videos/pr-<PR>-<slug>.mp4)`, and **explicitly tell the user**:

> Committed MP4 as `docs/pr-videos/pr-<PR>-<slug>.mp4`. GitHub will render this as a download link, not an inline video. If you want an inline video, drag the MP4 into the PR body manually — GitHub's web UI is the fallback for the fallback.

Then stop. Do not pretend the goal was achieved.

---

## Cleanup

After ANY successful track:
- Delete `Assets/PRVideoHolder.cs` and `Assets/PRVideoDriver.cs` (`.meta` files too) — one-shot scaffolding, not part of the project.
- Delete the local `Temp/pr-video-<PR>-<slug>.mp4` (Track A/B) — the source of truth is on the CDN.
- If you added `com.unity.recorder` to `Packages/manifest.json` for this run and the project didn't ship with it before, revert the manifest (`git checkout -- Packages/manifest.json Packages/packages-lock.json`) unless the user wants it kept.

---

## Rules

- **Verify every step**. This skill's whole reason for existing is to not ship broken PRs. Every gate is mandatory — do not "assume it worked".
- **Prefer the choreographed driver pattern** for anything that involves state changes. The passive `Start → sleep → Stop` shape is fine for "capture what's already on screen" but loses reliably to timing/domain-reload races once the demo has more than one moving part.
- **Never enter Play mode without checking `get_state` first.** Killing an active test job or stomping on the user's staged scene is a bad experience.
- **Never keep the local MP4** after a successful upload — it's just clutter.
- **Never commit an MP4 unless Track D is triggered.** Committed MP4s bloat the repo history without giving a good PR experience.
- **Never commit a GIF unless Track C is genuinely reached.** Track A′ (release-asset GIF upload) beats a committed GIF whenever it works — the GIF ends up in a release download URL instead of the repo tree, keeping the source clean.
- **Track A′ uses `![]()` markdown, Track A uses a bare URL.** They render through different GitHub paths — bare URLs trigger the `<video>` renderer (user-attachments only), `![]()` triggers the `<img>` renderer (any URL). Swap them and you get a plain hyperlink.
- **Refuse cleanly** if any prereq is missing (Recorder package, gh-attach, browser-session login) — print the exact one-line install/setup command and stop. Only add the Recorder package with explicit permission.
- **Do NOT use `sed` on PR bodies.** Always the temp-file + Edit + `--body-file` pattern. PR bodies routinely contain characters that break shell substitution.
- **Do NOT wrap the user-attachments URL in `![]()`** — for video attachments, the bare URL on its own line is the form GitHub renders inline. Markdown image syntax turns it into an `<img>` that won't play.
- **Do NOT use `using` directives inside execute_code snippets** — CodeDom (the default compiler) rejects them. Fully-qualify types.
- **Do NOT put `PRVideoHolder` / `PRVideoDriver` under `Assets/Editor/`** — they get compiled as Editor-only and Unity refuses to `AddComponent` them at runtime. `Assets/` root, with `#if UNITY_EDITOR` on the Recorder field.
- **Respect the size cap.** 10 MB free / 100 MB paid — the skill doesn't know which the user is on, so treat 10 MB as the hard ceiling for Track A and fall through for larger.
- **Duration cap.** Hard-refuse `> 30` seconds — clips longer than that are (a) way over the attachment limit at 720p, (b) not what reviewers watch. Suggest breaking the demo into multiple PRs if the user pushes back.
