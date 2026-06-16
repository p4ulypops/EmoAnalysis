# LLM_CONTEXT — Emotion Audio Analyser v2.1

This file describes the tool's purpose, CLI interface, all output schemas, config format,
and notation systems. Load this file as context before helping a user with this tool.

---

## Tool Purpose

`run_transcription.py` is a local audio transcription and emotional analysis tool.
It takes an audio recording (m4a, mp3, wav) and produces a structured output folder containing:
- A verbatim timestamped transcript with inline glossary references
- Emotional intensity scores per utterance
- Named entity extraction (people, places, dates, times)
- Glossary of domain-specific terms found in speech
- Metadata about the recording
- Noteworthy flagged moments (emotional freezes, room events, uncertainties)

All processing is local. No audio or transcript data is sent externally.
Schema: Affective-Clinical-MD v2.6 (Jefferson + TEI + CHAT notation).

---

## CLI Invocation

```
python3 '/path/to/run_transcription.py' AUDIO_PATH [OPTIONS]
```

### Arguments

```
AUDIO_PATH              Required. Path to audio file. Supports: m4a mp3 wav ogg flac aiff
--model MODEL           Whisper model. Values: tiny|base|small|medium|large. Default: base
--language LANG         ISO 639-1 code. Default: en. Examples: fr de pl he ar
--context LABEL         Free-text label stored in meta.json. Default: general
--output-dir PATH       Directory for output folder. Default: current working directory
--diarise-local         Enable local speaker clustering (Resemblyzer). Mutually exclusive with --diarise
--diarise               Enable pyannote.audio diarization. Requires --hf-token or HF_TOKEN env var
--hf-token TOKEN        HuggingFace access token for --diarise
--n-speakers N          Integer hint for expected speaker count. Optional. Auto-detected if omitted.
--match-voice PATH NAME Match a known voice clip (PATH) to a speaker label (NAME).
                        Repeatable for multiple speakers.
                        Requires --diarise or --diarise-local.
```

### Example invocations

```bash
# Minimal
python3 run_transcription.py audio.m4a

# Local diarization
python3 run_transcription.py audio.m4a --diarise-local --n-speakers 2

# Full
python3 run_transcription.py audio.m4a \
  --model small --language en --context care-advocacy \
  --diarise-local --n-speakers 3 \
  --match-voice ref_pauly.m4a Pauly \
  --output-dir ~/Transcripts
```

---

## Output Structure

```
<audio_stem>/
├── transcript.md       Verbatim transcript with timings, speaker turns, [G:N] glossary refs
├── emotions.json       Per-segment emotion data, pauses, freeze events
├── things.json         Named entities: people, places, dates, times
├── meta.json           Recording metadata, diarization info, hashtags
├── glossary.json       Domain terms found in speech, with definitions
└── noteworthy.json     Flagged moments requiring human review
```

---

## JSON Schemas

### emotions.json

```json
{
  "total_segments": 423,
  "freeze_events": [
    {
      "timestamp": "17:12",
      "duration_s": 13.49,
      "type": "extended_freeze",
      "certainty": 0.90,
      "note": "🚨 >10s silence — probable emotional freeze"
    }
  ],
  "significant_pauses": [
    {
      "timestamp": "05:32",
      "duration_s": 6.2,
      "type": "significant",
      "certainty": 0.88
    }
  ],
  "environmental_events": [
    {
      "timestamp": "00:03:41.00",
      "type": "music/radio/TV",
      "duration_s": 12.3,
      "certainty": 0.61
    }
  ],
  "segments": [
    {
      "index": 0,
      "timestamp": "00:00",
      "start_s": 0.0,
      "end_s": 3.2,
      "speaker": "Speaker_01",
      "text_preview": "First 100 chars of utterance…",
      "pause_before_s": 0.0,
      "intensity": 5,
      "emoji": "😐",
      "affect_label": "Neutral",
      "has_raised_voice": false,
      "has_question": false,
      "jefferson_markers": [],
      "certainty": 0.65
    }
  ]
}
```

