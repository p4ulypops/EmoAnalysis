# Emotion Audio Analyser — Reference Guide

A local audio analysis tool for transcribing speech, identifying speakers, and flagging emotional, clinical, and forensic indicators.

This repo is a processing utility. It extracts structure from recordings and writes review-ready outputs. The tool is designed to run on your machine and does not send audio files out by default.

---

## What it does (v3.0 — Omni)

- Transcribes audio from m4a, mp3, wav, ogg, flac files
- Detects speaker turns and optional speaker clusters
- Annotates emotion, pauses, and uncertainty
- Extracts people, places, dates, and times
- Produces JSON and Markdown output for review or automation
- **NEW v3.0**: Full Jefferson paralinguistic markers (all ON by default)
- **NEW v3.0**: Deception indicators (false starts, corrections, stalling, memory disclaimers, defensive language, evasion)
- **NEW v3.0**: Veracity/truthfulness indicators (certainty, sensory detail, temporal sequencing, contextual embedding, cognitive complexity, emotional consistency)
- **NEW v3.0**: Voice dynamics analysis (raised voice, quiet, whisper, sub-vocal, shaky voice) via librosa
- **NEW v3.0**: Clinical markers (PTSD fragmentation, somatic recall, mental defeat, ADHD maze, ASD awkward pauses)
- **NEW v3.0**: Omni output — a single comprehensive `omni.md` file with EVERYTHING
- **NEW v3.0**: Analysis.json — structured data for all indicators
- **NEW v3.0**: Token min-maxing — auto-model selection, cost estimation
- **NEW v3.0**: All features configurable via CLI flags
- **NEW v3.0**: Batch runner (`src/run_batch.sh`) with toggleable options, profiles, fun facts, privacy filtering, and live progress

---

## Quick start

### Repository structure

```
EmotionalVoiceAnalysis/
├── README.md                 ← you are here
├── DASHBOARD_MIDWARE.md      ← middleware architecture guide (in docs/)
├── src/                      ← all scripts
│   ├── run_transcription.py  ← main analysis script
│   ├── run_batch.py           ← dashboard batch runner
│   ├── run_batch.sh           ← legacy batch runner
│   └── viewer/                ← HTML viewer template
├── config/                   ← user-editable config files
│   ├── emotions.json
│   ├── places.json
│   └── wordlists.json
├── plugin/                   ← MCP plugin (server + skill)
│   ├── plugin.json
│   ├── mcp/
│   └── skills/
├── docs/                     ← documentation
│   ├── TECHNICAL.md
│   ├── LLM_CONTEXT.md
│   └── DASHBOARD_MIDWARE.md
└── tests/                    ← test audio + output samples
    ├── README.md
    ├── *.m4a                 ← sample recordings (gitignored)
    └── emotional_range_tests/ ← batch test files (gitignored)
```

### Single file

```bash
python3 src/run_transcription.py /path/to/audio.m4a
```

### Batch processing (all files in a folder)

```bash
python3 src/run_batch.py                           # Default: all features ON, 3 parallel
python3 src/run_batch.py --fast                    # Quick draft (tiny, no extras)
python3 src/run_batch.py --full                    # Everything ON, small model
python3 src/run_batch.py --forensic                # Deception + veracity + clinical
python3 src/run_batch.py --stealth                  # Minimal
python3 src/run_batch.py --dir /path/to/audios      # Custom directory
python3 src/run_batch.py --parallel 4               # 4 simultaneous
python3 src/run_batch.py --model small              # Force model
python3 src/run_batch.py --help                     # All options
```

A folder named after the audio file is created with:
- `transcript.md` — annotated transcript with all inline markers
- `emotions.json` — per-segment emotion, deception, veracity, clinical data
- `things.json` — people, places, dates, times
- `meta.json` — recording metadata, speakers, hashtags, cost estimate
- `glossary.json` — terms with definitions
- `noteworthy.json` — flagged moments (freezes, deception, veracity, clinical, uncertainties)
- `omni.md` — EVERYTHING in one file (all views, all indicators, all markers)
- `analysis.json` — structured deception/veracity/voice/clinical data
- `viewer.html` — interactive HTML viewer (optional)

---

## All CLI Options

### Basic options

