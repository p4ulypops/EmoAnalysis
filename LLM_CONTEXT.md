# LLM_CONTEXT — Emotion Audio Analyser v3.0

This file describes the tool's purpose, CLI interface, all output schemas, config format,
and notation systems. Load this file as context before helping a user with this tool.

---

## Tool Purpose

`run_transcription.py` is a local audio transcription and analysis tool.
It takes an audio recording (m4a, mp3, wav) and produces a structured output folder containing:
- A verbatim timestamped transcript with inline glossary references and ALL Jefferson markers
- Emotional intensity scores per utterance
- Named entity extraction (people, places, dates, times)
- Glossary of domain-specific terms found in speech
- Metadata about the recording
- Noteworthy flagged moments (emotional freezes, deception, veracity, clinical, room events)
- **NEW v3.0**: Deception indicators (false starts, corrections, stalling, memory disclaimers, evasion)
- **NEW v3.0**: Veracity/truthfulness indicators (certainty, sensory detail, temporal sequencing)
- **NEW v3.0**: Voice dynamics (raised voice, quiet, whisper, sub-vocal, shaky voice)
- **NEW v3.0**: Clinical markers (PTSD, ASD, ADHD phenotypes)
- **NEW v3.0**: Omni output (omni.md) — everything in one file
- **NEW v3.0**: Analysis.json — structured indicator data

All processing is local. No audio or transcript data is sent externally.
Schema: Affective-Clinical-MD v3.0 (Jefferson + TEI + CHAT notation + Omni indicators).

---

## CLI Invocation

```
python3 '/path/to/run_transcription.py' AUDIO_PATH [OPTIONS]
```

### Arguments

```
AUDIO_PATH              Required. Path to audio file. Supports: m4a mp3 wav ogg flac aiff
--model MODEL           Whisper model. Values: tiny|base|small|medium|large. Default: base
--auto-model            Auto-select model based on audio duration (token min-maxing)
--language LANG         ISO 639-1 code. Default: en.
--context LABEL         Free-text label stored in meta.json. Default: general
--output-dir PATH       Directory for output folder. Default: current working directory
--diarise-local         Enable local speaker clustering (Resemblyzer). No internet needed.
--diarise               Enable pyannote.audio diarization. Requires --hf-token or HF_TOKEN
--hf-token TOKEN        HuggingFace access token for --diarise
--n-speakers N          Integer hint for expected speaker count. Auto-detected if omitted.
--match-voice PATH NAME Match a known voice clip (PATH) to a speaker label (NAME). Repeatable.
--subfolder-suffix S    Suffix for output subfolder. Default: _subfile
--no-copy-audio         Don't copy audio into output folder
--no-viewer             Don't generate HTML viewer
--omni / --no-omni      Control omni.md generation (default: ON)
--no-jefferson          Disable Jefferson paralinguistic markers
--no-deception          Disable deception indicator detection
--no-veracity           Disable truthfulness/veracity indicator detection
--no-voice-dynamics     Disable voice dynamics analysis
--no-clinical           Disable clinical marker detection (PTSD/ASD/ADHD)
--no-emotional          Disable emotional analysis (affect heuristics)
--estimate-cost         Print token/cost estimation before running
```

---

## Output Structure

```
<audio_stem>/
├── transcript.md       Annotated transcript with all inline markers
├── emotions.json       Per-segment emotion + deception + veracity + clinical data
├── things.json         Named entities: people, places, dates, times
├── meta.json           Recording metadata, speakers, hashtags, cost estimate, features
├── glossary.json       Domain terms found in speech, with definitions
├── noteworthy.json     Flagged moments requiring human review
├── omni.md             EVERYTHING — all views, all indicators, all markers in one file
├── analysis.json       Structured deception/veracity/voice/clinical/Jefferson data
└── viewer.html         Interactive HTML viewer (optional)
```

---

## v3.0 Feature Summary

All features are ON by default. Each can be disabled via CLI flags.

### Jefferson Paralinguistic Markers (--no-jefferson to disable)
WORD (CAPS), °word° (whisper), ~word~ (shaky), #word# (creaky), word:: (prolonged),
↑↑ (pitch spike), ↓↓ (pitch drop), >word< (accelerated), <word> (decelerated),
.hhh (inbreath), hhh (exhalation), (.) (micropause), (0.7) (timed pause),
(1:04.20) (freeze), = (latching), [ (overlap), (word) (uncertain)

### Deception Indicators (--no-deception to disable)
<fs> (false start), <corrsp> (spontaneous correction), <rep> (stalling repetition),
<lack-mem> (memory disclaimer), <over-elab> (over-elaboration), <defensive> (defensive language),
<contradict> (contradiction), <cog-load> (cognitive load), <evade> (evasion)

### Veracity Indicators (--no-veracity to disable)
<veracious> (qualified certainty), <sensory-recall> (sensory detail), <temporal> (temporal sequencing),
<context> (contextual embedding), <emo-consist> (emotional consistency),
<cog-complex> (cognitive complexity), <spontaneous> (spontaneous detail), <recall-pause> (appropriate pause)

### Voice Dynamics (--no-voice-dynamics to disable, requires librosa)
raised_voice, normal, quiet, whisper, sub_vocal, shaky_voice

### Clinical Markers (--no-clinical to disable)
PTSD: <ptsd-frag>, <somatic>, <mental-defeat>
ADHD: <meta-correction>, <maze>
ASD: <pause type="awkward"/>

### Emotional Analysis (--no-emotional to disable)
12 built-in affect heuristics + custom patterns from config/emotions.json

---

## omni.md Structure

1. Recording Metadata
2. Cost & Token Estimate
3. Entity Register
4. Speaker Manifest
5. Emotion Timeline + Distribution
6. Deception Indicator Matrix (summary + detail)
7. Veracity Indicator Matrix (summary + detail)
8. Deception vs Veracity Balance (ratio + interpretation)
9. Voice Dynamics Report
10. Clinical Markers Report (by phenotype)
11. Jefferson Paralinguistic Markers (all symbols, counts)
12. Environmental Events Log + Freeze Events
13. Noteworthy Items (grouped by type)
14. Full Annotated Transcript (all inline markers per segment)
15. Glossary
16. Configuration Summary

---

## Token Min-Maxing

- `--auto-model` selects Whisper model based on duration
- `--estimate-cost` shows token count and processing time
- Model profiles: tiny (0-10min), base (0-30min), small (1-60min), medium (5-120min), large (10min+)
- For batch: use tiny for drafts, base/small for final
- Sub-agents can process different files in parallel with different models

---

## Certainty Score Reference

| Range | Meaning | Suggested action |
|-------|---------|-----------------|
| [C:0.90–1.00] | High confidence | Trust, archive |
| [C:0.70–0.89] | Moderate | Spot-check |
| [C:0.50–0.69] | Low | ⚠️ Verify before citing |
| [C:<0.50] | Speculative | Flag for manual review |

---

## Privacy Guarantee

`wispr_privacy_mode: true` in every `meta.json` means:
- Whisper ran locally — audio was never uploaded
- Resemblyzer ran locally — no internet connection made
- pyannote (if used) downloaded its model once; inference is local
- Source audio was read-only — never modified
- No data was sent to any external API or service