### things.json

```json
{
  "people": [
    {
      "name": "Pauly",
      "certainty": 0.95,
      "occurrences": 14,
      "source": "known_speaker"
    },
    {
      "name": "Sharon",
      "certainty": 0.62,
      "occurrences": 3,
      "source": "heuristic",
      "flag": "⚠️ verify"
    }
  ],
  "places": [
    { "place": "Barnet Hospital", "certainty": 0.70, "occurrences": 2 }
  ],
  "dates": [
    { "value": "last Tuesday", "type": "relative", "certainty": 0.88 },
    { "value": "06/11/2025", "type": "absolute", "certainty": 0.88 }
  ],
  "times": [
    { "value": "2pm", "certainty": 0.85 }
  ]
}
```

### meta.json

```json
{
  "audio_file": "Voice Memo - 2025-11-06.m4a",
  "audio_path": "/full/path/to/file.m4a",
  "duration_s": 1234.5,
  "duration_formatted": "20:34",
  "transcription_timestamp": "2026-06-16T10:23:00Z",
  "whisper_model": "base",
  "language": "en",
  "context_type": "general",
  "schema_version": "Affective-Clinical-MD-v2.6",
  "wispr_privacy_mode": true,
  "diarization": {
    "method": "Resemblyzer local clustering (no internet)",
    "n_speakers_detected": 2,
    "speaker_labels": ["Speaker_01", "Speaker_02"],
    "voice_matching": [
      {
        "reference_name": "Pauly",
        "reference_file": "/path/to/ref.m4a",
        "best_match_speaker": "Speaker_01",
        "renamed_to": "Pauly",
        "similarity_score": 0.823,
        "certainty": 0.82,
        "all_similarities": { "Speaker_01": 0.823, "Speaker_02": 0.412 },
        "note": "similarity >0.60 = confident match"
      }
    ],
    "note": "Speaker labels are discovered automatically — names are not assumed."
  },
  "segment_count": 423,
  "word_count": 5821,
  "hashtags": ["#general", "#Pauly", "#NHS", "#mental_health"],
  "output_folder": "/path/to/output/folder",
  "output_files": ["transcript.md","emotions.json","things.json","meta.json","glossary.json","noteworthy.json"]
}
```

### glossary.json

```json
{
  "entries": [
    {
      "id": 1,
      "term": "PIP",
      "category": "benefit/legal",
      "definition": "Personal Independence Payment — UK disability benefit replacing DLA.",
      "certainty": 0.90,
      "first_appears_at": "02:14"
    },
    {
      "id": 2,
      "term": "NHS",
      "category": "acronym",
      "definition": "Acronym — definition unknown; please fill in",
      "certainty": 0.55,
      "first_appears_at": "00:45"
    }
  ]
}
```

### noteworthy.json

```json
{
  "items": [
    {
      "type": "freeze",
      "timestamp": "17:12",
      "duration_s": 13.49,
      "certainty": 0.90,
      "note": "🚨 >10s silence — probable emotional freeze",
      "action": "Listen to content immediately before + after — key emotional moment"
    },
    {
      "type": "possible_room_change",
      "timestamp": "00:22:05.00",
      "certainty": 0.46,
      "note": "Possible door/entry/exit event",
      "action": "⚠️ Shenanigans Watch — verify who was present before/after"
    },
    {
      "type": "undefined_acronym",
      "term": "OBR",
      "glossary_id": 3,
      "first_appears_at": "00:00",
      "note": "Acronym needs definition → glossary.json entry 3"
    },
    {
      "type": "uncertain_entity",
      "value": "Sharon",
      "certainty": 0.44,
      "note": "Person name 'Sharon' low-confidence — verify"
    }
  ]
}
```

---

## transcript.md Format

