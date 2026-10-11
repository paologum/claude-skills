#!/usr/bin/env python3
"""Launch, restart or attach to one worktree's Unity Editor and wait until MCP can use it.

Run with Bash `run_in_background: true`: the harness re-invokes the session the
moment this exits, so a session never guesses an import time, ends its turn on a
timer, or needs the user to say "it's up".

Final stdout line / exit code:
  0  READY <name>@<hash> port=<p> pid=<pid> log=<path>
  3  COMPILE_ERRORS (Safe Mode) ...   errors, the log went idle, MCP never registered
  4  EXITED ...                       the Editor process went away
  5  TIMEOUT ...                      nothing conclusive before --timeout
  2  ERROR ...                        setup problem (no Unity install, not a project)
Compile errors from the latest compile are printed before the final line.
"""
import argparse
import glob
import json
import os
import re
import signal
import subprocess
import sys
import time

STATUS_DIR = os.path.expanduser("~/.unity-mcp")
ERR_RE = re.compile(r"^(?:Assets|Packages)/\S+\(\d+,\d+\): error CS\d+:.*$")
# A new compile starts here; errors before it belong to an earlier compile.
COMPILE_START = "Requested script compilation"
# The bridge rewrites its status file every ~0.5s while the Editor is alive.
FRESH_S = 15


def done(code, line, errors=()):
    for e in list(errors)[:25]:
        print(e)
    print(line, flush=True)
    sys.exit(code)


def editor_binary(project):
    try:
        with open(os.path.join(project, "ProjectSettings", "ProjectVersion.txt")) as f:
            ver = re.search(r"m_EditorVersion:\s*(\S+)", f.read()).group(1)
    except (OSError, AttributeError):
        done(2, f"ERROR no Unity version in {project}/ProjectSettings/ProjectVersion.txt")
    for exe in (f"/Applications/Unity/Hub/Editor/{ver}/Unity.app/Contents/MacOS/Unity",
                os.path.expanduser(f"~/Applications/Unity/Hub/Editor/{ver}/Unity.app/Contents/MacOS/Unity"),
                os.path.expanduser(f"~/Unity/Hub/Editor/{ver}/Editor/Unity")):
        if os.path.exists(exe):
            return exe
    done(2, f"ERROR Unity {ver} is not installed under the Unity Hub paths")


def editors(project):
    """{pid: log_path or None} for interactive Editors on this project (not import workers)."""
    out = subprocess.run(["ps", "-axww", "-o", "pid=,command="], capture_output=True, text=True).stdout
    # ps prints arguments unquoted, so match the raw command line (paths may contain spaces).
    path_re = re.compile(r"-projectpath\s+\"?" + re.escape(project) + r"/?\"?(\s+-|\s*$)", re.I)
    log_re = re.compile(r"-logfile\s+\"?(.+?)\"?(?=\s+-\w|\s*$)", re.I)
    found = {}
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if "Unity" not in cmd or re.search(r"-batchmode|AssetImportWorker", cmd, re.I):
            continue
        if not path_re.search(cmd):
            continue
        m = log_re.search(cmd)
        log = m.group(1) if m else None
        # "-logFile -" logs to stdout; a relative path is relative to Unity's cwd, unknown here.
        found[int(pid)] = log if log and os.path.isabs(log) else None
    return found


def proc_start(pid):
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True).stdout.strip()
        return time.mktime(time.strptime(out, "%a %b %d %H:%M:%S %Y"))
    except (ValueError, OSError):
        return None


def default_log(project, pid):
    """The shared Editor.log, only if this Editor (not another worktree's) wrote it."""
    started = proc_start(pid)
    for p in ("~/Library/Logs/Unity/Editor.log", "~/.config/unity3d/Editor.log"):
        p = os.path.expanduser(p)
        try:
            if started is None or os.path.getmtime(p) < started:
                continue
            with open(p, errors="replace") as f:
                head = f.read(200000)
            # Whole-line match: ".../foo" must not claim ".../foo-2"'s log.
            if re.search(r"^(?:Successfully changed project path to: )?" + re.escape(project) + r"/?$", head, re.M):
                return p
        except OSError:
            continue
    return None


def cpu(pid):
    """Recent CPU %. Linux ps reports a lifetime average, so sample /proc there instead."""
    stat = f"/proc/{pid}/stat"
    if os.path.exists(stat):
        def ticks():
            with open(stat) as f:
                fields = f.read().rsplit(")", 1)[1].split()
            return int(fields[11]) + int(fields[12])  # utime + stime
        try:
            t1 = ticks(); time.sleep(1); t2 = ticks()
            return 100.0 * (t2 - t1) / os.sysconf("SC_CLK_TCK")
        except (OSError, ValueError, IndexError):
            return 0.0
    try:
        return float(subprocess.run(["ps", "-p", str(pid), "-o", "%cpu="], capture_output=True,
                                    text=True).stdout.strip() or 0)
    except ValueError:
        return 0.0


