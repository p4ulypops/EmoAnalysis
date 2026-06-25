# Terminal Dashboard Middleware — Architecture & Integration Guide

> **What this is:** A vendor-neutral, project-agnostic reference for building a fixed terminal dashboard that acts as middleware between a processing backend and a frontend UI. It captures the logic, patterns, and conventions proven in the Emotion Audio Analyser batch runner and generalises them for any project that needs live monitoring, toggleable options, and multi-format export.

---

## 1. What Is This?

This is **middleware** — it sits between two systems:

```
┌──────────────────┐      ┌─────────────────────┐      ┌──────────────────┐
│  Processing       │      │  Terminal Dashboard │      │  Frontend UI     │
│  Backend          │ ←──→ │  (Middleware)       │ ←──→ │  (future / API)  │
│  (workers,        │      │                     │      │  (web, desktop,  │
│   scripts, APIs)  │      │  - live status      │      │   mobile)        │
│                   │      │  - toggles          │      │                  │
└──────────────────┘      │  - exports          │      └──────────────────┘
                          │  - privacy filter   │
                          │  - keyboard control │
                          └─────────────────────┘
```

The dashboard:
- Reads state from the backend (process status, output files, metrics)
- Displays it in a fixed terminal layout (no scrolling)
- Lets the user toggle options live via single-key presses
- Exports aggregated data in multiple formats
- Is designed so a proper frontend (web/desktop/mobile) can be built on top of the same state model

---

## 2. Dashboard Layout — Four-Zone Fixed Display

The screen never scrolls. It uses ANSI cursor control to overwrite the same regions each refresh cycle (~300ms).

```
┌──────────────────────────────────────────────────────────────────────┐
│  TOP: Title bar + active config + overall progress                    │  ← rows 1-6
├──────────────────────────────────┬───────────────────────────────────┤
│                                  │                                   │
│  MIDDLE-LEFT: Queue / watcher    │  MIDDLE-RIGHT: Detail cards       │  ← rows 7 to N-4
│  - file/item list                │  - switchable views (see below)    │
│  - per-item progress bars        │  - updates on item selection       │
│  - status icons                  │  - privacy-filtered               │
│  - selected item highlighted ▶   │                                   │
│                                  │                                   │
├──────────────────────────────────┴───────────────────────────────────┤
│  BOTTOM: Menu bar with keyboard shortcuts                             │  ← rows N-3 to N
└──────────────────────────────────────────────────────────────────────┘
```

### Zone responsibilities

| Zone | Purpose | Refresh rate |
|------|---------|-------------|
| TOP | Title, all active toggles, overall progress bar, elapsed time | Every cycle |
| MIDDLE-LEFT | Item queue with status icons, progress bars, highlighted selected row | Every cycle |
| MIDDLE-RIGHT | Detail cards for the selected item — switchable between N modes | Every cycle |
| BOTTOM | Menu bar showing all keyboard shortcuts and their current state | Every cycle |

### Queue status icons

Each item in the queue displays one of five states:

| Icon | State | When |
|------|-------|------|
| `⬚` hollow | Pending — not started | Before the user presses Enter |
| `⏸` pause | Queued — waiting to run | After Enter; processing active but this item not yet started |
| `▓` filled block | Running — in progress | Currently being processed |
| `✓` tick | Done | Completed successfully |
| `✗` cross | Failed | Errored — can be requeued |

The selected row is highlighted with a cyan bold `►` prefix and bold item name. All other rows are unstyled. This makes the current selection immediately visible without a separate cursor line.

---

## 3. Keyboard Shortcuts — Reference Design

All shortcuts are single-key presses (no Enter needed). Arrow keys use escape sequence reading.

### Navigation

| Key | Action | Notes |
|-----|--------|-------|
| `↑` / `↓` | Navigate up/down the queue | Highlights row with `►` + bold name, updates right panel |
| `Space` | Cycle card modes for selected item | Cycles right panel view (wraps last → first) |
| `1`-`7` | Jump directly to card mode N | Instant switch, no cycling needed |
| `F` | Cycle through all card modes | Same as Space — useful when a key press feels more explicit |

> **Note:** Left/right arrow keys are reserved for queue-only navigation. Do not bind them to card mode or other actions — they map to the same up/down queue navigation and are present only for ergonomic reach.

### Processing control

| Key | Action | Notes |
|-----|--------|-------|
| `Enter` | Start processing | Does NOT auto-start by default — lets user review first |
| `Q` | Quit gracefully | Finishes current items, stops queuing new ones |

### Toggleable options (affect next queued item)

