---
name: mermaid-check
description: Audits and fixes Mermaid diagrams in PR bodies, READMEs, or raw snippets before they ship. Catches the silent-render-fail bugs that GitHub swallows without an error message — literal `;` inside labels (parses as a statement terminator), unescaped `|` in flowchart edge labels, unbalanced quotes, `<br>` vs `<br/>` vs `\n` in messages, HTML that GitHub's `securityLevel: 'strict'` strips, unregistered participants in `sequenceDiagram`, unbalanced `activate` / `deactivate`, and node/participant IDs with reserved characters. Preserves diagram semantics — only rewrites what would block the render. Use whenever the user asks to check / debug / fix a Mermaid diagram, says a Mermaid block "isn't rendering" or "shows nothing on GitHub", is about to ship a PR body or docs page containing ```mermaid, or asks "why isn't my diagram working".
allowed-tools: "Bash(gh pr view *) Bash(gh pr edit *) Bash(git *) Read Edit Grep Glob WebFetch"
argument-hint: "[PR number | file path | --stdin]"
---

# /mermaid-check

The goal: **never let a broken Mermaid block ship**. GitHub's Mermaid renderer fails silently on parse errors — the code block just goes blank, the reader sees nothing, and the author doesn't notice until someone else opens the PR. This skill catches the specific patterns that trigger that silent failure and rewrites them without changing what the diagram is trying to say.

## When to use

Auto-trigger on any of:
- "check this Mermaid", "why isn't my diagram rendering", "the Mermaid block is blank", "fix this Mermaid".
- The user is drafting a PR body / README / docs page and the text contains a fenced <code>```mermaid</code> block.
- A PR body was just written (via `/pr-description` or otherwise) and includes Mermaid — run this before submitting.

## Inputs

- `<PR number>` — audit every ```mermaid block in `gh pr view <n> --json body` for the current repo. If issues are found, patch them and offer to `gh pr edit --body-file`.
- `<file path>` — audit every ```mermaid block in the file. Patch in place with Edit.
- `--stdin` (or no argument, with a snippet pasted in chat) — audit the pasted snippet, return the fixed version inline.

## What to check (silent-fail patterns first)

These are the ones GitHub renders as an empty block, not an error. Fix them all.

### 1. Semicolons inside labels — the #1 offender

Mermaid treats `;` as a statement terminator equivalent to a newline (all diagram types). A label like `Initialized = true; log persona` parses as two statements: a valid message, then an invalid trailing fragment. The whole block fails.

- **Fix:** replace `;` with `,`, ` — `, `<br/>`, or the escape entity `#59;`. Choose whichever preserves the author's intent (if the `;` was a visual "and then" separator, `,` is fine; if they wanted a real line break, use `<br/>`).
- **Docs:** https://mermaid.js.org/syntax/sequenceDiagram.html#entity-codes-to-escape-characters (the entity-codes section is not sequence-diagram-specific — the same escapes work in flowchart / classDiagram / stateDiagram labels).

### 2. `|` inside flowchart edge labels

`A -->|label with | in it| B` breaks because `|` is the label delimiter.
- **Fix:** wrap the label in quotes — `A -->|"a | b"| B` — or escape with `#124;`.

### 3. Unbalanced quotes or brackets in labels

`A["some "quoted" thing"]` — the inner quotes close the label early. Same story for `(`, `[`, `{` inside a `[label]`.
- **Fix:** use HTML entities: `#quot;` for `"`, `#40;` `#41;` for parens.

### 4. `<br>` vs `<br/>`

`<br/>` (self-closing) is the officially supported line-break token in Mermaid labels and works under GitHub's `securityLevel: 'strict'`. `<br>` (unclosed) fails on some parser versions.
- **Fix:** always write `<br/>`.

### 5. HTML tags that GitHub sanitizes

