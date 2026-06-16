# Emotion Audio Analyser — Technical Reference

This companion file is aimed at developers, analysts, and technical users.

## Architecture overview

The repository centers on `run_transcription.py`, a Python script that:
- loads optional configuration from `config/`
- transcribes audio with OpenAI Whisper models
- optionally performs speaker diarization using local clustering or pyannote.audio
- extracts entities, emotions, and event flags
- writes structured output files in a folder alongside the source audio

## Key files

- `run_transcription.py` — main CLI entrypoint and processing pipeline.
- `config/emotions.json` — custom emotion detection patterns.
- `config/places.json` — custom place names for entity recognition.
- `config/wordlists.json` — custom glossary and domain vocabularies.
- `LLM_CONTEXT.md` — context and examples for supporting LLM workflows.
- `emotion-audio-plugin/` — plugin assets and assistant-related schema material.

## Command-line flags

The script accepts these main inputs:

- `audio` — required audio path.
- `--model` — Whisper model name; defaults to `base`.
- `--language` — target transcription language; defaults to `en`.
- `--context` — analysis context label written to metadata.
- `--output-dir` — output folder path.
- `--diarise-local` — local speaker clustering via Resemblyzer.
- `--diarise` — pyannote diarization.
- `--hf-token` — HuggingFace token for `--diarise`.
- `--n-speakers` — expected speaker count to improve clustering.
- `--match-voice` — repeatable pair of a known voice clip and a speaker name.

## Data flow

1. `load_config()` reads `config/` files and merges wordlists.
2. Whisper transcribes the audio into timestamps and segments.
3. Speaker labels are assigned from Whisper turns, or refined with diarization.
4. `match_voice()` optionally maps known reference clips to speaker labels.
5. Emotion heuristics and glossary matching are applied to transcript text.
6. Output files are written in the audio-specific output folder.

## Output formats

- `transcript.md` — annotated markdown transcript.
- `emotions.json` — emotion segment data.
- `things.json` — named entities and contextual items.
- `meta.json` — pipeline metadata and settings.
- `glossary.json` — extracted glossary terms.
- `noteworthy.json` — review flags for important moments.

## Config details

### `config/emotions.json`
Defines custom emotion patterns with:
- regex pattern
- emoji
- label
- intensity

Example:

```json
{
  "patterns": [
    ["\\b(frustrated|upset)\\b", "😤", "Frustrated", 6]
  ]
}
```

### `config/places.json`
Lists additional locations to detect while extracting entities.

### `config/wordlists.json`
Supports four categories:
- `medical`
- `legal`
- `technical`
- `custom`

These terms are folded into the glossary engine to improve matching.

## Privacy and safety

The code is designed for local analysis and should not be used to expose sensitive recordings.

- `meta.json` preserves a record of the analysis pipeline.
- Speaker names are never assumed when using diarization.
- `--diarise-local` is the private option; `--diarise` uses a local model with a HuggingFace token.

## Editing and contribution

To extend detection patterns or vocabulary, add entries to the relevant `config/` files. No code changes are required for these customizations.

For any updates to behavior, inspect `run_transcription.py` and verify the output files still match their described formats.