| Key | What it toggles | Pattern |
|-----|-----------------|---------|
| `D` | Deception/analysis layer | ON/OFF |
| `V` | Veracity/truthfulness layer | ON/OFF |
| `J` | Jefferson/notation layer | ON/OFF |
| `C` | Clinical/marker layer | ON/OFF |
| `E` | Export format | Cycles through 12 formats + OFF |
| `X` | Export now | Triggers immediate export in selected format |
| `W` | Folder watch mode | ON/OFF — monitors directory for new files |

### Privacy control (3-level cycle)

| Key | What it controls | Level 0 | Level 1 | Level 2 |
|-----|------------------|---------|---------|---------|
| `N` | Names / personal identifiers | REDACTED → `Speaker_XX`, `[NAME]` | EMOJI → 🗣️ | FULL → show real names |
| `P` | Numbers / figures | REDACTED → `[NUM]` | EMOJI → 🔢 | FULL → show real numbers |

> **Important:** Privacy settings apply **globally** across all card views. If names are set to REDACTED, they're redacted everywhere — in the queue, in the cards, in the event log, everywhere. The actual output files on disk always contain full unfiltered data.

---

## 4. Card Modes (Middle-Right Panel)

The right panel is switchable between multiple "card modes." Each shows a different view of the selected item's data. Press `F` to cycle or `1`-`7` to jump.

### Design pattern for card modes

Each card mode should:
1. Have a clear title with an emoji
2. Show 4-8 rows of relevant data
3. Respect global privacy settings (names, numbers filtered)
4. Update live as new data comes in
5. Gracefully handle "no data yet" states

### Reference card modes

| # | Mode | Emoji | What it shows | Explainer |
|---|------|-------|--------------|-----------|
| 1 | Emotional | 😊 | Choice quotes, emotion distribution, people found, noteworthy items | Human-readable emotional analysis — what was felt, by whom, when |
| 2 | Technical | ⚙️ | Model, tokens, segments, indicator counts, marker summary | Machine-level stats — what was processed, how, and what was found |
| 3 | Quotes | 📌 | Key quotes/facts/key points from noteworthy items + high-intensity moments | The "if you only read one thing" view — the most important findings |
| 4 | Batch Stats | 📊 | Aggregate stats across ALL completed items: totals, distributions, top entities | Cross-item analysis — patterns that only emerge when looking at everything together |
| 5 | Micro RAG | 🔎 | Cross-item entity index: people/places/topics appearing in multiple items | Pseudo-RAG — a mini knowledge graph showing connections between items |
| 6 | Event Log | 📋 | Chronological system log with timestamps: started, done, failed, indicators found | Audit trail — what happened, when, in what order |
| 7 | Tech Specs | 🔧 | System info: runtime version, available models, dependencies, disk space | Environment — what's installed, what's available, what's missing |

### Adding your own card modes

To add a new card mode to your project:

1. Add it to the `card_mode_label()` list in your state class
2. Add a new `elif STATE.card_mode == N:` block in the render function
3. Follow the pattern: title → data rows → graceful empty state
4. Update the keyboard shortcut range (e.g. `1`-`8` if you add an 8th)
5. Document it in your README

---

## 5. No Auto-Start — Review Before Running

By default, the dashboard does NOT start processing when launched. It:
1. Scans the directory for items
2. Displays the queue with all items pending
3. Shows "Press [Enter] to start" in the queue header
4. Waits

This lets the user:
- Review which items will be processed
- Adjust toggle settings (deception, veracity, model, etc.)
- Navigate the list with arrow keys
- Select which item to view in the right panel
- Enable watch mode or set export format

Only when the user presses `Enter` does processing begin.

To auto-start (for CI/CD or unattended runs), pass `--auto-start` as a CLI flag.

---

## 6. Folder Watch Mode

When enabled (`--watch` or press `W`):
- The dashboard monitors the target directory at regular intervals (~3 seconds)
- New files matching the target pattern (e.g. `*.m4a`) are automatically:
  - Scanned for metadata (duration, size)
  - Added to the queue as "pending"
  - Logged in the Event Log card
- Processing starts automatically if the system is already running
- If not yet started, new files are queued but wait for `Enter`

Use cases:
- Processing recordings as they arrive (e.g. voice memos synced from phone)
- Watching a shared drop folder
- Continuous ingestion pipeline

---

## 7. Second Brain / Multi-Format Export

The dashboard can export all completed item data in multiple formats. This is inspired by Karpathy's second brain concept — bidirectional links between entities, quotes, and items.

### How it works

