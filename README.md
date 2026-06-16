# Emotion Audio Analyser — Reference Guide

A local audio analysis tool for transcribing speech, identifying speakers, and flagging emotional and contextual events.

This repo is a processing utility. It extracts structure from recordings and writes review-ready outputs. The tool is designed to run on your machine and does not send audio files out by default.

---

## What it does

- Transcribes audio from m4a, mp3, wav, ogg, flac files
- Detects speaker turns and optional speaker clusters
- Annotates emotion, pauses, and uncertainty
- Extracts people, places, dates, and times
- Produces JSON and Markdown output for review or automation

---

## Quick start

```bash
python3 ./run_transcription.py /path/to/audio.m4a
```

A folder named after the audio file is created with:
- `transcript.md`
- `emotions.json`
- `things.json`
- `meta.json`
- `glossary.json`
- `noteworthy.json`

For more technical detail, see `techy.readme.md`.

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

If you use `--diarise`, you also need a HuggingFace token.

---

## Use cases

### Transcribe a file

```bash
python3 ./run_transcription.py /path/to/audio.m4a
```

### Private speaker clustering

```bash
python3 ./run_transcription.py /path/to/audio.m4a --diarise-local
```

### Fix speaker count

```bash
python3 ./run_transcription.py /path/to/audio.m4a --diarise-local --n-speakers 2
```

### Best speaker diarization

```bash
export HF_TOKEN=hf_yourtoken
python3 ./run_transcription.py /path/to/audio.m4a --diarise --hf-token $HF_TOKEN
```

### Name speakers with reference clips

```bash
python3 ./run_transcription.py /path/to/audio.m4a \
  --diarise-local \
  --match-voice /clips/reference1.m4a Speaker_01 \
  --match-voice /clips/reference2.m4a Speaker_02
```

Only add known voice references when you already know the speaker identity. The tool will rename a detected cluster only when the voice match is confident.

---

## Output files

### `transcript.md`
A human-readable transcript with timestamps, speaker labels, emoji cues, pause markers, and glossary references.

### `emotions.json`
Segment-level emotion tagging with intensity, pause detection, and flags.

### `things.json`
Detected people, places, dates, and times.

### `meta.json`
Run metadata, model choice, speaker settings, and privacy notes.

### `glossary.json`
Terms, acronyms, and domain vocabulary discovered in the recording.

### `noteworthy.json`
Highlighted moments and follow-up items for review.

---

## How to use

- Use `--diarise-local` if you want private, offline speaker clustering.
- Use `--diarise` only if you need more advanced speaker separation.
- Keep audio local and review outputs manually.
- The tool is an assistant, not a final decision engine.

---

## Customization

Edit `config/` files to tune the output without changing code.

### `config/emotions.json`
Add custom emotion patterns and labels.

### `config/places.json`
Add custom location names to recognize.

### `config/wordlists.json`
Extend the glossary with medical, legal, technical, and custom terms.

Terms with your own definitions (appear verbatim in `glossary.json`):
```json
{
  "custom": [
    {
      "term": "PIP",
      "definition": "Personal Independence Payment — UK disability benefit.",
      "category": "benefit/legal"
    }
  ]
}
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

## Jefferson Notation (in transcript.md)

| Marker | Meaning |
|--------|---------|
| `~word~` | Shaky/crying voice |
| `WORD` | Shouting / raised voice |
| `°word°` | Whisper |
| `#word#` | Creaky voice / vocal fry |
| `(0.7)` | Pause in seconds |
| `(01:04.20)` | Extended pause — min:sec.ms |
| `↑↑word` | Extreme pitch spike |
| `>word<` | Accelerated delivery |
| `word::` | Prolonged sound |
| `.hhh` | Sharp inbreath |

---

## Privacy

- Whisper runs **entirely on your machine** — audio is never uploaded
- Resemblyzer runs **entirely on your machine** — no internet required
- pyannote downloads a model once on first use, then runs locally
- `wispr_privacy_mode: true` is written into every `meta.json` as a record of this
- Audio files in `DONT_TOUCH_RAW` folders are read-only — the script never modifies source files

---

## Next Steps After Running

1. Open `transcript.md` and listen back — apply Jefferson markers where you hear emotion
2. Fill in undefined acronyms in `glossary.json` (check `noteworthy.json` for the list)
3. Verify ⚠️ flagged entities in `things.json`
4. Paste `transcript.md` into Claude with the `emotion-audio-analyser` skill for full annotation
5. For PDF evidence output: use the `trauma-evidence-pdf` skill in Claude

---

## Troubleshooting

**"No such file or directory: run_transcription.py"**
Use the full path in quotes: `python3 '/full/path/to/run_transcription.py'`

**Transcription is slow**
Normal for long files. A 37-minute recording takes ~10–15 min on CPU with the `base` model.
Use `--model tiny` for a fast draft run first.

**Speaker clustering puts everyone in one group**
Try `--n-speakers 2` (or however many speakers you know are present).

**Voice match certainty is low (<0.60)**
The reference clip may be too short or contain background noise. Use a clean 30–60 second clip.

**ffmpeg not found**
Run: `brew install ffmpeg`

**ImportError for resemblyzer or pyannote**
Run: `pip3 install resemblyzer scikit-learn --break-system-packages`
or: `pip3 install pyannote.audio --break-system-packages`