```markdown
# Transcript: audio_filename.m4a

| File | Contents |
|------|----------|
| [emotions.json](emotions.json) | Per-segment emotion, intensity, emoji, pauses |
| [things.json](things.json) | People, places, dates, times |
| [meta.json](meta.json) | Recording metadata, speakers, hashtags |
| [glossary.json](glossary.json) | Terms marked [G:N] in this transcript |
| [noteworthy.json](noteworthy.json) | Freezes, room changes, uncertainties |

> `[G:N]` after a word → see entry N in glossary.json
> `[C:0.00–1.00]` certainty — below 0.70 is ⚠️ verify

---

`(2.50)` notable pause

**[00:00] {Speaker_01} [😐 Neutral : 5/10] [C:0.70]:**
Hello, how is that OBR[G:1] report coming along?

`(13.49)` 🚨 **EXTENDED FREEZE**

**[00:14] {Speaker_02} [😢 Distress : 7/10] [C:0.70]:**
I really don't know where to start...
```

### transcript.md conventions

- `[MM:SS]` — timestamp in minutes:seconds
- `{Speaker_N}` — discovered speaker label (may be renamed via --match-voice)
- `[emoji Label : N/10]` — affect emoji, label, intensity score
- `[C:0.00–1.00]` — certainty of automated annotation
- `[G:N]` — inline reference to glossary.json entry N (first occurrence per term only)
- `(N.NN)` — pause duration in seconds (Jefferson notation)
- `🚨 EXTENDED FREEZE` — pause >10s (clinical marker: PTSD, dissociation)
- `⚠️ significant pause` — pause 5–10s

---

## Config Files (user-editable, no code changes needed)

### config/emotions.json

Extends `AFFECT_HEURISTICS`. Format per entry: `[regex_pattern, emoji, label, intensity]`

```json
{
  "patterns": [
    ["\\b(devastated|shattered)\\b", "💔", "Heartbroken", 9]
  ]
}
```

### config/places.json

Extends location detection. Plain strings, case-insensitive.

```json
{
  "locations": ["Chase Farm Hospital", "Meadowbrook Care Home"]
}
```

### config/wordlists.json

Extends glossary detection. Plain strings go to `medical`/`legal`/`technical` lists.
Objects with `term`+`definition` go into `custom` and appear verbatim in `glossary.json`.

```json
{
  "medical": ["my_medication"],
  "legal": ["my_local_council"],
  "technical": ["my_app"],
  "custom": [
    { "term": "PIP", "definition": "Personal Independence Payment.", "category": "benefit/legal" }
  ]
}
```

---

## Certainty Score Reference

| Range | Meaning | Suggested action |
|-------|---------|-----------------|
| [C:0.90–1.00] | High confidence | Trust, archive |
| [C:0.70–0.89] | Moderate | Spot-check |
| [C:0.50–0.69] | Low | ⚠️ Verify before citing |
| [C:<0.50] | Speculative | Flag for manual review |

---

## Jefferson Notation Reference

| Symbol | Phenomenon | Clinical note |
|--------|-----------|---------------|
| `~word~` | Shaky/crying voice | Diaphragmatic control loss; grief, distress |
| `WORD` | Shouting / emphasis | Caps = distinctly louder than baseline |
| `°word°` | Whisper | Shame, conspiracy, trauma recall |
| `#word#` | Creaky voice / vocal fry | Low arousal, exhaustion, confidence collapse |
| `£word£` | Smiley voice | Resonance shift from suppressed smile |
| `w(h)ord` | Breathiness / laugh spurt | Abrupt breath through word |
| `word::` | Prolonged sound | Each colon ≈ 0.2s extra |
| `↑↑word` | Extreme pitch spike | Panic, shock, dysregulation |
| `↓↓word` | Extreme pitch drop | Resignation, defeat |
| `>word<` | Accelerated delivery | Rushed, hurried |
| `<word>` | Decelerated delivery | Deliberate slowing |
| `.hhh` | Sharp inbreath | Shock, trauma trigger, sobbing prep |
| `hhh` | Exhalation | Length proportional to duration |
| `(.)` | Micropause | 0.08–0.2s |
| `(0.7)` | Timed pause | Tenths of seconds |
| `(01:04.20)` | Extended pause — CHAT | min:sec.ms — freeze marker |

