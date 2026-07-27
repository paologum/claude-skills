---
name: mockup-parity-loop
description: The iteration discipline for building a UI screen against a designer-supplied mockup + normative spec. Runs one "measurement round" — capture the build, sample the mockup at the same anchors, compare against the spec's declared values, and report NUMBERS not prose. Enforces the rules that broke the 15-round loop on the Guandan main-menu overhaul into single-digit rounds: replace "visually confirmed" with a sampled pixel or a computed offset every time; distinguish measurable pass ("11px vs spec 15, off by 4") from chirality ("edges at Δy = -30, spec expected +30 → mirrored"); include a chirality check on every rotated element so a mirrored build doesn't pass symmetric measurements. Use whenever the user hands you a mockup image + a spec document and says "match this pixel-for-pixel", "iterate against the mockup", "audit this build against the design", "run the next round", or when a UI PR has visual acceptance criteria and you're about to eyeball it.
allowed-tools: "Bash(git *) Bash(grep *) Bash(find *) Bash(ls *) Bash(awk *) Bash(sed *) Bash(cat *) Bash(head *) Bash(tail *) Bash(wc *) Bash(python3 *) Bash(python *) Read Grep Glob Write Edit"
---

## Context

**Repo root:**
```
!`git rev-parse --show-toplevel 2>/dev/null || pwd`
```

**Mockup image (auto-detect: look for `*mockup*.png|jpg` in docs/design/ or docs/mockups/):**
```
!`find docs/design docs/mockups Assets/Art/design Assets/Design 2>/dev/null -type f \( -name '*mockup*.png' -o -name '*mockup*.jpg' -o -name '*target*.png' \) | head`
```

**Normative spec (auto-detect: look for a `*SPEC*.md` under docs/design/):**
```
!`find docs/design docs/mockups docs 2>/dev/null -type f -name '*SPEC*.md' -o -name '*spec*.md' -maxdepth 3 | head`
```