1. Press `E` to cycle through available export formats
2. Press `X` to export now in the selected format
3. Or use `--export <format>` for auto-export on batch completion
4. Exports go to `second_brain_export/<format>/`

### Available formats (reference set — adapt to your project)

| Format | Extension | Description |
|--------|-----------|-------------|
| 📝 Wiki MD | `.md` | Markdown with `[[wiki-links]]` — bidirectional connections, Karpathy-style. Each entity (person, place, topic) gets its own page. Links between items create a knowledge graph. |
| 🏠 Obsidian | `.md` (folder) | Full Obsidian vault: YAML frontmatter + wiki-links + folder structure (`people/`, `places/`, `attachments/`). Ready to open in Obsidian with graph view. |
| 📊 CSV | `.csv` | Tabular — one row per entity/quote/indicator. Multiple files: `entities.csv`, `quotes.csv`, `indicators.csv`. Importable into Excel, Google Sheets, or any database. |
| 🔧 JSON | `.json` | Structured, machine-readable. Nested blocks, relationships, full metadata. The interchange format for APIs and programmatic consumption. |
| 🌐 HTML | `.html` | Web-ready with inline CSS. Viewable in any browser without a server. Good for sharing read-only snapshots. |
| 🗄 SQL | `.sql` | SQL INSERT statements. Creates proper tables (`files`, `people`, `quotes`, `indicators`). Importable into SQLite, PostgreSQL, MySQL. |
| 📋 OPML | `.opml` | Outline Processor Markup Language. Hierarchical tree structure. Importable into Workflowy, Dynalist, Roam Research. |
| 📈 Excel | `.csv` | Excel-optimised CSV with summary table. One row per item showing all key metrics. Opens directly in Excel with proper columns. |
| 🌍 WordPress | `.html` | WordPress-ready HTML post. Includes categories and tags as HTML comments. Copy-paste into WordPress editor. |
| 📧 Substack | `.md` | Substack-ready Markdown newsletter. Sections per item, quotes formatted as blockquotes, indicator summary. |
| 🎬 CapCut | `.txt` | CapCut script: timestamped quote cards for video editing. Each quote has a timestamp, emoji, and affect label. |
| 📐 Notion | `.md` | Notion-import-ready Markdown with database tables. Each item is a row with columns for all key metrics. |

### "How Conclusions Were Reached" section

Every export includes a methodology section explaining how each indicator was detected. This is critical for:
- **Transparency:** users understand why something was flagged
- **Auditability:** reviewers can trace back from a conclusion to its detection method
- **Trust:** users know the system uses heuristic text-pattern matching, not magic

Example structure:
```markdown
## How Conclusions Were Reached

Each indicator above was detected via:
- **Deception**: text pattern matching for false starts, corrections, stalling repetitions,
  memory disclaimers, defensive language, evasion
- **Veracity**: text pattern matching for qualified certainty, sensory detail, temporal
  sequencing, contextual embedding, cognitive complexity
- **Clinical**: text pattern matching for PTSD fragmentation, somatic recall, ADHD maze
  blocks, ASD awkward pauses
- **Freeze events**: silence >10s between segments
- Certainty scores range from 0.00 to 1.00 — below 0.70 should be manually verified
```

### Adaptting exports to your project

Each project will have different entities and indicators. The export functions should:
1. Pull from the same `result` data structure that the card modes use
2. Include all entities, quotes, and indicators found
3. Include the methodology section
4. Support cross-item linking (e.g. when the same person appears in multiple files)

---

## 8. Middleware Architecture

The dashboard is designed as middleware — it sits between a processing backend and a future frontend UI.

### State model (shared between backend and frontend)

```python
class BatchState:
    # Item queue
    files: list          # each: {path, name, duration, status, pid, result, ...}

    # Processing control
    started: bool        # has the user pressed Enter?
    quit_requested: bool # has the user pressed Q?
    max_parallel: int    # max simultaneous processes
    watch_mode: bool     # monitoring directory for new files?

    # Feature toggles (all ON by default)
    deception: bool
    veracity: bool
    jefferson: bool
    clinical: bool
    voice_dynamics: bool
    emotional: bool
    omni: bool
    viewer: bool

    # Privacy (0=REDACTED, 1=EMOJI, 2=FULL)
    name_privacy: int
    num_privacy: int

    # Display
    card_mode: int       # 0-6 (which right-panel view)
    selected_file_idx: int

    # Aggregated data
    batch_stats: dict    # cross-item statistics
    micro_rag: dict      # cross-item entity index
    event_log: list      # chronological events

    # Export
    export_format: int   # 0=none, 1-12=formats
```

### Frontend integration path

