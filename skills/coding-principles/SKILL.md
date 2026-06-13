---
name: coding-principles
description: A concise, opinionated reference of C# / Unity / general engineering principles to follow when writing or reviewing code (readonly defaults, no-comment-if-code-explains, no LINQ in hot paths, server-authoritative networking, scale-aware design, anti-patterns to refuse). Use when the user asks about coding standards, style guide, best practices, how to write idiomatic C#, or "what rules should I follow here". Loaded automatically by the `coder` agent.
allowed-tools: "Read"
---

# Coding principles

A tight, opinionated standard. The agent (and humans) should apply these without being asked. If a rule conflicts with the user's explicit instruction, the user wins.

---

## 1. C# language idioms

- **`readonly` by default.** Private fields not reassigned post-ctor → `readonly`. Literal constants → `const`. Modifier order: `static readonly`, never the reverse. For value carriers, prefer `record` or `init`-only props.
- **`var` only when the RHS makes the type obvious.** `var users = new List<Player>();` yes. `var x = GetThing();` no — write the type.
- **Switch expressions + pattern matching over if-ladders.** `state switch { Dealing => ..., Playing => ..., _ => ... }`. Use `is { Health: > 0 } p` over null+property checks. `??` / `??=` for null fallbacks.
- **LINQ is for clarity, not hot paths.** No `Where`/`Select`/`ToList` inside `Update`/`FixedUpdate`/`LateUpdate` — allocations stress GC. Outside hot paths, use LINQ idiomatically:
  - `dict.Values` when keys are unused — don't iterate KVPs and remap.
  - `.Any()` over `.Count() > 0`.
  - `list.Count` (property) over `list.Count()` (extension).
  - Project the sequence directly instead of `foreach (var kv in ...) { var v = kv.Value; }`.
- **Public surfaces expose `IReadOnlyList<T>` / `IReadOnlyCollection<T>`.** Never the backing `List<T>`. Mutations go through methods you control.
- **`async` discipline.** Awaiting methods return `Task` / `Task<T>` and end in `Async`. `async void` only for event handlers — anywhere else it eats exceptions. Never `.Result` / `.Wait()` on a `Task`. Library / non-UI: `ConfigureAwait(false)`.
- **`using var` declaration form** over the older block form unless scoping demands it. Every `IDisposable` is disposed on every path.

## 2. Naming, comments, formatting

- **Naming:** `_camelCase` private fields, `PascalCase` public members/types/consts, `camelCase` locals/params, `IPascal` interfaces, `TName` generic params, `XxxAsync` for awaitables.
- **Comment the *why*, never the *what*.** If the code already says it, delete the comment. `// increment i` is noise. `// Mirror serializes SyncList deltas, so we batch mutations here to avoid N RPCs` is signal. **Default to writing no comments.**
- **Method ≤ ~30 lines, one reason to change.** If you'd want a section-header comment inside a method, extract that section into a named method. A method name *is* the best comment.
- **No magic numbers or strings.** Promote to `const`, `enum`, or ScriptableObject. `if (players.Count >= 4)` → `if (players.Count >= MaxPlayers)`.

## 3. Unity gotchas

- **`[SerializeField] private` over `public`** for inspector-edited fields. Encapsulation preserved; inspector still sees them.
- **Cache `GetComponent`, `Camera.main`, `transform`, `Find` in `Awake` / `OnEnable`.** Calling them per-frame is a documented hotspot.
- **No allocations in hot paths.** Avoid in `Update`-tier methods: string `+` / interpolation, boxing (`int` → `object`), `new` instantiations, capturing lambdas (`() => _x` allocates a closure), `params` arrays.
- **`FixedUpdate` for physics, `Update` for input/visuals, events for everything else.** Polling state that an event could fire is the most common LLM mistake.
- **Coroutines for frame-paced Unity work; `UniTask` (not bare `Task`) for async/await in Unity.** Bare `Task` doesn't honor Unity's main thread or PlayerLoop and won't cancel on scene unload.
- **ScriptableObject for shared / tunable config** (rules, deck definitions, table-size presets). Designers edit assets, not code.

## 4. Networking (Mirror / general)

- **Server is the source of truth.** Every gameplay-affecting client action arrives via `[Command]`, is **validated server-side**, and the result is broadcast via `[ClientRpc]` / `SyncVar` / `SyncList`. Never trust client-reported state.
- **Minimize message count and size.** Batch related state into one struct over many SyncVars; raise `syncInterval` for non-critical state; use `[SyncVar(hook=...)]` for change-driven UI rather than polling.
- **`SyncList` mutations are per-op deltas.** Replacing every element each turn floods the network. Mutate in place or `Clear() + AddRange` deliberately.
- **Don't assume ordering between SyncVars and RPCs.** Two SyncVars and an RPC fired together may arrive in any order. Encode causality in the payload.
- **Targeted RPCs over broadcasts** when only one client cares (private hand → `TargetRpc`, not `ClientRpc`).

## 5. Concurrency & async

- **Default to immutability.** Reach for `lock` only on shared mutable state — and lock on `private readonly object _gate = new()`, never `this`, never a type.
- **`Interlocked` for counters; `ConcurrentDictionary` over `lock` + `Dictionary`.** Don't roll your own.
- **`CancellationToken` flows through every async method.** Long-running async work without one is a bug.
- **Never `.Result` / `.Wait()` on Tasks in code that runs on a `SynchronizationContext`** (Unity main thread, UI) — instant deadlock. Async all the way down.

## 6. Think at scale

- **Parameterize counts; don't hardcode.** `MaxPlayers` from `GameConfig` (SO), not `const 4`. Loops and UI derive from it.
- **Know your complexity.** O(n²) on 4 players is free; on 64 it's a frame. If you'd write `players.Any(p => other.Any(...))`, stop — at 4 it's fine, at 8+ rewrite with a dict / hashset.
- **Network payload scales with players.** "Send everyone's hand to everyone" is O(n²) bandwidth. Send the full state to the owner, summaries to others.
- **YAGNI, but don't paint yourself into a corner.** Don't build `IFooFactoryFactory` for two cases. Do put player count behind a `const` / config so 4 → 8 is a one-line change, not a rewrite.

## 7. Anti-patterns to refuse

- **God `GameManager`.** Split by responsibility: `TurnController`, `DealService`, `ScoreTracker`. Singletons are last resort, not default.
- **Premature abstraction.** Minimum two implementations before extracting an interface.
- **Restate-the-code comments.** Delete on sight.
- **`catch (Exception) { }`** or `catch { Debug.Log(e); }` that swallow. Catch specific types; rethrow or fail loudly.
- **Magic numbers / strings / tags inline.** Promote to `const`, `enum`, or SO.
- **Mutable public fields, `List<T>` getters.** Use `IReadOnlyList<T>` + intent-named mutators.
- **Polling where events exist.** A `bool _isReady` checked every frame should be an `event Action Ready`.

---

## When applying these

1. **Read first, edit second.** Open the surrounding file and the call sites before changing anything.
2. **Bug fix ≠ refactor.** A small fix doesn't license a cleanup pass. Stay in scope.
3. **Don't invent error handling.** Internal callers and framework guarantees are trustworthy. Validate at system boundaries (user input, network, external APIs) — nowhere else.
4. **If a rule and the user disagree, the user wins.** Surface the disagreement once, then comply.