def ready_instance(project, since):
    want = os.path.join(project, "Assets")
    now = time.time()
    for path in glob.glob(os.path.join(STATUS_DIR, "unity-mcp-status-*.json")):
        try:
            mtime = os.path.getmtime(path)
            with open(path) as f:
                st = json.load(f)
        except (OSError, ValueError):
            continue
        if os.path.normpath(st.get("project_path", "")) != want:
            continue
        # Fresh heartbeat = a live Editor; stale files linger for weeks.
        if now - mtime > FRESH_S or mtime < since:
            continue
        if st.get("reloading") or st.get("reason") not in (None, "ready"):
            continue
        h = re.search(r"status-([0-9a-f]+)\.json$", path).group(1)
        return f"{st.get('project_name')}@{h}", st.get("unity_port")
    return None


def latest_errors(log):
    """Errors from the most recent compile in this log (earlier compiles were superseded)."""
    try:
        with open(log, errors="replace") as f:
            text = f.read()
    except (OSError, TypeError):
        return []
    cut = text.rfind(COMPILE_START)
    seen = []
    for line in text[cut if cut >= 0 else 0:].splitlines():
        line = line.strip()
        if ERR_RE.match(line) and line not in seen:
            seen.append(line)
    return seen


def alive(pid, proc):
    if proc is not None and proc.pid == pid:
        return proc.poll() is None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="worktree root (contains Assets/ and ProjectSettings/)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--launch", action="store_true", help="start this worktree's Editor if none is running")
    mode.add_argument("--restart", action="store_true",
                      help="stop this worktree's Editor (only this one), wait for it to exit, launch again")
    ap.add_argument("--log", help="log for a launched Editor (default <project>/Logs/claude-editor.log)")
    ap.add_argument("--timeout", type=int, default=1500, help="seconds (fresh imports take minutes)")
    ap.add_argument("--idle", type=int, default=45,
                    help="seconds of log silence, with compile errors and no MCP, that mean Safe Mode")
    a = ap.parse_args()

    project = os.path.realpath(a.project.rstrip("/"))
    if not os.path.isdir(os.path.join(project, "Assets")):
        done(2, f"ERROR not a Unity project: {project}")
    t0 = time.time()
    proc = None
    running = editors(project)

    if a.restart and running:
        for pid in running:
            os.kill(pid, signal.SIGTERM)
        while any(alive(p, None) for p in running) or editors(project):
            if time.time() - t0 > 120:
                done(4, f"EXITED? Editor pid(s) {list(running)} did not stop within 120s; not relaunching")
            time.sleep(1)
        print(f"STOPPED pid(s)={list(running)}", flush=True)
        running = {}

    if running:
        pid, log = next(iter(running.items()))
        log = log or default_log(project, pid)
        since = 0  # it may have registered before we started watching; freshness still applies
        print(f"ATTACHED pid={pid} log={log}", flush=True)
    elif a.launch or a.restart:
        exe = editor_binary(project)
        log = a.log or os.path.join(project, "Logs", "claude-editor.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        open(log, "w").close()
        since = time.time()  # after any --restart stop, so the old Editor's heartbeats don't count
        proc = subprocess.Popen([exe, "-projectPath", project, "-logFile", log],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        pid = proc.pid
        print(f"LAUNCHED pid={pid} log={log}", flush=True)
    else:
        done(4, f"EXITED no Editor is running for {project} (use --launch)")

    last_size, last_growth = -1, time.time()
    while True:
        inst = ready_instance(project, since)
        if inst:
            done(0, f"READY {inst[0]} port={inst[1]} pid={pid} log={log}")
        if not alive(pid, proc):
            tail = ""
            try:
                with open(log, errors="replace") as f:
                    tail = f.read()[-600:].replace("\n", " | ")
            except (OSError, TypeError):
                pass
            done(4, f"EXITED pid={pid} log tail: {tail}")
        try:
            size = os.path.getsize(log)
        except (OSError, TypeError):
            size = 0
        if size != last_size:
            last_size, last_growth = size, time.time()
        errs = latest_errors(log)
        if errs and time.time() - last_growth > a.idle and cpu(pid) < 5:
            done(3, f"COMPILE_ERRORS (Safe Mode) count={len(errs)} pid={pid} log={log}", errs)
        if time.time() - t0 > a.timeout:
            done(5, f"TIMEOUT after {a.timeout}s without MCP registration pid={pid} log={log}")
        time.sleep(2)


if __name__ == "__main__":
    main()