**Latest build capture (auto-detect: newest PNG under docs/pr-screenshots/):**
```
!`ls -t docs/pr-screenshots/*.png docs/screenshots/*.png 2>/dev/null | head -3`
```

## Task

This skill runs **one measurement round** per invocation. A round is the cheapest unit of iteration: capture the build, sample against the mockup + spec, produce a table of numbers, and hand back to the user for a decision. Do NOT try to "fix" what you find — a round produces a report; the user decides which findings to open and in what order.

The output is always a compact table the reviewer can scan in under a minute. Prose commentary comes after the table, not before. Everything is a number.

### Step 1 — Take the fresh build capture

If the user gave a captured build image, use it. Otherwise drive the app to capture one — Unity via `mcp__UnityMCP__` if the MCP is up, web via a browser tool, native via `screencapture -R`. **The capture must be from THIS turn.** A stale screenshot from an earlier round is the single biggest source of false findings — the user reports a bug, you say fixed, they check the same stale image, another round wasted. Always name captures with a monotonic round tag (`iter-D2.png`, not `menu-still.png`).

### Step 2 — Read the spec sections that name measurable elements

The spec (`MAIN_MENU_SPEC.md`-shaped) declares values per element under §-numbered sections. For each section you're iterating on this round, extract:
- **What is named** (element, hex, dimension, angle, alpha, gap)
- **What the pass condition is** (exact match / within tolerance / sign)
- **What the mockup value should be** (transcribed from the same spec)

If the spec doesn't declare a pass condition for a claim you want to test, that's a spec gap — flag it (`spec §3 doesn't declare a pass condition for X; measurement below is descriptive only`) and continue. Never invent tolerances.

### Step 3 — Sample the same anchor in both build and mockup

For every element with a spec value, pull one pixel or one geometric measurement at the same relative anchor in both images. Cheap, reproducible sample types:

| Sample | Use for | Example |
|---|---|---|
| Hex at a named coordinate | fill colour, felt corners | center `(W/2, H*0.45)` = `#1F5735` |
| Min/max RGB over a 100-px run | grain / stripe presence | `delta=(6,6,8)` means stripe present |
| Bounding box of a component's rect | dimensions, position | `sizeDelta=(120,180)` |
| Perpendicular distance between two edges | gap between elements | `TR of C1 → TL of C2 = +20.8` |
| Δy of two element centres | vertical arrangement | `c2.y − c1.y = +30.5` |
| Composited α reverse-solved from three known channels | opacity | `α = (measured − baseline) / (source − baseline)` |
| Horizontal scan through a rotated element | felt band between rotated cards | `C1[6..126] F[127..161] C2[162..206]` |

For colour samples over unknown baselines, always sample the baseline (the pixel under the element, without the element) first, then compute the composited α — a bare "measured pixel = X" without the baseline is unmeasurable, because you can't back out what changed.

### Step 4 — Add a chirality check for every rotated element

Symmetric measurements (bounding boxes, corner sets, single-axis band widths) **cannot detect a mirror**. The Guandan deco cards passed corner-set verification then failed on visual inspection because the chirality was inverted. Whenever you measure a rotated element, add one asymmetric check that would flip sign under a mirror:

- Δy between element centres (right of the row should sit higher OR lower than left — spec declares which)
- Perpendicular distance TOP vs BOTTOM of two facing edges (splay open at one end, cross at the other — the sign at each end is asymmetric)
- Which corner is highest — `TL.y > TR.y` on a −14° rotation but `TR.y > TL.y` on +14°

Report the sign, not just the magnitude.

### Step 5 — Produce the report

**Format is fixed.** One table per §-section, one row per measurement, four columns:

| Measurement | Build value | Spec target | Verdict |
|---|---|---|---|
| felt center (640, 324) | `#215939` (33, 89, 57) | `#1F5735` (31, 87, 53) | Δ per-ch +2/+2/+4 — PASS |
| TL inset (30, 30) | `#153923` | `#113722` (t≈0.657) | Δ +4/+2/+1 — PASS |
| card 1 right-edge → card 2 left-edge (top) | `+20.8` ref | `≈ +20` | ✓ splay open |
| card 1 right-edge → card 2 left-edge (bot) | `−7.3` ref | `≈ −8` | ✓ crosses (chirality OK) |

Follow with a short paragraph naming which measurements PASSED and which are still OPEN. No adjectives.

### Step 6 — File any residual findings

Open findings ONLY on measurements that failed a spec-declared pass condition. Each finding is one line: `§ + element + measured + expected + failure scenario`. Do not batch commentary; the point is one round = a report the user acts on.

## Rules

- **Every claim is a number.** "Looks about right", "visually confirmed", "close to mockup" are not evidence. Replace them with a sample, a computed offset, or a spec citation. If you can't measure it, the round doesn't cover it — say so.
- **Always sample the baseline.** For any composited element (drop shadow, α overlay, translucent panel), sample the underlying pixel first, then compute the delta. Reporting a raw pixel value without the baseline is meaningless.
- **Chirality check on every rotated element.** Symmetric measurements pass mirrors silently. The Guandan deco cards ate two rounds before this rule was added.
- **Never trust a stale screenshot.** Every round captures fresh, with a monotonic tag. If the user references an "earlier screenshot", surface which round it's from and ask if they want the current state instead.
- **Spec is the source of truth, mockup is the visual check.** When they disagree — and they will, sometimes — report the disagreement as a finding against the SPEC, not against the build. Do not silently substitute the mockup's number for the spec's.
- **Never edit the spec inside a round.** If the spec needs an amendment (footer α `.32 → .50` was one), flag it as a finding and let the user decide. The skill's job is measurement, not adjudication.
- **One round per invocation.** No implicit re-runs, no "let me also check…". The user drives the loop; the skill runs one pass at a time.
- **Report format is fixed.** Table first, prose after. Reviewers scan tables faster than paragraphs, and the table format is what lets the loop converge — round-N's table sits next to round-N-1's table for direct diff.
- **Do not propose fixes in the report.** Findings are detection; fixes are the user's next-turn ask. Mixing them makes rounds bigger and slower.

## Playbook — what to do when the loop stalls

When rounds start repeating (same finding closes-then-reopens two rounds in a row) or the reviewer says "still looks off" without a measurement, one of these is true:

1. **The measurement is missing an axis.** A rotated element's bounding-box check passed but the chirality wasn't measured — add the sign check.
2. **The baseline is wrong.** A composited-α sample used the raw felt colour when the element actually sits over a decoration — resample the baseline underneath.
3. **The spec value is wrong.** The mockup shows one thing; the spec says another; the build matches the spec. Report the disagreement as a spec finding, not a build finding.
4. **Two related findings are being fixed independently.** A rotation-sign fix + a pivot fix are the same bug seen from different angles. Consolidate.

When you notice a stall, name it explicitly in the round's prose ("this is the second round §2 has come back — likely (1) missing chirality check"), so the user has a shortcut to the underlying issue.