The state model above is serialisable to JSON. A future frontend can:

1. **Read state** via a JSON API endpoint (poll or WebSocket)
2. **Send commands** via keyboard shortcut equivalents (REST endpoints: `POST /toggle/deception`, `POST /start`, etc.)
3. **Receive exports** via the same export system (frontend calls `GET /export?format=obsidian`)
4. **Display** the same four-zone layout in a web/desktop UI

The terminal dashboard is the reference implementation. The frontend is the polished version.

### Backend integration path

The backend (processing workers) communicates via:
1. **Subprocess management** — workers are spawned as child processes
2. **File-based state** — workers write output files to disk, dashboard reads them
3. **Exit codes** — 0=success, non-zero=failure
4. **stdout** — workers print progress lines, dashboard filters and displays them

This file-based communication means any script in any language can be a backend worker — it just needs to write output files in the expected structure.

---

## 9. Terminal Rendering — Technical Notes

### ANSI cursor control

The dashboard uses these ANSI escape codes:
- `\033[H` — move cursor to home (top-left)
- `\033[2J` — clear screen
- `\033[2K` — clear current line
- `\033[R;CH` — move cursor to row R, column C
- `\033[?25l` / `\033[?25h` — hide/show cursor
- `\033[s` / `\033[u` — save/restore cursor position

### Non-blocking keyboard input

The dashboard uses `select()` on stdin with a 0-second timeout to read keypresses without blocking the render loop. Arrow keys are read as 3-byte escape sequences.

**Terminal compatibility:** Different terminals send different escape sequences for arrow keys. Always handle both:
- Normal cursor mode: `\x1b[A` (up), `\x1b[B` (down), `\x1b[C` (right), `\x1b[D` (left)
- Application cursor mode: `\x1bOA`, `\x1bOB`, `\x1bOC`, `\x1bOD` (sent by Terminal.app and others)

In the escape sequence reader, treat `ch2 == 'O'` identically to `ch2 == '['` — both lead to the same final character (`A`/`B`/`C`/`D`) and should map to the same actions.

### Raw terminal mode

`tty.setcbreak()` puts the terminal in cbreak mode — keys are delivered immediately without waiting for Enter, and no echo. Original terminal settings are restored on exit.

### Refresh cycle

The main loop runs at ~300ms intervals:
1. Check for completed processes
2. Check watch directory (if enabled)
3. Start new processes (if started and under parallel limit)
4. Read keypress
5. Render dashboard
6. Sleep 300ms

---

## 10. README Strategy

Every project using this dashboard pattern should maintain a README with:

1. **Quick start** — one command to run, one command for help
2. **All CLI flags** — documented in a table with defaults
3. **All keyboard shortcuts** — documented in a table, grouped by category
4. **All card modes** — documented with what each shows
5. **All export formats** — documented with description and use case
6. **Privacy modes** — documented with all three levels
7. **Profiles** — preset combinations documented
8. **Middleware note** — explain that this is middleware, not a final product
9. **Frontend integration** — document the state model for future UI developers
10. **Examples** — copy-pasteable commands for common use cases

### README style guidelines

- Use emoji in headers and tables (📝 📊 🔍 📌 🔧 🏠 🌐 🗄) but don't overdo it
- Write for both technical and non-technical readers — explain jargon
- Use tables for structured data (flags, shortcuts, modes)
- Use code blocks for commands and examples
- Include "what this does" plain-English summaries
- Keep sections short — one concept per section
- Cross-reference between sections (e.g. "see Card Modes above")

---

## 11. Adaptation Checklist

When applying this pattern to a new project:

- [ ] Define your "items" (files, tasks, jobs, recordings — whatever your backend processes)
- [ ] Define your feature toggles (what can be turned on/off)
- [ ] Define your card modes (what views are useful for your data)
- [ ] Define your export formats (what formats your users need)
- [ ] Define your privacy concerns (what needs filtering)
- [ ] Define your entity types (people, places, topics — what gets cross-referenced)
- [ ] Implement the four-zone layout (top, middle-left, middle-right, bottom)
- [ ] Implement non-blocking keyboard input
- [ ] Implement the state model
- [ ] Implement subprocess management for your workers
- [ ] Implement file-based result loading
- [ ] Implement batch stats aggregation
- [ ] Implement micro RAG (cross-item entity index)
- [ ] Implement event logging
- [ ] Implement the "How Conclusions Were Reached" methodology section
- [ ] Document everything in the README
- [ ] Document the frontend integration path (state model as JSON)

---

_This document is project-agnostic. It captures the logic, not the implementation. Adapt freely._
