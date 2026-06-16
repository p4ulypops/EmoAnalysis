---
name: emotion-audio-analyser
description: >
  Analyse emotional response, clinical markers, and paralinguistic features from an audio recording.
  Outputs a fully annotated Affective-Clinical-MD v2.5 transcript using Jefferson + TEI + CHAT notation.
  ALWAYS use this skill when the user mentions: audio analysis, emotion from audio, voice analysis,
  transcript annotation, clinical transcription, PTSD narrative, deception detection from speech,
  ASD prosody, ADHD speech patterns, care meeting recording, safeguarding transcript,
  or any request to analyse the emotional content of a recording or voice note.
  Also trigger when the user says: "analyse this recording", "annotate my audio", "what emotions
  are in this clip", "transcribe and flag", or "make this recording into evidence".
  v1.1: now detects named entities, classifies speakers (primary/secondary/bystander),
  detects environmental audio (music/radio/AI voices), acoustic events (car horns, doors),
  and room entry/exit with shenanigans flagging. All outputs carry [C:0.00–1.00] certainty scores.
compatibility:
  mcp_servers:
    - emotion-audio
---

# Emotion Audio Analyser

This skill turns an audio recording into a structured **Affective-Clinical-MD v2.5** transcript — 
annotated with emotion intensity, prosodic markers, clinical phenotypes (PTSD/ASD/ADHD), 
deception indicators, and safeguarding flags.

It uses the **emotion-audio MCP server** for transcription and prosody analysis, 
then applies the Jefferson + TEI + CHAT schema to produce a forensically useful document.

---

## Step 0 — Elicitation (always start here)

Before doing anything, ask Claude to surface these details from the user. 
You need them to configure the right schema layers and pick the right STT engine.

Ask as a single grouped message — don't fire them one at a time:

1. **Audio source** — file path / upload, or shall I start live recording?
2. **Context / purpose** — one of:
   - `clinical-ptsd` — trauma narrative, PTSD evaluation
   - `forensic-deception` — investigative interview, statement validity
   - `neurodivergent-adhd` — ADHD linguistic phenotyping
   - `neurodivergent-asd` — ASD prosodic assessment
   - `care-advocacy` — NHS/social care meeting, safeguarding record
   - `general` — exploratory / all-in-one
3. **Speakers** — names or IDs (e.g. "Patient_34, Dr_Aris"). Two minimum.
4. **Language** — or "auto" for detection.
5. **STT engine** — call `list_stt_engines` to show the menu, then confirm choice.
   - If the user is unsure, recommend **whisper-local** for sensitive data or **whisper-api** for speed.
   - Note that ElevenLabs gives speaker diarisation if they want labels automatically.
6. **Transcript ID** (optional) — defaults to auto-generated datestamp.

Only proceed to Step 1 once you have answers to 1–4 and a confirmed engine.

---

## Step 1 — List engines and confirm

Call `list_stt_engines` and show the output to the user.
Wait for explicit confirmation of which engine to use before transcribing.
This matters — the user may be handling sensitive NHS/forensic data.

---

## Step 2 — Transcribe

### File input
Call `transcribe_audio` with:
- `file_path`: the path provided
- `engine`: confirmed engine
- `language`: from elicitation
- `prompt_context`: a brief hint matching the context type 
  (e.g. "NHS clinical interview, UK English, patient and therapist")

### Live recording
If the user wants to record now:
1. Ask for duration in seconds.
2. Call `record_audio(duration_seconds=…)`.
3. Use the returned file path in `transcribe_audio`.

---

## Step 2b — Environmental + acoustic scan (run in parallel with transcription)

While transcription runs, kick off these three scans on the same audio file simultaneously:

1. `detect_environmental_audio(file_path)` — music, radio, TV, AI assistant voices
2. `detect_acoustic_events(file_path)` — car horns, door slams, alarms, dogs, phones
3. `detect_room_changes(file_path)` — entry/exit events, footsteps, shenanigans flags

Save all three outputs. They feed into the final transcript as TEI `<incident>` tags
and the Environmental Events summary table.

---

## Step 3 — Prosody analysis

Call `analyse_prosody` on the same audio file in parallel with (or immediately after) transcription.

This extracts:
- Pitch F0 mean/std (flags ASD flat affect if std < 20 Hz)
- Energy dynamic range (flags emotional blunting)
- Pause inventory (maps to CHAT `(1:04.20)` freeze markers)
- Arousal proxy (flags panic vs dissociation)

Pass the JSON output to `generate_affective_transcript` as `prosody_json`.

---

## Step 3b — Entity extraction and speaker classification

Once the transcript is available:

1. Call `extract_entities(transcript, speaker_hints="[names from elicitation]")`
   - Pulls names, dates, locations with [C:] scores
   - Flags low-confidence extractions for manual verification

2. Call `classify_speakers(transcript, known_primaries="[from elicitation]")`
   - Labels each speaker: PRIMARY / SECONDARY / BYSTANDER
   - Bystanders are noted but excluded from clinical analysis
   - Flags moments where bystander language patterns suggest incidental presence

---

## Step 4 — Generate annotated transcript

