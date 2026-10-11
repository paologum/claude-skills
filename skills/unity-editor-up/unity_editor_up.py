#!/usr/bin/env python3
"""Launch (optionally) and wait for one worktree's Unity Editor to be usable via MCP.

Run it with Bash `run_in_background: true`: the harness re-invokes the session
the moment it exits, so the session never has to guess an import time, end its
turn on a timer, or be told "it's up".

Exit codes / final line:
  0  READY <name>@<hash> port=<p>          MCP registered for this project
  0  READY_WITH_ERRORS <name>@<hash> ...   registered, but scripts have compile errors
  3  COMPILE_ERRORS (Safe Mode likely)     errors, and MCP never registered
  4  EXITED                                the Editor process went away
  5  TIMEOUT                               nothing conclusive before --timeout
  2  usage / setup error
Compile errors are printed (deduplicated, max 25) before the final line.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

STATUS_DIR = os.path.expanduser("~/.unity-mcp")
ERR_RE = re.compile(r"^(?:Assets|Packages)/\S+\(\d+,\d+\): error CS\d+:.*$")


def editor_binary(project):
    with open(os.path.join(project, "ProjectSettings", "ProjectVersion.txt")) as f:
        ver = re.search(r"m_EditorVersion:\s*(\S+)", f.read()).group(1)
    for root in ("/Applications/Unity/Hub/Editor", os.path.expanduser("~/Applications/Unity/Hub/Editor")):
        exe = os.path.join(root, ver, "Unity.app", "Contents", "MacOS", "Unity")
        if os.path.exists(exe):
            return exe
    linux = os.path.expanduser(f"~/Unity/Hub/Editor/{ver}/Editor/Unity")
    if os.path.exists(linux):
        return linux
    sys.exit(f"Unity {ver} not found under the Hub install paths")


def editor_pids(project):
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    pids = []
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if "Unity" in cmd and "-batchmode" not in cmd and re.search(
                r"-projectPath\s+\"?" + re.escape(project) + r"\"?(\s|$)", cmd):
            pids.append(int(pid))
    return pids


def ready_instance(project, since):
    """Status file for this project whose heartbeat is newer than `since`."""
    want = os.path.join(project, "Assets")
    for path in glob.glob(os.path.join(STATUS_DIR, "unity-mcp-status-*.json")):
        try:
            with open(path) as f:
                st = json.load(f)
        except (OSError, ValueError):
            continue
        if os.path.normpath(st.get("project_path", "")) != want:
            continue
        # The bridge rewrites this file on every heartbeat; a file left by an older
        # Editor session keeps an old mtime, so `since` filters it out.
        if os.path.getmtime(path) < since or st.get("reloading"):
            continue
        h = re.search(r"status-([0-9a-f]+)\.json$", path).group(1)
        return f"{st.get('project_name')}@{h}", st.get("unity_port")
    return None


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def new_errors(log, offset):
    try:
        with open(log, errors="replace") as f:
            f.seek(offset)
            text = f.read()
    except OSError:
        return []
    seen = []
    for line in text.splitlines():
        line = line.strip()
        if ERR_RE.match(line) and line not in seen:
            seen.append(line)
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="worktree root (contains Assets/ and ProjectSettings/)")
    ap.add_argument("--launch", action="store_true", help="start this worktree's Editor if none is running")
    ap.add_argument("--log", help="Editor log path (default: <project>/Logs/claude-editor.log)")
    ap.add_argument("--timeout", type=int, default=1500, help="seconds (default 1500; fresh imports take minutes)")
    ap.add_argument("--grace", type=int, default=60,
                    help="seconds to wait for MCP after compile errors appear before calling it Safe Mode")
    a = ap.parse_args()

    project = os.path.realpath(a.project.rstrip("/"))
    if not os.path.isdir(os.path.join(project, "Assets")):
        print(f"not a Unity project: {project}")
        return 2
    log = a.log or os.path.join(project, "Logs", "claude-editor.log")
    t0 = start = time.time()
    pids = editor_pids(project)

    if not pids:
        if not a.launch:
            print(f"EXITED no Editor is running for {project} (pass --launch to start one)")
            return 4
        os.makedirs(os.path.dirname(log), exist_ok=True)
        open(log, "w").close()
        # No -ignorecompilererrors: Unity 6 still stops at the Safe Mode dialog with it,
        # so compile errors are detected from the log instead (see COMPILE_ERRORS).
        proc = subprocess.Popen([editor_binary(project), "-projectPath", project, "-logFile", log],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        pids = [proc.pid]
        offset = 0
        print(f"LAUNCHED pid={proc.pid} log={log}", flush=True)
    else:
        offset = os.path.getsize(log) if os.path.exists(log) else 0
        print(f"ATTACHED pid={pids[0]} log={log if os.path.exists(log) else '(Editor log not under this path)'}", flush=True)
        start = 0  # an already-running Editor may have registered before we started watching

    first_err_at = None
    while True:
        inst = ready_instance(project, start)
        errs = new_errors(log, offset)
        if inst:
            for e in errs[:25]:
                print(e)
            tag = "READY_WITH_ERRORS" if errs else "READY"
            print(f"{tag} {inst[0]} port={inst[1]} pid={pids[0]} log={log}")
            return 0
        if errs and first_err_at is None:
            first_err_at = time.time()
        if first_err_at and time.time() - first_err_at > a.grace:
            for e in errs[:25]:
                print(e)
            print(f"COMPILE_ERRORS (Safe Mode likely) count={len(errs)} pid={pids[0]} log={log}")
            return 3
        if not any(alive(p) for p in pids):
            tail = ""
            try:
                with open(log, errors="replace") as f:
                    tail = f.read()[-600:].replace("\n", " | ")
            except OSError:
                pass
            print(f"EXITED pid={pids[0]} log tail: {tail}")
            return 4
        if time.time() - t0 > a.timeout:
            print(f"TIMEOUT after {a.timeout}s, no MCP registration yet. log={log}")
            return 5
        time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
