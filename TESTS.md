# Emotion Analyser — Test Runs

Always start here:
```bash
cd /Users/user/EmotionalVoiceAnalysis
```

All outputs go to `tests/test_complete/` — each run creates a named subfolder there.

---

## 1. Quick smoke test
**Brain-fart :: Sunflowers** — short personal memo, fast sanity check.
```bash
python3 src/run_transcription.py "tests/Brain-fart :: Sunflowers.m4a" --output-dir tests/test_complete
```

---

## 2. Small model, explicit
**Magic Talk** — forces `small` Whisper (more accurate, still fast).
```bash
python3 src/run_transcription.py "tests/Magic Talk.m4a" --model small --output-dir tests/test_complete
```

---

## 3. Auto model selection
**Anger Planet 2** — tool picks model size from audio duration.
```bash
python3 src/run_transcription.py "tests/emotional_range_tests/Voice Memo - 2026-01-14 17 14 45 - 2026-01-14 — Anger Planet 2.m4a" --auto-model --output-dir tests/test_complete
```

---

## 4. Multi-speaker / diarisation
**Paul + Mum: Talking** — two speakers, local clustering.
```bash
python3 src/run_transcription.py "tests/emotional_range_tests/Voice Memo - 2026-01-17 20 50 29 - 2026-01-17 — Paul + Mum: Talking.m4a" --diarise-local --output-dir tests/test_complete
```

---

## 5. Full forensic pass
**Sabrina meeting @ Springwell** — real meeting, all indicators on, cost estimate.
```bash
python3 src/run_transcription.py "tests/emotional_range_tests/Voice Memo - 2026-03-31 14 50 44 - 31-03-26 — Sabrina meeting @ Springwell.m4a" --auto-model --estimate-cost --output-dir tests/test_complete
```

---

## 6. Natalia + Jacky (emotional range test)
**Multi-person conversation, ~15 min** — good for emotion variety testing.
```bash
python3 src/run_transcription.py "tests/emotional_range_tests/Voice Memo - 2025-11-06 14 29 45 - 2025-11-06 — Natalia + Jacky.m4a" --auto-model --output-dir tests/test_complete
```

---

## 7. Batch dashboard (all test files)
```bash
python3 src/run_batch.py --dir tests/emotional_range_tests
```

| Key | Action |
|-----|--------|
| `Enter` | Start processing |
| `D` | Toggle deception |
| `N` | Cycle name privacy |
| `Q` | Quit |

---

## Optional: unlock voice dynamics
```bash
pip3 install librosa soundfile --break-system-packages
```
