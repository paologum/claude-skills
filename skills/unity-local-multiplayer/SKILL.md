---
name: unity-local-multiplayer
description: Sets up Unity's Multiplayer Play Mode (MPPM) in the current project so the dev can test up to 4 instances at once from a single Editor — ideal for card games like Guandan. Installs the MPPM package, writes a Player Tag-aware bootstrap that auto-starts Host vs Client on Play (detects Mirror or Netcode for GameObjects), and documents the virtual-player setup. Use whenever the user asks to set up local multiplayer testing, run multiple Unity instances, test multiplayer locally, spin up multiple clients, set up MPPM, or test the game without separate machines.
allowed-tools: "Read Write Edit Grep Glob Bash(find . *) Bash(cat *) Bash(grep *) Bash(ls *) Bash(rg *)"
---

## Project context

**Unity version:**
```
!`cat ProjectSettings/ProjectVersion.txt 2>/dev/null | head -2 || echo "NOT A UNITY PROJECT"`
```

**Packages manifest (search for networking + MPPM):**
```
!`grep -E '"(com\.unity\.multiplayer\.playmode|com\.unity\.netcode|mirror|fishnet|photon)"' Packages/manifest.json 2>/dev/null || echo "manifest.json not readable"`
```

**Existing NetworkManager subclasses:**
```
!`grep -rl "NetworkManager" Assets/Scripts 2>/dev/null | head -10`
```

**Existing scenes:**
```
!`find Assets/Scenes -name "*.unity" 2>/dev/null | head -10`
```

## Your task

Set up Multiplayer Play Mode so the user can run up to 4 simultaneous virtual players from a single Editor session, with each player auto-routing to Host or Client at Play time based on its Player Tag.

### Step 1 — verify prerequisites

1. Confirm `ProjectSettings/ProjectVersion.txt` shows Unity **6000.x or higher** (MPPM 1.x+ requires Unity 6). If older, stop and recommend ParrelSync instead with a one-paragraph explanation.
2. Determine the networking stack from `Packages/manifest.json`:
   - `com.mirrornetworking.mirror` → **Mirror** (API: `NetworkManager.singleton.StartHost()`)
   - `com.unity.netcode.gameobjects` → **NGO** (API: `NetworkManager.Singleton.StartHost()`)
   - Neither → tell the user the skill needs a networking lib installed and stop.
3. Identify the project's `NetworkManager` subclass (e.g. `GuandanNetworkManager`) — the bootstrap will look it up via singleton.

### Step 2 — install MPPM

Add to `Packages/manifest.json` under `dependencies`:

```json
"com.unity.multiplayer.playmode": "2.0.0"
```

Use the latest 2.x version. If a `dependencies` block already has the key, leave it untouched. Don't run any package-manager commands — Unity picks up the change when the user reopens the Editor.

### Step 3 — write the bootstrap script

Create `Assets/Scripts/DevTools/MPPMBootstrap.cs`. Use this template, **substituting** the correct networking API based on detection:

```csharp
#if UNITY_EDITOR || UNITY_INCLUDE_TESTS
using UnityEngine;
using UnityEngine.SceneManagement;
#if UNITY_MP_TOOLS_DEV
using Unity.Multiplayer.Playmode;
#endif

// For Mirror:
using Mirror;
// For NGO instead, use: using Unity.Netcode;

/// Bootstraps host/client connection at Play time based on the MPPM Player Tag.
/// Tag "Host" → StartHost(). Anything else → StartClient() to 127.0.0.1.
public static class MPPMBootstrap
{
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void AutoConnect()
    {
#if UNITY_MP_TOOLS_DEV
        var tags = CurrentPlayer.ReadOnlyTags();
        if (tags == null || tags.Length == 0) return;

        // Only auto-connect from the lobby/menu scene to avoid double-starts.
        var scene = SceneManager.GetActiveScene().name;
        if (scene != "MenuScene" && scene != "LobbyScene") return;

        bool isHost = System.Array.Exists(tags, t => t.Equals("Host", System.StringComparison.OrdinalIgnoreCase));

        // Mirror flavor:
        var nm = NetworkManager.singleton;
        if (nm == null) { Debug.LogError("[MPPM] No NetworkManager in scene."); return; }
        if (isHost) { nm.StartHost(); }
        else        { nm.networkAddress = "127.0.0.1"; nm.StartClient(); }

        Debug.Log($"[MPPM] Auto-started as {(isHost ? "Host" : "Client")} (tags: {string.Join(",", tags)})");
#endif
    }
}
#endif
```