GitHub's Mermaid runs with `securityLevel: 'strict'`. Tags like `<span>`, `<img>`, `<a href=…>` inside labels are stripped or cause the block to render as raw text.
- **Fix:** remove the HTML; use plain text or `#tag` entities. If the user needs styling, tell them GitHub doesn't render it — offer to drop it.

### 6. `sequenceDiagram`: message to an undeclared participant

`SM->>SDX: …` where `SDX` was never declared (typo of `SDK`) is auto-created by Mermaid but with the raw ID as the visible name — not always a hard fail, but often the "why does one lane show `SDX` instead of `Steamworks.NET SDK`?" complaint.
- **Fix:** confirm every participant on the right side of an arrow appears in a `participant … as …` declaration up top.

### 7. `sequenceDiagram`: unbalanced `activate` / `deactivate`

Every `activate X` needs a `deactivate X` (or the trailing `-x`/`--x` return arrow, which auto-deactivates). Unbalanced pairs silently drop the activation bar or fail the render on stricter parsers.

### 8. `flowchart`: node IDs with reserved characters

Node IDs are identifiers, not labels. `flowchart TD` then `Player launches --> B` fails because `Player launches` isn't a valid ID. This is the "I typed the label where the ID goes" mistake.
- **Fix:** `A[Player launches] --> B`.

### 9. `graph` vs `flowchart`

Both parse; `flowchart` is the current keyword. Not a break — but if you're upgrading a diagram, `flowchart TD` is preferred over `graph TD`.

### 10. Direction token typos

`sequenceDiagram` doesn't take a direction. `flowchart` takes `TD` / `LR` / `BT` / `RL` — anything else silently falls back and often confuses readers who expected the layout they typed.

## How to apply the fix

### Case A: `<PR number>`

```
!`gh pr view $ARGUMENTS --json body -q .body > /tmp/mermaid-check-$$.md`
```

1. Extract every ```mermaid block. If there are none, tell the user and stop.
2. For each block, run through the checklist above. Track edits per-block.
3. Show the user a diff of what you'd change and **ask before pushing**. Per this repo's convention, PR body edits are visible external actions and need explicit approval each time.
4. On approval: `gh pr edit <n> --body-file /tmp/mermaid-check-$$.md`.
5. Rebuild the URL and hand it back.

### Case B: `<file path>`

Same, but write changes with Edit and don't push. Print the diff and note the file was updated.

### Case C: `--stdin`

Return the fixed block inline in chat, with a **one-line explanation per fix** (not a lecture — just "line 12: `;` → `,` (statement terminator)"). Don't dump the whole checklist.

## Output

Format is always the same three sections, in this order:

1. **Findings** — bulleted list of concrete issues found, one per line, in `line N: <what> — <why it breaks>` form. If none, say `No issues found.` and stop.
2. **Corrected diagram** — the fixed ```mermaid block(s), unchanged where nothing was wrong.
3. **References** — canonical Mermaid docs for each pattern you fixed (link, not summary).

## Never

- Never change diagram semantics to make a fix easier. If the author's `;` really meant "two things happen in one step" and you can't preserve that with `,` or `<br/>`, ask.
- Never invent Mermaid syntax. If unsure, WebFetch `https://mermaid.js.org/syntax/<diagramType>.html` and quote the relevant section back.
- Never claim a diagram renders without verifying — GitHub's silent-fail mode means "looks fine to me" is not evidence. If the user hasn't loaded the PR body in a browser, tell them to.
- Never touch anything outside the ```mermaid fence. Preserve surrounding prose byte-for-byte.

## Escape entity cheat sheet

Common characters that need escaping inside labels:

| Character | Entity |
|---|---|
| `;` | `#59;` |
| `\|` | `#124;` |
| `"` | `#quot;` |
| `(` | `#40;` |
| `)` | `#41;` |
| `[` | `#91;` |
| `]` | `#93;` |
| `<` | `#lt;` |
| `>` | `#gt;` |
| `&` | `#amp;` |

Source: https://mermaid.js.org/syntax/flowchart.html#entity-codes-to-escape-characters