---

## Clinical Markers (TEI XML — for annotation pass in Claude)

| Tag | Context | Use |
|-----|---------|-----|
| `<ptsd-frag type="repetition">` | Trauma narrative | Repeated phrases |
| `<ptsd-frag type="unfinished_utterance">` | Trauma narrative | Abandoned sentences |
| `<somatic>` | Visceral recall | Body-memory language |
| `<mental-defeat>` | I/me/my pronoun cluster | Isolation + hopelessness |
| `<maze>` | ADHD | Tangential narrative blocks |
| `<cluttering>` | ADHD | Rapid erratic speech |
| `<meta-correction type="rerail">` | ADHD | Self-correction back to topic |
| `<pause dur="1.2s" type="awkward"/>` | ASD | Non-grammatical pause |
| `<fs>` | Deception | False start |
| `<corrsp correct="X">Y</corrsp>` | Deception | Spontaneous correction |
| `<rep n="3">word</rep>` | Deception | Stalling repetition |
| `<lack-mem>` | Deception | Memory disclaimer |

---

## Affect Emoji Reference

| Emoji | Label | Typical trigger |
|-------|-------|----------------|
| 😐 | Neutral | Baseline |
| 😟 | Apologetic | sorry, forgive |
| 😨 | Anxious | help, please, desperate |
| 😠 | Refusing | no, never, won't |
| 🤩 | Positive | amazing, wonderful |
| 🤔 | Uncertain | don't know, maybe, perhaps |
| 😢 | Distress | cry, tears, hurt, pain |
| 😄 | Amusement | laugh, funny, joke |
| 😴 | Depleted | tired, exhausted, giving up |
| 😡 | Furious | angry, rage, outrageous |
| 😱 | Fearful | scared, terrified, afraid |
| 😕 | Confused | don't understand |
| 😤 | Frustrated | stuck, blocked, won't let |
| 💔 | Heartbroken | devastated, shattered (config) |
| 🌊 | Overwhelmed | can't cope, too much (config) |
| 🪦 | Hopeless | hopeless, pointless (config) |
| 🫥 | Dissociated | numb, blank, shutdown (config) |

---

## Workflow for LLM Annotation Pass

When a user provides a `transcript.md` generated by this tool, follow this workflow:

1. **Load context**: Read `LLM_CONTEXT.md` (this file). Load `glossary.json` for `[G:N]` definitions.
2. **Check noteworthy.json**: Prioritise freeze events and shenanigans items — listen guidance first.
3. **Annotate the transcript**: Apply Jefferson markers, TEI XML tags, and clinical phenotype tags inline.
4. **Fill glossary gaps**: Resolve undefined acronyms in `noteworthy.json` items of type `undefined_acronym`.
5. **Build analytical notes**: Context-specific interpretation per the `context_type` in `meta.json`.
6. **Output format**: Affective-Clinical-MD v2.6 — see schema reference above.
7. **Certainty**: Add `[C:N]` scores to every automated annotation.
8. **Schema version**: Set `schema_version: Affective-Clinical-MD-v2.6` in YAML frontmatter.

The `emotion-audio-analyser` skill in the Claude Cowork plugin contains full step-by-step instructions.

---

## Privacy Guarantee

`wispr_privacy_mode: true` in every `meta.json` means:
- Whisper ran locally — audio was never uploaded
- Resemblyzer ran locally — no internet connection made
- pyannote (if used) downloaded its model once; inference is local
- Source audio was read-only — never modified
- No data was sent to any external API or service