Adjustments to make:
- **NGO variant**: replace `using Mirror;` with `using Unity.Netcode;`, swap `NetworkManager.singleton` for `NetworkManager.Singleton`, and use `GetComponent<UnityTransport>().SetConnectionData("127.0.0.1", 7777)` before `StartClient()`.
- **Scene gating**: replace the scene names with the project's actual lobby/menu scene names from the context block above.
- **Port**: if the project uses a non-default port, set it on the transport before `StartClient`.

Wrap the MPPM-specific code in `#if UNITY_MP_TOOLS_DEV` so the file compiles in builds where the package isn't included.

**Handle the host/client startup race.** MPPM launches all virtual players at roughly the same instant, so a client's `StartClient()` often fires *before* the host's `StartHost()` is listening — the client then fails to connect and just sits at the menu. The tag doesn't control ordering; both run their `AutoConnect` in parallel. Two fixes, apply both:

1. **Host starts immediately; clients retry.** Don't assume the host is up. Have clients attempt connection on a short repeating retry until connected (or a timeout), instead of a single `StartClient()`:

```csharp
else
{
    nm.networkAddress = "127.0.0.1";
    // Client: retry until the host is listening (MPPM starts players in parallel).
    static System.Collections.IEnumerator ConnectWithRetry(NetworkManager m)
    {
        for (int i = 0; i < 20 && !NetworkClient.isConnected; i++)
        {
            if (!NetworkClient.active) m.StartClient();
            yield return new UnityEngine.WaitForSeconds(0.5f);
        }
        if (!NetworkClient.isConnected) Debug.LogError("[MPPM] Client gave up connecting to host.");
    }
    // Needs a MonoBehaviour to run the coroutine — see note below.
}
```

Since `MPPMBootstrap` is `static`, spawn a tiny hidden `MonoBehaviour` (`new GameObject("MPPMRunner")` + `DontDestroyOnLoad`) to run the retry coroutine, or convert the bootstrap to a `MonoBehaviour` created at `AfterSceneLoad`. For **NGO**, poll `NetworkManager.Singleton.IsConnectedClient` instead of `NetworkClient.isConnected`.

2. **If "lobby" means a game-level lobby scene, not just a network connection**, connecting is only half of it — after the transport connects, the client must still be *routed into the lobby UI/state*. Auto-connect gets them on the wire; joining the lobby list is your lobby system's join RPC/message. Note this to the user explicitly so they don't expect network auto-connect alone to populate the lobby.

**On "why is host second?"**: sidebar/order in the MPPM window is just Player Tag order and does **not** guarantee host-starts-first at runtime — the retry above is what actually guarantees clients wait for the host. Don't rely on player ordering for correctness.

### Step 4 — tell the user what to do in the Editor

After Unity reimports, output a clear checklist for the user (Claude can't click Editor menus):

1. Open **Window → Multiplayer → Multiplayer Play Mode**.
2. Enable **Player 2, Player 3, Player 4** checkboxes.
3. Set Player Tags:
   - Player 1 (Main Editor): `Host`
   - Player 2 / 3 / 4: `Client` (or `P2`, `P3`, `P4`)
4. Press **Play** in the main Editor. All four virtual players launch, the main Editor calls `StartHost()`, the other three call `StartClient()` to `127.0.0.1`.

### Step 5 — write a short docs page

Add `docs/local-multiplayer.md` (create the `docs/` directory if missing) with:
- 3-sentence overview of MPPM
- The 4-step checklist from Step 4
- A "Troubleshooting" subsection with: "If clients don't connect or don't auto-join the lobby: (1) the host/client startup race is the usual cause — clients start in parallel with the host and must retry until it's listening (the bootstrap does this); (2) confirm the transport port matches the host's and the address is `127.0.0.1`; (3) check the firewall; (4) verify the bootstrap script is in `Assets/Scripts/DevTools/` and the active scene matches the gated scene names; (5) remember network-connect ≠ lobby-join — the client still needs your lobby system's join call after connecting."

Keep the docs page under ~60 lines.

### Output

Report back to the user:
- Files created/modified (paths only)
- The Editor checklist (Step 4)
- A one-sentence note that the project must be reopened for Unity to install the MPPM package
- If the project wasn't a Unity 6 project, what was done instead (or stopped)

Do not run Unity. Do not modify scenes. Do not touch existing NetworkManager subclasses — the bootstrap is additive and gates itself with `RuntimeInitializeOnLoadMethod`.