| Flag | Default | Description |
|------|---------|-------------|
| `audio` | (required) | Path to audio file (m4a/mp3/wav/ogg/flac) |
| `--model` | `base` | Whisper model: tiny, base, small, medium, large |
| `--auto-model` | off | Auto-select model based on audio duration (token min-maxing) |
| `--language` | `en` | ISO 639-1 language code |
| `--context` | `general` | Context type label for analysis |
| `--output-dir` | current dir | Where to create output folder |
| `--subfolder-suffix` | `_subfile` | Suffix for output subfolder name |
| `--no-copy-audio` | off | Don't copy audio into output folder |
| `--no-viewer` | off | Don't generate HTML viewer |

### Speaker diarization

| Flag | Description |
|------|-------------|
| `--diarise-local` | Local voice clustering via Resemblyzer (no internet, no token) |
| `--diarise` | pyannote.audio diarization (needs HuggingFace token) |
| `--hf-token` | HuggingFace access token for --diarise |
| `--n-speakers` | Expected number of speakers (auto-detected if omitted) |
| `--match-voice` | Match known voice clip to speaker label. Repeatable: `--match-voice clip.m4a Name` |

### Feature toggles (all ON by default)

| Flag | What it disables |
|------|-----------------|
| `--no-jefferson` | Jefferson paralinguistic marker detection |
| `--no-deception` | Deception indicator detection |
| `--no-veracity` | Truthfulness/veracity indicator detection |
| `--no-voice-dynamics` | Voice dynamics analysis (raised voice, whisper, shaky) |
| `--no-clinical` | Clinical marker detection (PTSD/ASD/ADHD) |
| `--no-emotional` | Emotional analysis (affect heuristics) |
| `--no-omni` | Skip omni.md generation |

### Output control

| Flag | Description |
|------|-------------|
| `--omni` | Generate omni.md (default ON) |
| `--estimate-cost` | Print token/cost estimation before running |

---

## Token Min-Maxing

The tool supports automatic model selection based on audio duration:

| Duration | Model | Speed | Accuracy |
|----------|-------|-------|----------|
| 0-10 min | tiny | fastest | draft |
| 0-30 min | base | fast | good |
| 1-60 min | small | medium | better |
| 5-120 min | medium | slow | high |
| 10+ min | large | slowest | best |

Use `--auto-model` to enable automatic selection. Use `--estimate-cost` to see the token count and processing time estimate before running.

**Parallel processing tip**: For batch processing, run multiple files in parallel with different models — use `tiny` for quick drafts, `base` or `small` for final transcriptions. Sub-agents can process different files simultaneously.

---

## Jefferson Paralinguistic Markers (all ON by default)

| Symbol | Phenomenon | Clinical note |
|--------|-----------|---------------|
| `WORD` | Shouting / strong emphasis | Caps = distinctly louder than baseline |
| `°word°` | Whisper / quiet speech | Shame, conspiracy, trauma recall |
| `~word~` | Shaky/crying voice | Diaphragmatic control loss; grief, distress |
| `#word#` | Creaky voice / vocal fry | Low arousal, exhaustion, confidence collapse |
| `word::` | Prolonged sound | Each colon ≈ 0.2s extra duration |
| `↑↑word` | Extreme pitch spike | Panic, shock, dysregulation |
| `↓↓word` | Extreme pitch drop | Resignation, defeat |
| `>word<` | Accelerated delivery | Hurried, rushed — evasion or anxiety |
| `<word>` | Decelerated delivery | Deliberate slowing — careful or deceptive |
| `.hhh` | Sharp inbreath | Shock, trauma trigger, sobbing prep |
| `hhh` | Exhalation | Relief, resignation, emotional release |
| `(.)` | Micropause (0.08-0.2s) | Brief hesitation or natural turn boundary |
| `(0.7)` | Timed pause | Processing, hesitation, or topic shift |
| `(1:04.20)` | Extended pause/freeze | PTSD marker, dissociation, emotional shutdown |
| `=` | Latching (no gap between turns) | Power dynamic, interruption, or urgency |
| `[` | Overlap (simultaneous speech) | Competition for turn, or supportive co-construction |
| `(word)` | Uncertain transcription | Hesitation, cognitive load, or stalling |

---

## Deception Indicators (ON by default)