Call `generate_affective_transcript` with:
- `raw_transcript`: text from Step 2
- `prosody_json`: JSON string from Step 3
- `context_type`: from elicitation
- `speakers`: from elicitation
- `transcript_id`: from elicitation or auto
- `include_analytical_notes: true`

---

## Step 5 — Assemble and present

The final document has these sections in order:

1. **YAML frontmatter** (transcript ID, date, speakers, context, schema version)
2. **Entity Register** — names, dates, locations with [C:] scores from `extract_entities`
3. **Speaker Manifest** — role table (PRIMARY/SECONDARY/BYSTANDER) from `classify_speakers`
4. **Environmental Events Log** — summary table from Steps 2b scans
5. **Acoustic-Prosodic Baseline** — pitch, energy, arousal from `analyse_prosody`
6. **Annotated Transcript** — from `generate_affective_transcript`, enriched with:
   - TEI `<incident>` tags from environmental/acoustic/room scans inserted at correct timestamps
   - `{BYSTANDER}` blocks for incidental speakers, visually separated
   - `[C:0.00–1.00]` scores on every automated annotation
7. **Analytical Notes** — context-specific interpretation
8. **Shenanigans Watch** ⚠️ — if `detect_room_changes` flagged any entry/exit moments

When instructing the user to run `run_transcription.py` locally, always use the full script path:
```
python3 '/Users/user/Library/Application Support/Claude/local-agent-mode-sessions/9f946972-8ad4-4a83-bda4-fd9d7e621aad/b6e0b069-0598-4b7f-bfaf-fa7c4d9e0e64/local_152db07a-1520-4dae-aa27-00751e5d4cdf/outputs/run_transcription.py' '/path/to/audio.m4a'
```

Save as `<transcript_id>.md`. Offer PDF export via `trauma-evidence-pdf` skill for
forensic, care-advocacy, or legal submission contexts.

---

## Schema quick reference

> Full schema details live in `references/schema.md`. Load it if you need 
> deeper guidance on any notation system.

### Affective header format
```
[HH:MM:SS.mmm] {Speaker_ID} [😨 Anxious : 8/10] <Cert:High>:
```

### Key paralinguistic markers

| Symbol | Phenomenon |
|--------|------------|
| `~word~` | Shaky/crying voice |
| `WORD` | Shouting |
| `°word°` | Whispering |
| `#word#` | Creaky voice / vocal fry |
| `£word£` | Suppressed laughter / smiley voice |
| `(0.7)` | Timed pause (seconds) |
| `(1:04.20)` | Extended pause — CHAT format (min:sec.ms) |
| `↑↑word` | Extreme pitch spike |
| `>word<` | Accelerated delivery |
| `word::` | Prolonged sound |
| `.hhh` | Sharp inbreath |
| `hhh` | Exhalation |

### Clinical XML tags

| Tag | Context |
|-----|---------|
| `<ptsd-frag type="repetition">` | Trauma narrative fragmentation |
| `<somatic>…</somatic>` | Visceral sensory recall |
| `<mental-defeat>…</mental-defeat>` | High first-person pronoun + isolation |
| `<maze>…</maze>` | ADHD tangential narrative |
| `<cluttering>…</cluttering>` | Rapid erratic speech (ADHD) |
| `<meta-correction type="rerail">` | ADHD self-correction back to topic |
| `<pause dur="1.2s" type="awkward"/>` | ASD non-grammatical gap |
| `<fs>` | False start (deception) |
| `<corrsp correct="[word]">` | Spontaneous correction (deception) |
| `<rep n="3">word</rep>` | Stalling repetition (deception) |
| `<lack-mem>…</lack-mem>` | Memory disclaimer (deception defence) |

---

## Persona output guidelines

### `care-advocacy`
- Flag power imbalances (`=` latching, interruptions).
- Bold (`**`) any clinically or legally significant utterances.
- Add safeguarding flags 🚩 with a one-line note explaining the concern.
- Suitable for submission to Ombudsman, MP, solicitor, or CQC.

### `forensic-deception`
- Annotate every `<fs>`, `<corrsp>`, `<rep>`, `<lack-mem>` instance.
- Add a **Deception Probability Matrix** table at the end:
  - Columns: Marker type | Count | % of turns | Interpretation

### `clinical-ptsd`
- Compute estimated readability score (Flesch-Kincaid) if possible via bash.
- Count first-person pronouns vs cognitive integration words.
- Note CHAT-formatted freeze pauses > 30s explicitly.

### `neurodivergent-asd`
- Compare F0 std against TD baseline (>20 Hz = normal variability).
- Score expressivity 1–10 per speaker turn.
- Flag articulation rate if below 4 syllables/second.

### `neurodivergent-adhd`
- Count `<maze>` blocks and estimate semantic divergence qualitatively.
- Track `<meta-correction>` frequency as self-awareness marker.

---

## Reference files

- `references/schema.md` — Full Jefferson/TEI/CHAT notation guide with examples
- `references/clinical-markers.md` — ADHD/ASD/PTSD/deception marker reference

Load these if you need to check a specific notation or clinical criterion during annotation.
