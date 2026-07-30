# OMNI OUTPUT — 04_detour_deceptive.wav

_Generated: 2026-07-30 16:12:56_
_Schema: Affective-Clinical-MD v3.0 (Omni)_
_All indicators ON by default — see config summary below_

---

## Table of Contents
1. [Recording Metadata](#recording-metadata)
2. [Cost & Token Estimate](#cost--token-estimate)
3. [Entity Register](#entity-register)
4. [Speaker Manifest](#speaker-manifest)
5. [Emotion Timeline](#emotion-timeline)
6. [Deception Indicator Matrix](#deception-indicator-matrix)
7. [Veracity Indicator Matrix](#veracity-indicator-matrix)
8. [Voice Dynamics Report](#voice-dynamics-report)
9. [Clinical Markers Report](#clinical-markers-report)
10. [Jefferson Paralinguistic Markers](#jefferson-paralinguistic-markers)
11. [Environmental Events Log](#environmental-events-log)
12. [Noteworthy Items](#noteworthy-items)
13. [Full Annotated Transcript](#full-annotated-transcript)
14. [Glossary](#glossary)
15. [Configuration Summary](#configuration-summary)

---

## Recording Metadata

| Field | Value |
|-------|-------|
| File | 04_detour_deceptive.wav |
| Duration | 00:24 (24.2s) |
| Whisper model | base |
| Language | en |
| Context | general |
| Schema | Affective-Clinical-MD-v3.0-Omni |
| Privacy | ✅ Local only |
| Segments | 1 |
| Words | 108 |
| Hashtags | #general |

## Cost & Token Estimate

| Metric | Value |
|--------|-------|
| Estimated words | 62 |
| Estimated tokens | 46 |
| Model used | base |
| Est. processing time | 0.4 min |
| Cost (local Whisper) | $0.00 |
| Note | Local Whisper — no API cost. For cloud LLM annotation pass, ~$0.01-0.05 per transcript. |

**Token Min-Maxing Tips:**
- Use `--auto-model` to auto-select Whisper model based on duration
- For batch processing, split long files and use `tiny` for drafts, `base` for final
- Sub-agents can process different files in parallel with different models
- Cloud LLM annotation pass costs ~$0.01-0.05 per transcript via OpenRouter

## Entity Register

| Entity | Type | [C:] | Occurrences | Notes |
|--------|------|------|-------------|-------|
| From | Person | [C:0.44] | 1 | heuristic ⚠️ verify |
| Siamese | Person | [C:0.44] | 1 | heuristic ⚠️ verify |
| Since | Person | [C:0.44] | 1 | heuristic ⚠️ verify |
| Say | Person | [C:0.44] | 1 | heuristic ⚠️ verify |
| Have | Person | [C:0.44] | 1 | heuristic ⚠️ verify |
| Get | Person | [C:0.44] | 1 | heuristic ⚠️ verify |
| Nothing | Person | [C:0.44] | 1 | heuristic ⚠️ verify |
| Okay | Person | [C:0.44] | 1 | heuristic ⚠️ verify |
| next door | Date (relative) | [C:0.88] | | |
| this car | Date (relative) | [C:0.88] | | |

## Speaker Manifest

| Speaker | Method |
|---------|--------|
| Speaker_01 | none (Whisper turn heuristics only) |

## Emotion Timeline

| Time | Speaker | Emoji | Affect | Intensity | Pauses | Question | Raised |
|------|---------|-------|--------|-----------|--------|----------|--------|
| 00:00 | Speaker | 😱 | Fearful | 8/10 | 0.0s |  |  |

### Emotion Distribution

| Affect | Count | % |
|--------|-------|---|
| Fearful | 1 | 100% |

## Deception Indicator Matrix

**Total deception indicators detected: 0**

_No deception indicators detected._

> ⚠️ **IMPORTANT**: Deception indicators are NOT proof of deception. They are patterns
> that *may* indicate cognitive load, rehearsal, or evasive behaviour. Single indicators
> are meaningless — look for clusters and patterns. Always consider context, baseline
> behaviour, and alternative explanations. These are heuristic text-pattern matches, not
> voice-stress analysis or scientific deception detection.

## Veracity Indicator Matrix

**Total veracity indicators detected: 3**

| Type | Symbol | Count | Avg Certainty | Examples |
|------|--------|-------|---------------|----------|
| temporal_sequencing | <temporal> | 2 | [C:0.55] | Temporal sequencing — structured recall; Temporal relation — genuine memory structure |
| contextual_embedding | <context> | 1 | [C:0.55] | Spatial embedding — genuine memory |

### Veracity Indicators Detail

| Time | Type | Note | Symbol | [C:] |
|------|------|------|--------|------|
| 00:00 | temporal_sequencing | Temporal sequencing — structured recall | <temporal> | [C:0.55] |
| 00:00 | temporal_sequencing | Temporal relation — genuine memory structure | <temporal> | [C:0.55] |
| 00:00 | contextual_embedding | Spatial embedding — genuine memory | <context> | [C:0.55] |

### Deception vs Veracity Balance

| Metric | Value |
|--------|-------|
| Deception indicators | 0 (0%) |
| Veracity indicators | 3 (100%) |
| Ratio (veracity:deception) | 3.0:1 |
| Interpretation | More veracity signals — likely truthful overall |