| Symbol | Type | What it detects |
|--------|------|----------------|
| `<fs>` | False start | Sentence abandoned and redirected |
| `<corrsp>` | Spontaneous correction | Word replaced with alternative |
| `<rep n="N">` | Stalling repetition | Word/phrase repeated 3+ times |
| `<lack-mem>` | Memory disclaimer | Claiming inability to recall |
| `<over-elab>` | Over-elaboration | Excessive precision in casual context |
| `<defensive>` | Defensive language | Pre-emptive denial, rhetorical defence |
| `<contradict>` | Contradiction | Self-correction with contradiction cue |
| `<cog-load>` | Cognitive load | Complex sentences under pressure |
| `<evade>` | Evasion | Topic avoidance, minimising, deflecting |

> ⚠️ Deception indicators are NOT proof of deception. They are heuristic text-pattern matches that *may* indicate cognitive load, rehearsal, or evasive behaviour. Look for clusters, not single indicators. Always consider context.

---

## Veracity / Truthfulness Indicators (ON by default)

| Symbol | Type | What it detects |
|--------|------|----------------|
| `<veracious>` | Qualified certainty | Appropriate confidence, direct experience |
| `<sensory-recall>` | Sensory detail | Multi-sensory recall — genuine memory |
| `<temporal>` | Temporal sequencing | Logical time order — structured recall |
| `<context>` | Contextual embedding | Connected to time/place/setting |
| `<emo-consist>` | Emotional consistency | Emotion matches content and behaviour |
| `<cog-complex>` | Cognitive complexity | Doubt, self-correction, nuance |
| `<spontaneous>` | Spontaneous detail | Unprompted, relevant detail |
| `<recall-pause>` | Appropriate recall pause | Natural processing pause before recall |

---

## Voice Dynamics (ON by default, requires librosa)

| Level | Jefferson | What it means |
|-------|-----------|---------------|
| `raised_voice` | `WORD` | RMS > 1.8x global average — shouting/loud |
| `normal` | — | Normal speaking volume |
| `quiet` | `°word°` | RMS < 0.3x global — quiet speech |
| `whisper` | `°word°` | RMS < 0.1x global — whispered |
| `sub_vocal` | `((murmured))` | Very low energy — sub-vocal/murmured |
| `shaky` | `~word~` | High pitch variability or amplitude instability |

---

## Clinical Markers (ON by default)

| Phenotype | Tag | What it detects |
|-----------|-----|----------------|
| PTSD | `<ptsd-frag type="repetition">` | Repetitive narrative fragments |
| PTSD | `<ptsd-frag type="unfinished">` | Unfinished utterance pattern |
| PTSD | `<somatic>` | Visceral sensory recall |
| PTSD | `<mental-defeat>` | First-person pronoun cluster + hopelessness |
| ADHD | `<meta-correction type="rerail">` | Self-correction back to topic |
| ADHD | `<maze>` | Tangential narrative blocks |
| ASD | `<pause type="awkward">` | Non-grammatical pause |

---

## Omni Output (omni.md)

The omni.md file is a single comprehensive document containing EVERYTHING:

