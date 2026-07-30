# OMNI OUTPUT — 01_notld_calm_graveyard.wav

_Generated: 2026-07-30 16:24:11_
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
| File | 01_notld_calm_graveyard.wav |
| Duration | 00:21 (22.0s) |
| Whisper model | base |
| Language | en |
| Context | general |
| Schema | Affective-Clinical-MD-v3.0-Omni |
| Privacy | ✅ Local only |
| Segments | 1 |
| Words | 20 |
| Hashtags | #general |

## Cost & Token Estimate

| Metric | Value |
|--------|-------|
| Estimated words | 54 |
| Estimated tokens | 40 |
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

## Speaker Manifest

| Speaker | Method |
|---------|--------|
| Speaker_01 | none (Whisper turn heuristics only) |

## Emotion Timeline

| Time | Speaker | Emoji | Affect | Intensity | Pauses | Question | Raised |
|------|---------|-------|--------|-----------|--------|----------|--------|
| 00:00 | Speaker | 🤔 | Curious | 5/10 | 0.0s |  |  |

### Emotion Distribution

| Affect | Count | % |
|--------|-------|---|
| Curious | 1 | 100% |

## Deception Indicator Matrix

**Total deception indicators detected: 1**

| Type | Symbol | Count | Avg Certainty | Examples |
|------|--------|-------|---------------|----------|
| memory_disclaimer | <lack-mem> | 1 | [C:0.55] | Qualified memory — weakening commitment to statement |

### Deception Indicators Detail

| Time | Type | Note | Symbol | [C:] |
|------|------|------|--------|------|
| 00:00 | memory_disclaimer | Qualified memory — weakening commitment to statement | <lack-mem> | [C:0.55] |

> ⚠️ **IMPORTANT**: Deception indicators are NOT proof of deception. They are patterns
> that *may* indicate cognitive load, rehearsal, or evasive behaviour. Single indicators
> are meaningless — look for clusters and patterns. Always consider context, baseline
> behaviour, and alternative explanations. These are heuristic text-pattern matches, not
> voice-stress analysis or scientific deception detection.

## Veracity Indicator Matrix

**Total veracity indicators detected: 0**

_No veracity indicators detected._

### Deception vs Veracity Balance

| Metric | Value |
|--------|-------|
| Deception indicators | 1 (100%) |
| Veracity indicators | 0 (0%) |
| Ratio (veracity:deception) | 0.0:1 |
| Interpretation | More deception signals — review carefully |