1. Recording Metadata
2. Cost & Token Estimate
3. Entity Register (people, places, dates, times)
4. Speaker Manifest
5. Emotion Timeline (per-segment affect, intensity, distribution)
6. Deception Indicator Matrix (by type, with examples, detail table)
7. Veracity Indicator Matrix (by type, with examples, detail table)
8. Deception vs Veracity Balance (ratio and interpretation)
9. Voice Dynamics Report (level distribution, per-segment detail)
10. Clinical Markers Report (by phenotype, with TEI tags)
11. Jefferson Paralinguistic Markers (all symbols, counts, clinical notes)
12. Environmental Events Log (music, acoustic events, room changes, freezes)
13. Noteworthy Items (grouped by type — freezes, deception, veracity, clinical, entities)
14. Full Annotated Transcript (all inline markers, all indicators per segment)
15. Glossary (all terms with definitions)
16. Configuration Summary (what's ON/OFF)

---

## Install requirements

### Required

```bash
pip3 install openai-whisper librosa soundfile numpy --break-system-packages
brew install ffmpeg
```

### Optional for better speaker separation

```bash
pip3 install resemblyzer scikit-learn --break-system-packages
```

### Optional for advanced diarization

```bash
pip3 install pyannote.audio --break-system-packages
```

---

## Use cases

### Basic transcription (all features ON)

```bash
python3 ./src/run_transcription.py /path/to/audio.m4a
```

### With auto model selection (token min-maxing)

```bash
python3 ./src/run_transcription.py /path/to/audio.m4a --auto-model --estimate-cost
```

### Private speaker clustering

```bash
python3 ./src/run_transcription.py /path/to/audio.m4a --diarise-local
```

### Disable specific features

```bash
python3 ./src/run_transcription.py /path/to/audio.m4a --no-deception --no-veracity
```

### Only emotional analysis, no deception/clinical

```bash
python3 ./src/run_transcription.py /path/to/audio.m4a --no-deception --no-veracity --no-clinical
```

### Name speakers with reference clips

```bash
python3 ./src/run_transcription.py /path/to/audio.m4a \
  --diarise-local \
  --match-voice /clips/reference1.m4a Speaker_01 \
  --match-voice /clips/reference2.m4a Speaker_02
```

### Best speaker diarization

```bash
export HF_TOKEN=hf_yourtoken
python3 ./src/run_transcription.py /path/to/audio.m4a --diarise --hf-token $HF_TOKEN
```

---

## Certainty Scores

All automated annotations carry a `[C:0.00–1.00]` score.

| Range | Meaning | Action |
|-------|---------|--------|
| 0.90–1.00 | High confidence | Trust and archive |
| 0.70–0.89 | Moderate | Spot-check |
| 0.50–0.69 | Low | ⚠️ Verify before citing |
| <0.50 | Speculative | Flag for manual review |

---

## Customization

Edit `config/` files to tune the output without changing code.

### `config/emotions.json`
Add custom emotion patterns and labels.

### `config/places.json`
Add custom location names to recognize.

### `config/wordlists.json`
Extend the glossary with medical, legal, technical, and custom terms.

---

## Privacy

- Whisper runs **entirely on your machine** — audio is never uploaded
- Resemblyzer runs **entirely on your machine** — no internet required
- pyannote downloads a model once on first use, then runs locally
- `wispr_privacy_mode: true` is written into every `meta.json` as a record of this
- Audio files in `DONT_TOUCH_RAW` folders are read-only — the script never modifies source files

---

## Troubleshooting

**"No such file or directory: run_transcription.py"**
Use the full path in quotes: `python3 '/full/path/to/src/run_transcription.py'`

**Transcription is slow**
Normal for long files. Use `--auto-model` or `--model tiny` for a fast draft run first.

**Voice dynamics not working**
Install librosa: `pip3 install librosa soundfile numpy --break-system-packages`

**Speaker clustering puts everyone in one group**
Try `--n-speakers 2` (or however many speakers you know are present).

**ffmpeg not found**
Run: `brew install ffmpeg`

---

## Batch Runner

The batch runner comes in two versions:

### Dashboard mode (`src/run_batch.py`) — recommended

A fixed terminal dashboard with live toggles, dual-mode cards, and 3-level privacy filtering. The screen stays fixed (no vertical scrolling) with four zones:

- **TOP**: Title bar + active config (all toggles) + overall progress bar
- **MIDDLE-LEFT**: Queue of files with per-file progress bars
- **MIDDLE-RIGHT**: Detail cards for the current/last-processed file, switchable between Emotional mode (choice quotes, emotional markers, people found, noteworthy items) and Technical mode (model, tokens, segments, indicator counts, Jefferson markers)
- **BOTTOM**: Menu bar with single-key shortcuts

```bash
python3 src/run_batch.py                           # Default: all ON, 3 parallel
python3 src/run_batch.py --fast                    # Quick draft (tiny, no extras)
python3 src/run_batch.py --full                    # Everything ON, small model
python3 src/run_batch.py --forensic                # Deception + veracity + clinical
python3 src/run_batch.py --stealth                 # Minimal
python3 src/run_batch.py --dir /path/to/audios     # Custom directory
python3 src/run_batch.py --parallel 4              # 4 simultaneous
python3 src/run_batch.py --model small             # Force model
python3 src/run_batch.py --help                    # All options
```

#### Keyboard shortcuts (press key, no Enter needed)

| Key | Action |
|-----|--------|
| `[N]` | Names privacy: cycles REDACTED -> EMOJI -> FULL |
| `[P]` | Numbers privacy: cycles REDACTED -> EMOJI -> FULL |
| `[F]` | Card mode: cycles through 7 modes (see below) |
| `[1]` | Jump to card: Emotional |
| `[2]` | Jump to card: Technical |
| `[3]` | Jump to card: Quotes |
| `[4]` | Jump to card: Batch Stats |
| `[5]` | Jump to card: Micro RAG |
| `[6]` | Jump to card: Event Log |
| `[7]` | Jump to card: Tech Specs |
| `[D]` | Deception: ON/OFF (affects next queued file) |
| `[V]` | Veracity: ON/OFF |
| `[J]` | Jefferson: ON/OFF |
| `[C]` | Clinical: ON/OFF |
| `[⏎]` | Enter: Start processing (does not auto-start by default) |
| `[E]` | Cycle export format (12 Second Brain formats) |
| `[X]` | Export now in selected format |
| `[W]` | Toggle folder watch mode |
| `[↑↓]` | Navigate up/down file list (selects file for card display) |
| `[←→]` | Navigate left/right (previous/next file, updates card display) |
| `[Q]` | Quit gracefully (finish current, stop queuing) |

#### Card modes (middle-right panel, switchable with [F] or [1]-[7])

| # | Mode | What it shows |
|---|------|--------------|
| 1 | Emotional | Choice quotes, emotion distribution, people found, noteworthy items |
| 2 | Technical | Model, tokens, segments, indicator counts, Jefferson markers |
| 3 | Quotes | Key quotes/facts/key points from noteworthy items + high-intensity moments |
| 4 | Batch Stats | Aggregate stats across ALL completed files: totals, emotion distribution, top people |
| 5 | Micro RAG | Cross-file entity index: people/places/topics appearing in multiple files |
| 6 | Event Log | Chronological system log: file started/done/failed, indicator counts found |
| 7 | Tech Specs | System info: Python version, Whisper models, librosa/ffmpeg status, disk space |

#### No auto-start

By default, the dashboard does NOT start processing automatically. It shows the file queue and waits for you to press [Enter]. This lets you review files, adjust settings, and select which file to view before starting. Use `--auto-start` to start immediately.

#### Folder watch mode

Press [W] or use `--watch` to enable folder watching. New .m4a files added to the directory are automatically detected and added to the queue. Useful for processing recordings as they come in.

```bash
python3 src/run_batch.py --watch                # Watch default directory
python3 src/run_batch.py --watch --auto-start   # Watch and start immediately
```

#### Second Brain export (12 formats)

Press [E] to cycle through export formats, then [X] to export. Or use `--export` for auto-export on completion.

| Format | Description |
|--------|-------------|
| Wiki MD | Markdown with [[wiki-links]] — Karpathy-style second brain, bidirectional connections |
| Obsidian | Full Obsidian vault: frontmatter + wiki-links + graph-ready folder structure |
| CSV | Tabular CSV — entities, quotes, indicators as separate files, importable into spreadsheets |
| JSON | Structured JSON — nested blocks, relationships, machine-readable |
| HTML | Web-ready HTML with inline CSS — viewable in any browser |
| SQL | SQL INSERT statements — creates tables for people, places, quotes, indicators |
| OPML | Outline Processor Markup — hierarchical tree, importable to Workflowy/Dynalist |
| Excel | Excel-compatible CSV with summary table (file, duration, indicators, emotions) |
| WordPress | WordPress-ready HTML post with formatting, categories, and tags |
| Substack | Substack-ready Markdown newsletter post with quotes and indicator summary |
| CapCut | CapCut script: timestamped quote cards for video editing |
| Notion | Notion-import-ready Markdown with database tables and relations |

Each export includes a "How Conclusions Were Reached" section explaining the detection methodology for all indicators.

```bash
python3 src/run_batch.py --export wiki_md      # Auto-export as Wiki MD on completion
python3 src/run_batch.py --export obsidian     # Auto-export as Obsidian vault
python3 src/run_batch.py --export csv          # Auto-export as CSV files
```

Export files are saved to `second_brain_export/<format>/`.

#### Privacy modes

| Level | Names | Numbers |
|-------|-------|---------|
| REDACTED | Speaker_XX, [NAME] | [NUM] |
| EMOJI | 🗣️ | 🔢 |
| FULL | Show everything | Show everything |

### Legacy scroll mode (`src/run_batch.sh`)

The original bash-based batch runner with vertical scrolling output. Still available but superseded by the dashboard.

```bash
./src/run_batch.sh --fast
./src/run_batch.sh --forensic --no-clinical
./src/run_batch.sh --help
```

---

## For more technical detail, see `docs/TECHNICAL.md`.
