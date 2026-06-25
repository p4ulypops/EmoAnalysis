#!/usr/bin/env python3
"""
Emotion Audio — Local Transcription + Analysis Script  v3.0

v3.0 — Omni output, full Jefferson, deception + veracity, voice dynamics, token min-maxing
v2.1 — Diarization, voice matching, environmental scans, HTML viewer
v2.0 — Core pipeline

Creates a folder named after the audio file containing:
    transcript.md    — verbatim transcript with timings + [G:N] glossary refs
    emotions.json    — per-segment emotion, intensity, emoji, pauses
    things.json      — people, places, dates, times
    meta.json        — recording metadata, speakers, hashtags, file info
    glossary.json    — medical/legal/tech terms + acronyms found in speech
    noteworthy.json  — flagged moments (freezes, events, uncertainties)
    omni.md          — EVERYTHING in one file (all views, all markers, all indicators)
    analysis.json    — deception/veracity/voice-dynamics/clinical data
    viewer.html      — interactive HTML viewer (optional)

Requirements:
    pip3 install openai-whisper librosa soundfile numpy --break-system-packages
    brew install ffmpeg

Speaker identification (choose one):

  Tier 1 — No diarization (default):
    Speakers labelled Speaker_01, Speaker_02 etc. from Whisper turn changes only.

  Tier 2 — Local / no token (recommended for private recordings):
    pip3 install resemblyzer scikit-learn --break-system-packages
    python3 '...run_transcription.py' audio.m4a --diarise-local

  Tier 3 — pyannote (best accuracy, free HuggingFace token required):
    pip3 install pyannote.audio --break-system-packages
    python3 '...run_transcription.py' audio.m4a --diarise --hf-token hf_xxx

Usage:
    python3 run_transcription.py '/path/to/audio.m4a'
    python3 run_transcription.py '/path/to/audio.m4a' --diarise-local
    python3 run_transcription.py '/path/to/audio.m4a' --model small
    python3 run_transcription.py '/path/to/audio.m4a' --omni
    python3 run_transcription.py '/path/to/audio.m4a' --auto-model
    python3 run_transcription.py '/path/to/audio.m4a' --no-deception --no-veracity

All options:
    --model         Whisper model: tiny|base|small|medium|large (default: base)
    --auto-model    Auto-select model based on audio duration (token min-maxing)
    --language      ISO 639-1 code (default: en)
    --context       Context label (default: general)
    --output-dir    Where to create output folder
    --diarise-local Local speaker clustering (Resemblyzer, no internet)
    --diarise       pyannote diarization (needs HF token)
    --hf-token      HuggingFace token
    --n-speakers    Expected speaker count
    --match-voice   Match known voice clips: --match-voice clip.m4a Name
    --subfolder-suffix  Suffix for output subfolder (default: _subfile)
    --no-copy-audio Don't copy audio into output folder
    --no-viewer     Don't generate HTML viewer
    --omni          Generate omni.md (comprehensive single-file output) — default ON
    --no-omni       Skip omni.md generation
    --no-jefferson  Disable Jefferson paralinguistic marker detection
    --no-deception  Disable deception indicator detection
    --no-veracity   Disable truthfulness/veracity indicator detection
    --no-voice-dynamics  Disable voice dynamics analysis (raised voice, whisper, etc.)
    --no-clinical   Disable clinical marker detection (PTSD/ASD/ADHD)
    --no-emotional  Disable emotional analysis (affect heuristics)
    --estimate-cost Print token/cost estimation before running
    --json-output   Output analysis.json with all structured indicator data
"""

import argparse
import json
import re
import subprocess
import sys
import shutil
from datetime import datetime, timedelta
from pathlib import Path



# ─── Token Min-Maxing / Model Selection ─────────────────────────────────────────

# Model cost table (approximate, OpenRouter pricing in USD per 1K tokens)
# Whisper models are local/free but have different speed/resource trade-offs
WHISPER_MODEL_PROFILES = {
    "tiny":   {"vram_mb": 1000,  "speed": "fastest",  "accuracy": "draft",  "min_duration_s": 0,    "max_duration_s": 600},
    "base":   {"vram_mb": 1000,  "speed": "fast",     "accuracy": "good",   "min_duration_s": 0,    "max_duration_s": 1800},
    "small":  {"vram_mb": 2000,  "speed": "medium",   "accuracy": "better", "min_duration_s": 60,   "max_duration_s": 3600},
    "medium": {"vram_mb": 5000,  "speed": "slow",     "accuracy": "high",   "min_duration_s": 300,  "max_duration_s": 7200},
    "large":  {"vram_mb": 10000, "speed": "slowest",  "accuracy": "best",   "min_duration_s": 600,  "max_duration_s": 99999},
}

def auto_select_model(duration_s: float) -> str:
    """Auto-select Whisper model based on audio duration for optimal speed/accuracy."""
    for model_name in ["tiny", "base", "small", "medium", "large"]:
        profile = WHISPER_MODEL_PROFILES[model_name]
        if profile["min_duration_s"] <= duration_s <= profile["max_duration_s"]:
            return model_name
    return "base"

def estimate_tokens(duration_s: float, model_size: str) -> dict:
    """Estimate token count and processing cost."""
    # Rough: English speech ~150 words/min, ~0.75 tokens/word
    words_per_min = 150
    est_words = int((duration_s / 60) * words_per_min)
    est_tokens = int(est_words * 0.75)
    # Whisper processing time estimate (on CPU, base model)
    speed_multiplier = {"tiny": 0.5, "base": 1.0, "small": 2.5, "medium": 5.0, "large": 10.0}
    est_process_s = duration_s * speed_multiplier.get(model_size, 1.0)
    return {
        "estimated_words": est_words,
        "estimated_tokens": est_tokens,
        "estimated_process_seconds": int(est_process_s),
        "estimated_process_minutes": round(est_process_s / 60, 1),
        "model": model_size,
        "cost_usd": 0.0,  # Local Whisper is free
        "note": "Local Whisper — no API cost. For cloud LLM annotation pass, ~$0.01-0.05 per transcript.",
    }


# ─── Wordlists ────────────────────────────────────────────────────────────────

MEDICAL_TERMS = {
    "nhs", "gp", "mri", "ct", "a&e", "icu", "physio", "physiotherapy",
    "adhd", "asd", "autism", "ptsd", "ocd", "bpd", "bipolar", "schizophrenia",
    "dementia", "alzheimer", "diagnosis", "prognosis", "symptom", "consultant",
    "referral", "prescription", "dosage", "discharge", "triage", "ambulance",
    "paramedic", "psychiatrist", "psychologist", "therapist", "safeguarding",
    "care plan", "social worker", "mental health", "occupational therapy",
    "speech therapy", "cognitive", "sensory", "executive function", "masking",
    "meltdown", "shutdown", "stimming", "hyperfocus", "burnout", "comorbid",
}

LEGAL_TERMS = {
    "ombudsman", "tribunal", "injunction", "affidavit", "claimant",
    "defendant", "plaintiff", "respondent", "appellant", "barrister",
    "solicitor", "indemnity", "liability", "negligence", "tort",
    "judicial review", "section 20", "section 47", "duty of care",
    "statutory", "cqc", "ofsted", "gdpr", "foi", "freedom of information",
    "subject access", "mca", "mental capacity act", "dols", "chc",
    "continuing healthcare", "advocate", "independent", "complaint",
}

TECH_TERMS = {
    "api", "sdk", "ai", "ml", "llm", "gpt", "algorithm", "database",
    "server", "cloud", "github", "python", "javascript", "app", "software",
    "hardware", "wifi", "bluetooth", "nfc", "qr", "blockchain", "crypto",
    "mcp", "plugin", "model", "neural", "prompt", "token", "inference",
}


# ─── Config Loading ───────────────────────────────────────────────────────────

CUSTOM_GLOSSARY_DEFS: list = []
EXTRA_PLACES: list = []

def load_config(script_path: Path) -> None:
    """Load user config files from config/ next to the script and merge into globals."""
    global MEDICAL_TERMS, LEGAL_TERMS, TECH_TERMS, AFFECT_HEURISTICS
    global CUSTOM_GLOSSARY_DEFS, EXTRA_PLACES

    config_dir = script_path.parent / "config"
    if not config_dir.exists():
        return

    emo_file = config_dir / "emotions.json"
    if emo_file.exists():
        try:
            data = json.loads(emo_file.read_text(encoding="utf-8"))
            for entry in data.get("patterns", []):
                if len(entry) >= 4:
                    AFFECT_HEURISTICS.append(tuple(entry[:4]))
            print(f"  ✓ config/emotions.json — {len(data.get('patterns', []))} custom patterns loaded")
        except Exception as e:
            print(f"  ⚠️ config/emotions.json parse error: {e}")

    places_file = config_dir / "places.json"
    if places_file.exists():
        try:
            data = json.loads(places_file.read_text(encoding="utf-8"))
            EXTRA_PLACES = [str(p) for p in data.get("locations", [])]
            print(f"  ✓ config/places.json — {len(EXTRA_PLACES)} custom locations loaded")
        except Exception as e:
            print(f"  ⚠️ config/places.json parse error: {e}")

    wl_file = config_dir / "wordlists.json"
    if wl_file.exists():
        try:
            data = json.loads(wl_file.read_text(encoding="utf-8"))
            added_m = len(data.get("medical", []))
            added_l = len(data.get("legal", []))
            added_t = len(data.get("technical", []))
            MEDICAL_TERMS.update(str(t).lower() for t in data.get("medical", []))
            LEGAL_TERMS.update(str(t).lower() for t in data.get("legal", []))
            TECH_TERMS.update(str(t).lower() for t in data.get("technical", []))
            CUSTOM_GLOSSARY_DEFS = data.get("custom", [])
            print(f"  ✓ config/wordlists.json — medical+{added_m}, legal+{added_l}, "
                  f"tech+{added_t}, custom defs: {len(CUSTOM_GLOSSARY_DEFS)}")
        except Exception as e:
            print(f"  ⚠️ config/wordlists.json parse error: {e}")


AFFECT_HEURISTICS = [
    (r'\b(sorry|apolog|forgive)\b',                            "😟", "Apologetic",   4),
    (r'\b(help|please|desperate|begging|can you)\b',          "😨", "Anxious",       5),
    (r'\b(no|never|won\'t|refuse|absolutely not)\b',          "😠", "Refusing",      6),
    (r'\b(love|wonderful|amazing|great|fantastic|brilliant)\b',"🤩", "Positive",     7),
    (r'\b(don\'t know|not sure|maybe|perhaps|i think)\b',     "🤔", "Uncertain",     4),
    (r'\b(cry|crying|tears|upset|hurt|pain|suffering)\b',     "😢", "Distress",      7),
    (r'\b(laugh|haha|funny|joke|joking|hilarious)\b',         "😄", "Amusement",     5),
    (r'\b(tired|exhausted|can\'t|giving up|done|depleted)\b', "😴", "Depleted",      3),
    (r'\b(angry|furious|rage|unacceptable|outrageous)\b',     "😡", "Furious",       9),
    (r'\b(scared|terrified|afraid|fear|frightened)\b',        "😱", "Fearful",       8),
    (r'\b(confused|lost|don\'t understand|what do you mean)\b',"😕","Confused",      4),
    (r'\b(frustrated|stuck|blocked|can\'t get|won\'t let)\b', "😤", "Frustrated",    6),
]


# ─── Jefferson Paralinguistic Markers ──────────────────────────────────────────
# All ON by default. Each marker type can be disabled via CLI flags.

def detect_jefferson_markers(text: str, pause_before: float, prev_text: str = "") -> list:
    """Detect all Jefferson paralinguistic markers in a text segment.
    Returns list of marker descriptions with their Jefferson notation symbol.
    """
    markers = []

    # CAPS — shouting / strong emphasis (3+ consecutive uppercase words or all-caps words 3+ chars)
    caps_words = re.findall(r'\b[A-Z]{3,}\b', text)
    if caps_words:
        # Filter out common acronyms
        acro_stop = {"NHS", "PIP", "ESA", "DLA", "CBT", "DBT", "EMDR", "ADHD", "ASD", "PTSD", "OCD", "BPD", "GDP", "API", "SDK", "LLM", "GPT", "MCP", "UC", "WCA", "SEN", "EHCP", "CAMHS", "IAPT", "CQC", "DOLS", "LPA", "IMCA", "IMHA", "CPS", "ICO", "SAR", "COPDOL", "PHSO", "LGO"}
        real_caps = [w for w in caps_words if w not in acro_stop]
        if real_caps:
            markers.append({
                "symbol": "WORD",
                "phenomenon": "Shouting / strong emphasis",
                "clinical_note": "Caps = distinctly louder than baseline",
                "words": real_caps,
                "certainty": 0.75,
            })

    # Whisper indicators — low volume, hedging, shame language
    whisper_patterns = [
        (r'\b(quietly|under my breath|whisper|mutter|mumbled)\b', "°word°", "Whisper / quiet speech", "Shame, conspiracy, trauma recall"),
        (r'\b(I dunno|sort of|kind of|ish|maybe just)\b', "°word°", "Hedging / minimising", "Low confidence, shame, or evasion"),
    ]
    for pattern, symbol, phenomenon, note in whisper_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            markers.append({"symbol": symbol, "phenomenon": phenomenon, "clinical_note": note, "certainty": 0.60})

    # Shaky voice — distress indicators in text
    shaky_patterns = [
        (r'\b(crying|tears|sobbing|breaking down|shaking|trembling)\b', "~word~", "Shaky/crying voice", "Diaphragmatic control loss; grief, distress"),
        (r'\b(can\'t breathe|choking up|overwhelmed with emotion)\b', "~word~", "Shaky/crying voice", "Acute emotional dysregulation"),
    ]
    for pattern, symbol, phenomenon, note in shaky_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            markers.append({"symbol": symbol, "phenomenon": phenomenon, "clinical_note": note, "certainty": 0.65})

    # Creaky voice / vocal fry — exhaustion, low arousal
    creaky_patterns = [
        (r'\b(exhausted|drained|burnt out|wrung out|spent|depleted|dead tired)\b', "#word#", "Creaky voice / vocal fry", "Low arousal, exhaustion, confidence collapse"),
        (r'\b(whatever|I suppose|not bothered|don\'t care anymore)\b', "#word#", "Creaky voice / vocal fry", "Resignation, emotional withdrawal"),
    ]
    for pattern, symbol, phenomenon, note in creaky_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            markers.append({"symbol": symbol, "phenomenon": phenomenon, "clinical_note": note, "certainty": 0.55})

    # Prolonged sound — drawn out words
    if re.search(r'\b\w{2,}(?:oo+|aa+|ee+|er+|um+)\b', text, re.IGNORECASE):
        markers.append({"symbol": "word::", "phenomenon": "Prolonged sound", "clinical_note": "Each colon ≈ 0.2s extra duration — emphasis or hesitation", "certainty": 0.60})
    # Also check for repeated letters (e.g. "soooo", "wellll")
    if re.search(r'\b\w*(\w)\1{2,}\w*\b', text) and not re.match(r'^[A-Z]+$', text.strip()):
        markers.append({"symbol": "word::", "phenomenon": "Prolonged sound (repeated letters)", "clinical_note": "Emphasis, emotional elongation", "certainty": 0.55})

    # Pitch spike — panic, shock
    pitch_spike_patterns = [
        (r'[!?]{2,}', "↑↑word", "Extreme pitch spike (exclamation)", "Panic, shock, dysregulation"),
        (r'\b(suddenly|oh my god|what the|no way|are you serious)\b', "↑↑word", "Extreme pitch spike (exclamation)", "Surprise, alarm, dysregulation"),
    ]
    for pattern, symbol, phenomenon, note in pitch_spike_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            markers.append({"symbol": symbol, "phenomenon": phenomenon, "clinical_note": note, "certainty": 0.60})

    # Pitch drop — resignation, defeat
    pitch_drop_patterns = [
        (r'\b(never mind|forget it|it doesn\'t matter|what\'s the point|give up)\b', "↓↓word", "Extreme pitch drop", "Resignation, defeat"),
        (r'\b(I tried|I did my best|nothing works)\b', "↓↓word", "Extreme pitch drop", "Resignation, defeat"),
    ]
    for pattern, symbol, phenomenon, note in pitch_drop_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            markers.append({"symbol": symbol, "phenomenon": phenomenon, "clinical_note": note, "certainty": 0.55})

    # Accelerated delivery — rushed, hurried
    if re.search(r'\b(anyway|so anyway|moving on|next thing|long story short)\b', text, re.IGNORECASE):
        markers.append({"symbol": ">word<", "phenomenon": "Accelerated delivery", "clinical_note": "Hurried, rushed — evasion or anxiety", "certainty": 0.50})

    # Decelerated delivery — deliberate slowing
    if re.search(r'\b(let me be clear|I want to be precise|let me think|how do I put this)\b', text, re.IGNORECASE):
        markers.append({"symbol": "<word>", "phenomenon": "Decelerated delivery", "clinical_note": "Deliberate slowing — careful, possibly deceptive or carefully truthful", "certainty": 0.50})

    # Sharp inbreath — shock, trauma trigger
    if re.search(r'\b(gasp|oh god|jesus|christ|fuck me|bloody hell|oh no)\b', text, re.IGNORECASE):
        markers.append({"symbol": ".hhh", "phenomenon": "Sharp inbreath", "clinical_note": "Shock, trauma trigger, sobbing preparation", "certainty": 0.55})

    # Exhalation — relief, resignation
    if re.search(r'\b(sigh|phew|oh well|there we go|that\'s that)\b', text, re.IGNORECASE):
        markers.append({"symbol": "hhh", "phenomenon": "Exhalation", "clinical_note": "Relief, resignation, or emotional release", "certainty": 0.50})

    # Micropause
    if 0.08 <= pause_before <= 0.2:
        markers.append({"symbol": "(.)", "phenomenon": "Micropause (0.08–0.2s)", "clinical_note": "Brief hesitation or natural turn boundary", "certainty": 0.90})

    # Timed pause
    if 0.2 < pause_before <= 1.5:
        markers.append({"symbol": f"({pause_before:.1f})", "phenomenon": "Timed pause", "clinical_note": "Processing, hesitation, or topic shift", "certainty": 0.88})

    # Significant pause
    if 1.5 < pause_before <= 5:
        markers.append({"symbol": f"({pause_before:.2f})", "phenomenon": "Significant pause (1.5–5s)", "clinical_note": "Emotional processing or topic gravity", "certainty": 0.85})

    # Extended pause / freeze
    if pause_before > 5:
        m_v = int(pause_before // 60)
        s_v = pause_before % 60
        if pause_before > 10:
            markers.append({"symbol": f"({m_v:02d}:{s_v:06.3f})", "phenomenon": "Extended freeze (>10s)", "clinical_note": "PTSD marker, dissociation, emotional shutdown", "certainty": 0.90})
        else:
            markers.append({"symbol": f"({pause_before:.2f})", "phenomenon": "Extended pause (5–10s)", "clinical_note": "Deep emotional processing, possible freeze response", "certainty": 0.88})

    # Question / uncertainty
    if "?" in text:
        markers.append({"symbol": "?", "phenomenon": "Question / uncertainty", "clinical_note": "Seeking information or expressing doubt", "certainty": 0.95})

    # Latching — no gap between turns (if previous text ends abruptly)
    if prev_text and pause_before < 0.08 and pause_before > 0:
        markers.append({"symbol": "=", "phenomenon": "Latching (no gap between turns)", "clinical_note": "Power dynamic, interruption, or urgency", "certainty": 0.70})

    # Overlap — if text starts mid-sentence from previous
    if prev_text and not prev_text.rstrip().endswith(('.', '!', '?', '...')):
        if pause_before < 0.05:
            markers.append({"symbol": "[", "phenomenon": "Possible overlap (simultaneous speech)", "clinical_note": "Competition for turn, or supportive co-construction", "certainty": 0.40})

    # Uncertain transcription — words Whisper may have gotten wrong
    if re.search(r'\b(huh|mm|um|er|uh|hmm)\b', text, re.IGNORECASE):
        markers.append({"symbol": "(word)", "phenomenon": "Uncertain transcription (filler/hesitation)", "clinical_note": "Hesitation, cognitive load, or stalling", "certainty": 0.80})

    return markers


# ─── Deception Indicators ──────────────────────────────────────────────────────

def detect_deception_indicators(text: str, prev_text: str = "") -> list:
    """Detect potential deception markers in a text segment.
    Based on Statement Validity Analysis, Reality Monitoring, and cognitive load theory.
    Each marker carries a certainty score and interpretation note.
    """
    indicators = []

    # False start — sentence abandoned mid-way (<fs>)
    # Pattern: sentence starts, then redirects with a different structure
    false_start_patterns = [
        (r'\b(I was|he was|she was|they were|we were)\b.{1,20}\b(but|actually|no|well|I mean)\b', "false_start", "Sentence abandoned and redirected"),
        (r'\b(I think|I believe|I guess)\b.{1,30}\b(no|actually|well|I mean|rather)\b', "false_start", "Hedged statement then corrected"),
    ]
    for pattern, mtype, note in false_start_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            indicators.append({"type": "false_start", "symbol": "<fs>", "note": note, "certainty": 0.55})

    # Also detect: sentence starts with capital, then dash/ellipsis mid-sentence
    if re.search(r'[A-Z][a-z]+.{2,30}(\.{2,}|—|–)', text):
        indicators.append({"type": "false_start", "symbol": "<fs>", "note": "Sentence abandoned mid-way (dash/ellipsis)", "certainty": 0.50})

    # Spontaneous correction (<corrsp>) — self-correcting a word or phrase
    corrsp_patterns = [
        (r'\b(\w+)\b.{0,5}\b(I mean|I meant|sorry|rather|or rather)\b.{0,5}\b(\w+)\b', "spontaneous_correction", "Word replaced with alternative"),
        (r'\b(\w+)\s*[-–]\s*(\w+)\b', "self_correction_dash", "Word corrected via dash (e.g. 'went–came')"),
    ]
    for pattern, mtype, note in corrsp_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            indicators.append({"type": "spontaneous_correction", "symbol": "<corrsp>", "note": note, "certainty": 0.50})

    # Stalling repetition (<rep n="N">) — repeating a word or phrase 3+ times
    rep_match = re.findall(r'\b(\w{3,})\b(?:\s+\1){2,}', text, re.IGNORECASE)
    if rep_match:
        for word in rep_match:
            count = len(re.findall(r'\b' + re.escape(word) + r'\b', text, re.IGNORECASE))
            indicators.append({
                "type": "stalling_repetition", "symbol": f'<rep n="{count}">{word}</rep>',
                "note": f"Word '{word}' repeated {count} times — stalling for time",
                "certainty": 0.60,
            })

    # Also detect repeated phrases (2+ word phrases)
    phrase_reps = re.findall(r'\b((?:\w+\s+){1,3}\w+)\b(?:\s+\1){1,}', text, re.IGNORECASE)
    for phrase in phrase_reps[:3]:
        indicators.append({
            "type": "stalling_repetition", "symbol": f'<rep>{phrase}</rep>',
            "note": f"Phrase '{phrase}' repeated — possible stalling",
            "certainty": 0.45,
        })

    # Memory disclaimer (<lack-mem>) — claiming not to remember
    lack_mem_patterns = [
        (r'\b(I don\'t remember|I can\'t remember|I don\'t recall|I forget|I\'ve forgotten)\b', "Memory disclaimer — claiming inability to recall"),
        (r'\b(not sure if|I might be wrong|I could be mistaken|if I remember correctly)\b', "Hedged memory — distancing from certainty"),
        (r'\b(I think|I believe|as far as I know|to the best of my recollection)\b', "Qualified memory — weakening commitment to statement"),
        (r'\b(allegedly|apparently|supposedly|they say|I\'m told)\b', "Attribution distancing — removing personal agency"),
    ]
    for pattern, note in lack_mem_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            indicators.append({"type": "memory_disclaimer", "symbol": "<lack-mem>", "note": note, "certainty": 0.55})

    # Excessive detail / over-elaboration (deception: too much detail where not needed)
    words = text.split()
    if len(words) > 40:
        # Check for unnecessary specificity (exact times, exact numbers in casual context)
        over_detail_patterns = [
            (r'\b(at exactly \d|precisely \d|exactly \d|to be specific)\b', "Excessive precision in casual context"),
            (r'\b(as I mentioned before|like I said|as previously stated)\b', "Repetition of already-stated facts (rehearsal indicator)"),
        ]
        for pattern, note in over_detail_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                indicators.append({"type": "over_elaboration", "symbol": "<over-elab>", "note": note, "certainty": 0.40})

    # Defensive language
    defensive_patterns = [
        (r'\b(I didn\'t do it|it wasn\'t me|that\'s not what happened|I would never)\b', "Pre-emptive denial / defensive stance"),
        (r'\b(why would I|what reason would I have|I have no reason to)\b', "Rhetorical defence — challenging the questioner"),
        (r'\b(honestly|to be honest|I swear|believe me|truthfully)\b', "Emphasis on honesty — possible overcompensation"),
        (r'\b(let me be clear|for the record|just to clarify)\b', "Formalised framing — possible rehearsal"),
    ]
    for pattern, note in defensive_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            indicators.append({"type": "defensive_language", "symbol": "<defensive>", "note": note, "certainty": 0.45})

    # Inconsistency markers — contradicting earlier statements
    contradiction_patterns = [
        (r'\b(well actually|that\'s not quite right|let me correct)\b', "Self-correction with contradiction cue"),
    ]
    for pattern, note in contradiction_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            indicators.append({"type": "contradiction", "symbol": "<contradict>", "note": note, "certainty": 0.40})

    # Cognitive load indicators — complex sentences under pressure
    if len(words) > 25:
        clause_count = text.count(',') + text.count(';')
        if clause_count > 4:
            indicators.append({
                "type": "cognitive_load", "symbol": "<cog-load>",
                "note": f"Complex sentence ({clause_count} clauses, {len(words)} words) — high cognitive load for spontaneous speech",
                "certainty": 0.35,
            })

    # Evasion / topic avoidance
    evasion_patterns = [
        (r'\b(anyway|moving on|that\'s in the past|let\'s not go there|I don\'t want to talk about)\b', "Topic avoidance / deflection"),
        (r'\b(what difference does it make|does it matter|it\'s not important)\b', "Minimising / dismissing the topic"),
    ]
    for pattern, note in evasion_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            indicators.append({"type": "evasion", "symbol": "<evade>", "note": note, "certainty": 0.40})

    return indicators


# ─── Veracity / Truthfulness Indicators (reverse of deception) ────────────────

def detect_veracity_indicators(text: str, pause_before: float = 0.0) -> list:
    """Detect truthfulness indicators — the exact reverse of deception.
    Based on Reality Monitoring criteria: genuine memories have more sensory detail,
    contextual embedding, and emotional consistency.
    """
    indicators = []

    # Qualified certainty — appropriately confident (not over- or under-confident)
    certainty_patterns = [
        (r'\b(I\'m certain|I\'m sure|I clearly remember|I know for a fact)\b', "Qualified certainty — appropriate confidence"),
        (r'\b(I saw|I heard|I felt|I was there)\b', "First-person sensory recall — direct experience"),
    ]
    for pattern, note in certainty_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            indicators.append({"type": "qualified_certainty", "symbol": "<veracious>", "note": note, "certainty": 0.65})

    # Sensory detail — genuine memories have more sensory specificity
    sensory_patterns = [
        (r'\b(I could see|I could hear|I could smell|I could feel|I could taste)\b', "Multi-sensory recall — genuine memory"),
        (r'\b(the sound of|the smell of|the feeling of|the taste of)\b', "Sensory specificity — genuine memory"),
        (r'\b(bright|dark|loud|quiet|warm|cold|heavy|light|sharp|dull)\b', "Sensory adjectives — experiential recall"),
    ]
    for pattern, note in sensory_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            indicators.append({"type": "sensory_detail", "symbol": "<sensory-recall>", "note": note, "certainty": 0.60})

    # Temporal sequencing — genuine memories have logical time order
    temporal_patterns = [
        (r'\b(first|then|after that|next|finally|in the end)\b', "Temporal sequencing — structured recall"),
        (r'\b(before|after|while|during|as soon as|once)\b', "Temporal relation — genuine memory structure"),
        (r'\b(in the morning|later that day|the next day|that evening)\b', "Temporal specificity — real memory anchor"),
    ]
    for pattern, note in temporal_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            indicators.append({"type": "temporal_sequencing", "symbol": "<temporal>", "note": note, "certainty": 0.55})

    # Contextual embedding — real memories are connected to time/place/setting
    context_patterns = [
        (r'\b(at \w+\'s house|at the \w+|in the \w+|on the \w+|by the \w+)\b', "Spatial embedding — genuine memory"),
        (r'\b(we were|I was|they were|he was|she was)\b.{0,20}\b(when|while|because|so that)\b', "Contextual embedding — situational recall"),
    ]
    for pattern, note in context_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            indicators.append({"type": "contextual_embedding", "symbol": "<context>", "note": note, "certainty": 0.55})

    # Emotional consistency — genuine emotion matches content
    emotional_consistency_patterns = [
        (r'\b(I was scared|I felt afraid|I was terrified)\b.{0,30}\b(ran|fled|hid|shaking|screaming)\b', "Emotional-behavioural consistency"),
        (r'\b(I was angry|I was furious)\b.{0,30}\b(shouted|screamed|slammed|confronted)\b', "Emotional-behavioural consistency"),
        (r'\b(I was sad|I was heartbroken)\b.{0,30}\b(cried|wept|broke down)\b', "Emotional-behavioural consistency"),
    ]
    for pattern, note in emotional_consistency_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            indicators.append({"type": "emotional_consistency", "symbol": "<emo-consist>", "note": note, "certainty": 0.60})

    # Cognitive complexity — genuine recall includes doubt, self-correction, and nuance
    complexity_patterns = [
        (r'\b(I\'m not entirely sure but|I think maybe|part of me thinks)\b', "Appropriate doubt — genuine recall includes uncertainty"),
        (r'\b(on the other hand|but then again|although|even so)\b', "Cognitive complexity — weighing alternatives"),
        (r'\b(I might be wrong but|correct me if I\'m wrong)\b', "Intellectual humility — confidence without overcompensation"),
    ]
    for pattern, note in complexity_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            indicators.append({"type": "cognitive_complexity", "symbol": "<cog-complex>", "note": note, "certainty": 0.50})

    # Spontaneous detail — unprompted, relevant detail (vs rehearsed)
    if len(text.split()) > 15:
        if re.search(r'\b(suddenly|out of nowhere|I didn\'t expect|it surprised me)\b', text, re.IGNORECASE):
            indicators.append({"type": "spontaneous_detail", "symbol": "<spontaneous>", "note": "Spontaneous reaction detail — genuine recall", "certainty": 0.50})

    # Appropriate pause before recall (thinking, not stalling)
    if 0.5 < pause_before < 3.0:
        # Short pause is normal for genuine recall
        if not re.search(r'\b(um|er|uh|hmm)\b', text, re.IGNORECASE):
            indicators.append({"type": "appropriate_recall_pause", "symbol": "<recall-pause>", "note": f"Natural {pause_before:.1f}s pause before recall — genuine processing", "certainty": 0.40})

    return indicators


# ─── Voice Dynamics Analysis ───────────────────────────────────────────────────

def analyze_voice_dynamics(segments: list, audio_path: Path) -> list:
    """Analyze voice dynamics per segment: raised voice, quiet, whisper, sub-vocal, shaky.
    Uses librosa to extract RMS energy and pitch features per segment.
    Returns a list of per-segment voice dynamics records.
    """
    try:
        import librosa
        import numpy as np
    except ImportError:
        print("  ⚠️ librosa not available — voice dynamics analysis skipped")
        return []

    print("  → Loading audio for voice dynamics analysis...")
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    duration = len(y) / sr

    # Compute global RMS for normalisation
    global_rms = float(np.sqrt(np.mean(y ** 2)))

    dynamics = []
    for seg in segments:
        start = int(seg.get("start", 0) * sr)
        end = int(seg.get("end", 0) * sr)
        clip = y[start:end]
        if len(clip) < sr * 0.05:
            continue

        rms = float(np.sqrt(np.mean(clip ** 2)))
        peak = float(np.max(np.abs(clip)))

        # Pitch via pyin
        f0_mean = 0.0
        f0_std = 0.0
        try:
            f0, voiced, _ = librosa.pyin(clip, fmin=60, fmax=400,
                                          frame_length=2048)
            f0_clean = f0[voiced]
            if len(f0_clean) > 0:
                f0_mean = float(np.nanmean(f0_clean))
                f0_std = float(np.nanstd(f0_clean))
        except Exception:
            pass

        # Classify voice level relative to global RMS
        rms_ratio = rms / global_rms if global_rms > 0 else 1.0

        if rms_ratio > 1.8:
            level = "raised_voice"
            label = "Raised voice / loud"
            cert = 0.75
        elif rms_ratio > 0.8:
            level = "normal"
            label = "Normal volume"
            cert = 0.80
        elif rms_ratio > 0.3:
            level = "quiet"
            label = "Quiet speech"
            cert = 0.70
        elif rms_ratio > 0.1:
            level = "whisper"
            label = "Whispered / very quiet"
            cert = 0.65
        else:
            level = "sub_vocal"
            label = "Sub-vocal / murmured"
            cert = 0.50

        # Shaky voice detection — high pitch variability
        shaky = False
        if f0_std > 60 and f0_mean > 80:
            shaky = True
        # Also check for amplitude instability
        frame_rms = librosa.feature.rms(y=clip, frame_length=512, hop_length=256)[0]
        if len(frame_rms) > 4:
            rms_cv = float(np.std(frame_rms) / (np.mean(frame_rms) + 1e-8))
            if rms_cv > 0.8:
                shaky = True

        # Speaking rate
        word_count = len(seg.get("text", "").split())
        seg_duration = seg.get("end", 0) - seg.get("start", 0)
        rate = word_count / seg_duration if seg_duration > 0 else 0

        entry = {
            "index": seg.get("index", 0),
            "timestamp": fmt_ms(seg.get("start", 0)),
            "speaker": seg.get("speaker", ""),
            "rms_energy": round(rms, 4),
            "rms_ratio_to_global": round(rms_ratio, 3),
            "peak_amplitude": round(peak, 4),
            "f0_mean_hz": round(f0_mean, 1) if f0_mean else None,
            "f0_std_hz": round(f0_std, 1) if f0_std else None,
            "voice_level": level,
            "voice_label": label,
            "certainty": cert,
            "speaking_rate_wps": round(rate, 2) if rate > 0 else None,
        }

        if shaky:
            entry["shaky_voice"] = True
            entry["shaky_label"] = "Shaky/crying voice — pitch or amplitude instability"
            entry["shaky_certainty"] = 0.65

        if level == "raised_voice":
            entry["jefferson"] = "WORD (CAPS)"
        elif level == "whisper":
            entry["jefferson"] = "°word°"
        elif level == "quiet":
            entry["jefferson"] = "°word°"
        elif level == "sub_vocal":
            entry["jefferson"] = "((murmured))"

        dynamics.append(entry)

    return dynamics


# ─── Clinical Markers ─────────────────────────────────────────────────────────

def detect_clinical_markers(text: str, pause_before: float) -> list:
    """Detect clinical phenotype markers: PTSD, ASD, ADHD, and general clinical."""
    markers = []

    # PTSD fragmentation
    ptsd_patterns = [
        (r'\b(the|that)\b.{1,30}\b(the|that)\b.{1,30}\b(the|that)\b', "repetition", "PTSD: Repetitive narrative fragments"),
        (r'\b(I couldn\'t|I can\'t|I didn\'t want to)\b.{1,20}\b(anymore|any more|ever again)\b', "unfinished", "PTSD: Unfinished utterance pattern"),
    ]
    for pattern, mtype, note in ptsd_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            markers.append({"phenotype": "PTSD", "type": mtype, "note": note,
                            "tei": f'<ptsd-frag type="{mtype}">', "certainty": 0.45})

    # Somatic recall
    if re.search(r'\b(felt like|my body|I could feel|in my chest|in my stomach|my hands were)\b', text, re.IGNORECASE):
        markers.append({"phenotype": "PTSD", "type": "somatic", "note": "Visceral sensory recall",
                        "tei": "<somatic>", "certainty": 0.55})

    # Mental defeat
    if re.search(r'\b(I (am|was) (alone|trapped|helpless|worthless|nothing)|nobody (cares|came|helped)|there\'s no (point|hope))\b', text, re.IGNORECASE):
        markers.append({"phenotype": "PTSD", "type": "mental_defeat", "note": "First-person pronoun cluster + hopelessness",
                        "tei": "<mental-defeat>", "certainty": 0.50})

    # ADHD markers
    if re.search(r'\b(anyway|so anyway|where was I|what was I saying|back to|tangent)\b', text, re.IGNORECASE):
        markers.append({"phenotype": "ADHD", "type": "meta_correction", "note": "Self-correction back to topic",
                        "tei": '<meta-correction type="rerail">', "certainty": 0.45})

    # Maze (tangential narrative)
    words = text.split()
    if len(words) > 30:
        topic_shifts = len(re.findall(r'\b(but|so|anyway|and then|oh|also|another thing)\b', text, re.IGNORECASE))
        if topic_shifts > 3:
            markers.append({"phenotype": "ADHD", "type": "maze", "note": f"Tangential narrative ({topic_shifts} topic shifts in {len(words)} words)",
                            "tei": "<maze>", "certainty": 0.40})

    # ASD markers
    if pause_before > 1.0 and pause_before < 5.0:
        # Non-grammatical pause (not at sentence boundary)
        if not text.rstrip().endswith(('.', '!', '?')):
            markers.append({"phenotype": "ASD", "type": "awkward_pause", "note": f"Non-grammatical pause ({pause_before:.1f}s)",
                            "tei": f'<pause dur="{pause_before:.1f}s" type="awkward"/>', "certainty": 0.35})

    return markers


# ─── Helpers ──────────────────────────────────────────────────────────────────

def fmt_hms(seconds: float) -> str:
    """HH:MM:SS.mm"""
    total_s = int(seconds)
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    cs = int((seconds - total_s) * 100)
    return f"{h:02d}:{m:02d}:{s:02d}.{cs:02d}"


def fmt_ms(seconds: float) -> str:
    """MM:SS short form"""
    total_s = int(seconds)
    return f"{total_s // 60:02d}:{total_s % 60:02d}"


# ─── STT ──────────────────────────────────────────────────────────────────────

def transcribe(audio_path: Path, model_size: str = "base", language: str = "en"):
    print(f"Loading Whisper model: {model_size} ...")
    import whisper
    model = whisper.load_model(model_size)
    print(f"Transcribing: {audio_path.name}")
    print("(This may take several minutes for long files — do not close terminal)")
    result = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=True,
        verbose=False,
        initial_prompt="UK English conversation. Personal discussion.",
    )
    return result


# ─── Speaker Diarization ──────────────────────────────────────────────────────

def label_from_cluster(cluster_id: int) -> str:
    return f"Speaker_{cluster_id + 1:02d}"


def diarise_pyannote(audio_path: Path, hf_token: str) -> list:
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        print("ERROR: pip3 install pyannote.audio --break-system-packages  then re-run")
        return []
    import os
    token = hf_token or os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: Set HF_TOKEN from https://huggingface.co/settings/tokens")
        return []
    print("Running pyannote speaker diarization...")
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1",
                                        use_auth_token=token)
    diarization = pipeline(str(audio_path))
    turns = []
    cluster_map = {}
    for turn, _, raw_label in diarization.itertracks(yield_label=True):
        if raw_label not in cluster_map:
            cluster_map[raw_label] = len(cluster_map)
        turns.append({
            "start": turn.start,
            "end": turn.end,
            "speaker": label_from_cluster(cluster_map[raw_label]),
        })
    return turns


def diarise_local(audio_path: Path, n_speakers: int = None) -> list:
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav
        from sklearn.cluster import AgglomerativeClustering
        import numpy as np
    except ImportError:
        print("ERROR: pip3 install resemblyzer scikit-learn --break-system-packages")
        return []

    print("Loading Resemblyzer voice encoder (local, no internet)...")
    encoder = VoiceEncoder()
    print("Preprocessing audio for voice analysis...")
    wav = preprocess_wav(str(audio_path))
    sr = 16000

    print("Extracting voice embeddings per segment...")
    embeddings = []
    valid_indices = []

    window_s = 3.0
    step_s = 1.5
    n_samples = len(wav)
    duration_s = n_samples / sr

    windows = []
    t = 0.0
    while t + window_s <= duration_s:
        start_i = int(t * sr)
        end_i = int((t + window_s) * sr)
        clip = wav[start_i:end_i]
        try:
            embed = encoder.embed_utterance(clip)
            embeddings.append(embed)
            windows.append({"start": t, "end": t + window_s})
        except Exception:
            pass
        t += step_s

    if len(embeddings) < 2:
        print("  ⚠️ Not enough audio for voice clustering — defaulting to Speaker_01")
        return [{"start": 0, "end": duration_s, "speaker": "Speaker_01"}]

    if n_speakers is None:
        n_speakers = min(6, max(2, len(embeddings) // 20))
        print(f"  → Auto-estimating {n_speakers} speakers")

    print(f"  → Clustering voice embeddings into {n_speakers} speaker groups...")
    clustering = AgglomerativeClustering(n_clusters=n_speakers,
                                         metric="cosine",
                                         linkage="average")
    labels = clustering.fit_predict(embeddings)

    turns = []
    for i, window in enumerate(windows):
        turns.append({
            "start": window["start"],
            "end": window["end"],
            "speaker": label_from_cluster(int(labels[i])),
        })

    return turns


def assign_speakers_from_turns(segments: list, speaker_turns: list) -> list:
    if not speaker_turns:
        return segments

    def get_speaker(start: float, end: float) -> str:
        mid = (start + end) / 2
        best = None
        best_overlap = 0.0
        for turn in speaker_turns:
            overlap = min(end, turn["end"]) - max(start, turn["start"])
            if overlap > best_overlap:
                best_overlap = overlap
                best = turn["speaker"]
        return best or "Speaker_01"

    for seg in segments:
        seg["speaker"] = get_speaker(seg["start"], seg["end"])
    return segments


def match_known_voices(audio_path: Path, segments: list,
                       voice_refs: list) -> list:
    if not voice_refs:
        return []
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav
        import numpy as np
    except ImportError:
        print("ERROR: pip3 install resemblyzer --break-system-packages")
        return []

    print("Matching known voices against speaker clusters...")
    encoder = VoiceEncoder()
    sr = 16000
    audio_wav = preprocess_wav(str(audio_path))

    speaker_clip_embeds: dict = {}
    for seg in segments:
        spk = seg.get("speaker", "Speaker_01")
        start_i = int(seg["start"] * sr)
        end_i = int(seg["end"] * sr)
        clip = audio_wav[start_i:end_i]
        if len(clip) < sr * 0.5:
            continue
        try:
            embed = encoder.embed_utterance(clip)
            speaker_clip_embeds.setdefault(spk, []).append(embed)
        except Exception:
            pass

    speaker_avg: dict = {}
    for spk, embeds in speaker_clip_embeds.items():
        speaker_avg[spk] = np.mean(embeds, axis=0)

    results = []
    rename_map: dict = {}

    for ref_path, ref_name in voice_refs:
        ref_path = Path(ref_path)
        if not ref_path.exists():
            print(f"  ⚠️ Reference file not found: {ref_path}")
            continue
        print(f"  → Matching '{ref_name}' from {ref_path.name}...")
        ref_wav = preprocess_wav(str(ref_path))
        ref_embed = encoder.embed_utterance(ref_wav)

        similarities = {}
        for spk, avg_embed in speaker_avg.items():
            norm = np.linalg.norm(ref_embed) * np.linalg.norm(avg_embed)
            sim = float(np.dot(ref_embed, avg_embed) / norm) if norm > 0 else 0.0
            similarities[spk] = round(sim, 3)

        if not similarities:
            continue

        best_spk = max(similarities, key=similarities.get)
        best_sim = similarities[best_spk]
        cert = round(min(0.95, max(0.20, best_sim)), 2)

        if best_sim >= 0.60 and best_spk not in rename_map:
            rename_map[best_spk] = ref_name
            print(f"     ✅ {best_spk} → '{ref_name}' [C:{cert:.2f}]")
        else:
            flag = "⚠️ low confidence — not renamed" if best_sim < 0.60 else "⚠️ already matched"
            print(f"     {flag}: best match {best_spk} @ {best_sim:.3f}")

        results.append({
            "reference_name": ref_name,
            "reference_file": str(ref_path),
            "best_match_speaker": best_spk,
            "renamed_to": rename_map.get(best_spk),
            "similarity_score": best_sim,
            "certainty": cert,
            "all_similarities": similarities,
            "note": "similarity >0.60 = confident match" if best_sim >= 0.60
                    else "⚠️ similarity <0.60 — verify before trusting",
        })

    if rename_map:
        for seg in segments:
            old = seg.get("speaker", "")
            if old in rename_map:
                seg["speaker"] = rename_map[old]
        print(f"  → Speaker labels updated: {rename_map}")

    return results


# ─── Glossary Detection ───────────────────────────────────────────────────────

def detect_glossary_terms(segments: list) -> list:
    full_text = " ".join(s.get("text", "") for s in segments)
    entries = []
    seen = set()
    gid = 0

    def first_time(term):
        pat = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
        for seg in segments:
            if pat.search(seg.get("text", "")):
                return seg.get("start", 0)
        return 0

    def add(term, category, definition, certainty):
        nonlocal gid
        key = term.lower().strip()
        if key in seen:
            return
        seen.add(key)
        gid += 1
        entries.append({
            "id": gid,
            "term": term,
            "category": category,
            "definition": definition,
            "certainty": certainty,
            "first_appears_at": fmt_ms(first_time(term)),
        })

    trivial = {"I", "UK", "US", "TV", "OK", "AM", "PM", "GP"}
    for m in re.finditer(r'\b([A-Z]{2,5})\b', full_text):
        ac = m.group(1)
        if ac not in trivial:
            add(ac, "acronym", "Acronym — definition unknown; please fill in", 0.55)

    for term in MEDICAL_TERMS:
        if re.search(r'\b' + re.escape(term) + r'\b', full_text, re.IGNORECASE):
            add(term, "medical/clinical",
                "Medical or clinical term — see NHS guidance or professional definition", 0.82)

    for term in LEGAL_TERMS:
        if re.search(r'\b' + re.escape(term) + r'\b', full_text, re.IGNORECASE):
            add(term, "legal",
                "Legal or regulatory term — consult solicitor or official guidance", 0.82)

    for term in TECH_TERMS:
        if re.search(r'\b' + re.escape(term) + r'\b', full_text, re.IGNORECASE):
            add(term, "technical", "Technical/digital term", 0.78)

    drug_re = re.compile(
        r'\b([A-Za-z]{3,}(?:ol|ine|mab|nib|stat|pril|sartan|azole|mycin|cillin))\b',
        re.IGNORECASE
    )
    for m in drug_re.finditer(full_text):
        term = m.group(1)
        if term.lower() not in seen:
            add(term, "medication",
                "Possible medication — verify: dosage, purpose, side effects", 0.65)

    for m in re.finditer(r'\b(?:like|as)\s+(?:a|an|the)\s+(\w+)', full_text, re.IGNORECASE):
        phrase = f"like a {m.group(1)}"
        if phrase.lower() not in seen:
            add(phrase, "metaphor/simile",
                "Figurative expression — contextual interpretation may be needed", 0.45)

    for entry in CUSTOM_GLOSSARY_DEFS:
        if not isinstance(entry, dict):
            continue
        term = entry.get("term", "")
        if not term:
            continue
        if re.search(r'\b' + re.escape(term) + r'\b', full_text, re.IGNORECASE):
            add(term,
                entry.get("category", "custom"),
                entry.get("definition", "Custom term — see config/wordlists.json"),
                0.90)

    return entries


def build_term_index(glossary: list) -> dict:
    return {e["term"].lower(): e["id"] for e in glossary}


def mark_glossary_inline(text: str, term_index: dict, already_marked: set) -> tuple:
    result = text
    for term_lower, gid in sorted(term_index.items(), key=lambda x: -len(x[0])):
        if term_lower in already_marked:
            continue
        pat = re.compile(r'\b(' + re.escape(term_lower) + r')\b', re.IGNORECASE)
        if pat.search(result):
            result = pat.sub(rf'\1[G:{gid}]', result, count=1)
            already_marked.add(term_lower)
    return result, already_marked


# ─── Things (Entities) ────────────────────────────────────────────────────────

def extract_things(segments: list, speaker_hints: list) -> dict:
    full_text = " ".join(s.get("text", "") for s in segments)

    people = []
    seen_people = set()
    for hint in speaker_hints:
        count = len(re.findall(r'\b' + re.escape(hint) + r'\b', full_text, re.IGNORECASE))
        if count and hint.lower() not in seen_people:
            seen_people.add(hint.lower())
            people.append({"name": hint, "certainty": 0.95, "occurrences": count,
                           "source": "known_speaker"})

    stop = {
        "monday","tuesday","wednesday","thursday","friday","saturday","sunday",
        "january","february","march","april","may","june","july","august",
        "september","october","november","december","ok","yeah","nhs","the",
        "i","we","you","he","she","it","they","this","that","there","those",
        "these","then","also","just","well","right","really","actually",
        "so","but","and","or","if","when","where","what","how","why","who",
    }
    for name in set(re.findall(r'\b([A-Z][a-z]{2,})\b', full_text)):
        if name.lower() in stop or name.lower() in seen_people:
            continue
        count = len(re.findall(r'\b' + re.escape(name) + r'\b', full_text))
        cert = round(min(0.82, 0.35 + count * 0.09), 2)
        if cert >= 0.40:
            seen_people.add(name.lower())
            people.append({"name": name, "certainty": cert, "occurrences": count,
                           "source": "heuristic",
                           "flag": "⚠️ verify" if cert < 0.70 else None})

    extra = "|".join(re.escape(p.lower()) for p in EXTRA_PLACES) if EXTRA_PLACES else ""
    extra_part = ("|" + extra) if extra else ""
    loc_pat = (r'\b(hospital|clinic|surgery|school|park|station|court|council|ward|'
               r'office|flat|street|road|london|barnet|finchley|hackney|islington|'
               r'camden|enfield|haringey|brent|ealing|hounslow|richmond|croydon|'
               r'bromley|lewisham|greenwich|newham|waltham' + extra_part + r')\b')
    places = []
    for m in set(re.findall(loc_pat, full_text, re.IGNORECASE)):
        count = len(re.findall(r'\b' + re.escape(m) + r'\b', full_text, re.IGNORECASE))
        places.append({"place": m, "certainty": 0.70, "occurrences": count})

    dates = []
    date_patterns = [
        (r'\b(\d{1,2}[\/\-\.]\\d{1,2}[\/\-\.]\\d{2,4})\b', "absolute"),
        (r'\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:january|february|march|april|may|june|'
         r'july|august|september|october|november|december)(?:\s+\\d{4})?)\b', "absolute"),
        (r'\b(yesterday|today|tomorrow|last\s+\w+|next\s+\w+|this\s+\w+)\b', "relative"),
    ]
    seen_dates = set()
    for pat, dtype in date_patterns:
        for m in re.findall(pat, full_text, re.IGNORECASE):
            val = m if isinstance(m, str) else m[0]
            if val.lower() not in seen_dates:
                seen_dates.add(val.lower())
                dates.append({"value": val, "type": dtype, "certainty": 0.88})

    times = []
    seen_times = set()
    for m in re.findall(
        r'\b(\d{1,2}:\d{2}(?:\s*[aApP][mM])?|\d{1,2}\s*(?:o\'?clock|am|pm))\b',
        full_text, re.IGNORECASE
    ):
        if m.lower() not in seen_times:
            seen_times.add(m.lower())
            times.append({"value": m, "certainty": 0.85})

    return {
        "people": sorted(people, key=lambda x: -x["certainty"]),
        "places": sorted(places, key=lambda x: -x["certainty"]),
        "dates": dates,
        "times": times,
    }


# ─── Emotions (Enhanced with all indicators) ──────────────────────────────────

def build_emotions(segments: list, env_events: list, acoustic: list, room: list,
                   enable_jefferson: bool = True, enable_deception: bool = True,
                   enable_veracity: bool = True, enable_clinical: bool = True,
                   enable_emotional: bool = True) -> dict:
    emotion_segments = []
    pauses = []
    freeze_events = []
    prev_end = 0.0
    prev_text = ""

    all_deception = []
    all_veracity = []
    all_clinical = []

    for i, seg in enumerate(segments):
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "").strip()
        speaker = seg.get("speaker", "Speaker")
        pause_before = max(0.0, round(start - prev_end, 2))

        # Pause detection
        if pause_before > 10:
            freeze_events.append({
                "timestamp": fmt_ms(prev_end),
                "duration_s": pause_before,
                "type": "extended_freeze",
                "certainty": 0.90,
                "note": "🚨 >10s silence — probable emotional freeze",
            })
        elif pause_before > 5:
            pauses.append({"timestamp": fmt_ms(prev_end), "duration_s": pause_before,
                           "type": "significant", "certainty": 0.88})
        elif pause_before > 1.5:
            pauses.append({"timestamp": fmt_ms(prev_end), "duration_s": pause_before,
                           "type": "notable", "certainty": 0.85})

        # Affect heuristics
        emoji = "😐"
        affect = "Neutral"
        intensity = 5
        if enable_emotional:
            for pattern, em, label, inten in AFFECT_HEURISTICS:
                if re.search(pattern, text, re.IGNORECASE):
                    emoji = em
                    affect = label
                    intensity = inten
                    break

        has_caps = bool(re.search(r'\b[A-Z]{3,}\b', text))
        if has_caps:
            intensity = min(10, intensity + 2)
            if affect == "Neutral":
                emoji = "😠"
                affect = "Raised voice / emphasis"

        # Jefferson markers (all, enhanced)
        jefferson_markers = []
        if enable_jefferson:
            jefferson_markers = detect_jefferson_markers(text, pause_before, prev_text)

        # Deception indicators
        deception_markers = []
        if enable_deception:
            deception_markers = detect_deception_indicators(text, prev_text)
            if deception_markers:
                all_deception.extend([{"segment_index": i, "timestamp": fmt_ms(start), **d} for d in deception_markers])

        # Veracity indicators
        veracity_markers = []
        if enable_veracity:
            veracity_markers = detect_veracity_indicators(text, pause_before)
            if veracity_markers:
                all_veracity.extend([{"segment_index": i, "timestamp": fmt_ms(start), **v} for v in veracity_markers])

        # Clinical markers
        clinical_markers = []
        if enable_clinical:
            clinical_markers = detect_clinical_markers(text, pause_before)
            if clinical_markers:
                all_clinical.extend([{"segment_index": i, "timestamp": fmt_ms(start), **c} for c in clinical_markers])

        seg_entry = {
            "index": i,
            "timestamp": fmt_ms(start),
            "start_s": round(start, 2),
            "end_s": round(end, 2),
            "speaker": speaker,
            "text_preview": text[:100] + ("…" if len(text) > 100 else ""),
            "pause_before_s": pause_before,
            "intensity": intensity,
            "emoji": emoji,
            "affect_label": affect,
            "has_raised_voice": has_caps,
            "has_question": "?" in text,
            "jefferson_markers": jefferson_markers,
            "deception_markers": deception_markers,
            "veracity_markers": veracity_markers,
            "clinical_markers": clinical_markers,
            "certainty": 0.65,
        }

        emotion_segments.append(seg_entry)
        prev_end = end
        prev_text = text

    return {
        "total_segments": len(segments),
        "freeze_events": freeze_events,
        "significant_pauses": pauses,
        "environmental_events": [
            {"timestamp": e["time"], "type": e.get("type", e.get("likely", "?")),
             "duration_s": e["duration_s"], "certainty": e["certainty"]}
            for e in (env_events + acoustic + room)
        ],
        "segments": emotion_segments,
        "deception_indicators": all_deception,
        "veracity_indicators": all_veracity,
        "clinical_markers": all_clinical,
        "summary": {
            "total_deception_markers": len(all_deception),
            "total_veracity_markers": len(all_veracity),
            "total_clinical_markers": len(all_clinical),
            "freeze_events_count": len(freeze_events),
            "significant_pauses_count": len(pauses),
            "jefferson_enabled": enable_jefferson,
            "deception_enabled": enable_deception,
            "veracity_enabled": enable_veracity,
            "clinical_enabled": enable_clinical,
            "emotional_enabled": enable_emotional,
        },
    }


# ─── ffmpeg Scans ─────────────────────────────────────────────────────────────

def run_ffmpeg(audio_path: Path, af_filter: str) -> str:
    r = subprocess.run(
        ["ffmpeg", "-i", str(audio_path), "-af", af_filter, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return r.stderr


def detect_environmental_ffmpeg(audio_path: Path) -> list:
    raw = run_ffmpeg(audio_path,
                     "bandpass=f=1000:width_type=o:width=3,silencedetect=noise=-35dB:d=3.0")
    events = []
    ends = re.findall(r'silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)', raw)
    starts = re.findall(r'silence_start: ([0-9.]+)', raw)
    for i, (end, dur) in enumerate(ends):
        d = float(dur)
        if d > 5:
            start_s = float(starts[i]) if i < len(starts) else float(end) - d
            cert = round(min(0.75, 0.45 + d / 60), 2)
            events.append({
                "time": fmt_hms(start_s), "time_s": start_s,
                "duration_s": round(d, 1), "type": "music/radio/TV",
                "certainty": cert,
                "tei": f'<incident type="sustained_audio" desc="music/radio/TV?" dur="{d:.1f}s" cert="{cert:.2f}"/>',
            })
    return events


def detect_acoustic_events_ffmpeg(audio_path: Path) -> list:
    raw = run_ffmpeg(audio_path,
                     "compand=attacks=0.01:decays=0.01:points=-90/-60|-60/-20|0/0,"
                     "silencedetect=noise=-15dB:d=0.05")
    events = []
    for end_s, dur_s in re.findall(
        r'silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)', raw
    ):
        d = float(dur_s)
        if d < 0.5:
            t = float(end_s) - d
            events.append({
                "time": fmt_hms(t), "time_s": t,
                "duration_s": round(d, 2), "type": "transient_event",
                "likely": "car horn / door slam / alarm", "certainty": 0.52,
                "tei": f'<incident type="acoustic_event" desc="transient" dur="{d:.2f}s" cert="0.52"/>',
            })
    return events[:20]


def detect_room_changes_ffmpeg(audio_path: Path) -> list:
    raw = run_ffmpeg(audio_path,
                     "bandpass=f=300:width_type=h:width=400,silencedetect=noise=-25dB:d=0.05")
    events = []
    last_t = -10.0
    for end_s, dur_s in re.findall(
        r'silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)', raw
    ):
        d = float(dur_s)
        t = float(end_s) - d
        if 0.05 < d < 0.4 and (t - last_t) > 2.0:
            events.append({
                "time": fmt_hms(t), "time_s": t,
                "duration_s": round(d, 3), "type": "possible_door_event",
                "certainty": 0.46,
                "tei": '<incident type="door_event" desc="possible entry/exit?" cert="0.46"/>',
                "note": "⚠️ verify — short mid-band burst",
            })
            last_t = t
    return events[:15]


# ─── Noteworthy ───────────────────────────────────────────────────────────────

def build_noteworthy(emotions: dict, env_events: list, acoustic: list,
                     room: list, things: dict, glossary: list) -> list:
    items = []

    for fe in emotions["freeze_events"]:
        items.append({
            "type": "freeze", "timestamp": fe["timestamp"],
            "duration_s": fe["duration_s"], "certainty": fe["certainty"],
            "note": fe["note"],
            "action": "Listen to content immediately before + after — key emotional moment",
        })

    for p in sorted(emotions["significant_pauses"], key=lambda x: -x["duration_s"])[:5]:
        items.append({
            "type": "significant_pause", "timestamp": p["timestamp"],
            "duration_s": p["duration_s"], "certainty": p["certainty"],
            "note": "Sustained silence — emotional processing or topic gravity",
        })

    for e in room:
        items.append({
            "type": "possible_room_change", "timestamp": e["time"],
            "certainty": e["certainty"],
            "note": "Possible door/entry/exit event",
            "action": "⚠️ Shenanigans Watch — verify who was present before/after",
        })

    for e in env_events:
        items.append({
            "type": "environmental_audio", "timestamp": e["time"],
            "duration_s": e["duration_s"], "certainty": e["certainty"],
            "note": f"Possible {e['type']} — may affect transcript accuracy nearby",
        })

    # Deception flags
    for d in emotions.get("deception_indicators", []):
        items.append({
            "type": f"deception_{d.get('type', 'unknown')}",
            "timestamp": d.get("timestamp", ""),
            "certainty": d.get("certainty", 0.5),
            "note": f"DECEPTION: {d.get('note', '')} [{d.get('symbol', '')}]",
            "action": "Review context — single indicator is not proof of deception",
        })

    # Veracity positives
    for v in emotions.get("veracity_indicators", []):
        items.append({
            "type": f"veracity_{v.get('type', 'unknown')}",
            "timestamp": v.get("timestamp", ""),
            "certainty": v.get("certainty", 0.5),
            "note": f"VERACITY: {v.get('note', '')} [{v.get('symbol', '')}]",
        })

    # Clinical markers
    for c in emotions.get("clinical_markers", []):
        items.append({
            "type": f"clinical_{c.get('phenotype', 'unknown')}",
            "timestamp": c.get("timestamp", ""),
            "certainty": c.get("certainty", 0.4),
            "note": f"CLINICAL ({c.get('phenotype', '')}): {c.get('note', '')} [{c.get('tei', '')}]",
        })

    for p in things.get("people", []):
        if p["certainty"] < 0.60:
            items.append({
                "type": "uncertain_entity", "value": p["name"],
                "certainty": p["certainty"],
                "note": f"Person name '{p['name']}' low-confidence — verify",
            })

    for g in glossary:
        if g["category"] == "acronym":
            items.append({
                "type": "undefined_acronym", "term": g["term"],
                "glossary_id": g["id"],
                "first_appears_at": g["first_appears_at"],
                "note": f"Acronym needs definition → glossary.json entry {g['id']}",
            })

    return sorted(items, key=lambda x: x.get("timestamp", "99:99"))


# ─── Hashtags ─────────────────────────────────────────────────────────────────

def generate_hashtags(things: dict, segments: list, context_type: str) -> list:
    tags = set()
    if context_type:
        tags.add(f"#{context_type.replace('-', '_')}")
    full_text = " ".join(s.get("text", "") for s in segments).lower()
    topic_map = {
        "nhs": "#NHS", "hospital": "#hospital", "doctor": "#medical",
        "care": "#care", "social worker": "#socialcare",
        "mental health": "#mentalhealth", "money": "#finance",
        "rent": "#housing", "council": "#council", "family": "#family",
        "mum": "#family", "dad": "#family", "work": "#work",
        "school": "#education", "police": "#police",
        "court": "#legal", "solicitor": "#legal", "dream": "#dream",
        "therapy": "#therapy", "medication": "#medication",
    }
    for keyword, tag in topic_map.items():
        if keyword in full_text:
            tags.add(tag)
    for person in things.get("people", [])[:3]:
        if person["certainty"] >= 0.70:
            tags.add(f"#{person['name'].replace(' ', '_')}")
    return sorted(tags)


# ─── Transcript MD (Enhanced with all inline markers) ──────────────────────────

def build_transcript_md(segments: list, emotions_data: dict,
                        glossary: list, audio_path: Path,
                        voice_dynamics: list = None) -> str:
    term_index = build_term_index(glossary)
    already_marked: set = set()
    em_by_index = {e["index"]: e for e in emotions_data["segments"]}
    vd_by_index = {v["index"]: v for v in voice_dynamics} if voice_dynamics else {}

    lines = [
        f"# Transcript: {audio_path.name}",
        "",
        "| File | Contents |",
        "|------|----------|",
        "| [emotions.json](emotions.json) | Per-segment emotion, intensity, emoji, pauses |",
        "| [things.json](things.json) | People, places, dates, times |",
        "| [meta.json](meta.json) | Recording metadata, speakers, hashtags |",
        "| [glossary.json](glossary.json) | Terms marked `[G:N]` in this transcript |",
        "| [noteworthy.json](noteworthy.json) | Freezes, room changes, uncertainties |",
        "| [omni.md](omni.md) | EVERYTHING — all views, all indicators, all markers |",
        "| [analysis.json](analysis.json) | Structured deception/veracity/voice/clinical data |",
        "",
        "> `[G:N]` after a word → see entry N in glossary.json",
        "> `[C:0.00–1.00]` certainty — below 0.70 is ⚠️ verify",
        "> Jefferson markers shown inline: WORD=shout, °word°=whisper, ~word~=shaky, #word#=creaky",
        "> word::=prolonged, ↑↑=pitch spike, ↓↓=pitch drop, >word<=fast, <word>=slow",
        "> Deception: <fs>=false start, <corrsp>=correction, <rep>=repetition, <lack-mem>=memory lapse",
        "> Veracity: <veracious>=certainty, <sensory-recall>=sensory, <temporal>=sequencing",
        "",
        "---",
        "",
    ]

    prev_end = 0.0
    prev_speaker = None

    for i, seg in enumerate(segments):
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "").strip()
        speaker = seg.get("speaker", "Speaker")
        em = em_by_index.get(i, {})
        vd = vd_by_index.get(i, {})
        pause_before = max(0.0, start - prev_end)

        # Pause markers
        if pause_before > 10:
            m_v = int(pause_before // 60)
            s_v = pause_before % 60
            lines.append(f"\n`({m_v:02d}:{s_v:06.3f})` 🚨 **EXTENDED FREEZE**\n")
        elif pause_before > 5:
            lines.append(f"\n`({pause_before:.2f})` ⚠️ significant pause\n")
        elif pause_before > 1.5:
            lines.append(f"\n`({pause_before:.2f})`\n")
        elif 0.08 <= pause_before <= 0.2:
            lines.append(f"\n`(.)`\n")

        # Speaker header
        if speaker != prev_speaker:
            emoji = em.get("emoji", "😐")
            affect = em.get("affect_label", "Neutral")
            intensity = em.get("intensity", 5)
            # Add voice level to header
            voice_info = ""
            if vd:
                vl = vd.get("voice_level", "")
                if vl and vl != "normal":
                    voice_info = f" [{vd.get('voice_label', '')}]"
            lines.append(
                f"\n**[{fmt_ms(start)}] {{{speaker}}} "
                f"[{emoji} {affect} : {intensity}/10]{voice_info} [C:0.70]:**"
            )
            prev_speaker = speaker
        else:
            lines.append(f"[{fmt_ms(start)}]")

        # Inline glossary marks
        marked_text, already_marked = mark_glossary_inline(text, term_index, already_marked)

        # Add inline deception/veracity markers AFTER the text
        deco_markers = em.get("deception_markers", [])
        ver_markers = em.get("veracity_markers", [])
        clin_markers = em.get("clinical_markers", [])

        lines.append(marked_text)

        # Inline indicator annotations
        annotations = []
        for d in deco_markers:
            annotations.append(f"  ⚠️ DECEPTION: {d.get('note', '')} {d.get('symbol', '')} [C:{d.get('certainty', 0.5):.2f}]")
        for v in ver_markers:
            annotations.append(f"  ✓ VERACITY: {v.get('note', '')} {v.get('symbol', '')} [C:{v.get('certainty', 0.5):.2f}]")
        for c in clin_markers:
            annotations.append(f"  🏥 CLINICAL: {c.get('note', '')} {c.get('tei', '')} [C:{c.get('certainty', 0.4):.2f}]")

        # Jefferson markers summary
        jf_markers = em.get("jefferson_markers", [])
        if jf_markers:
            jf_summary = ", ".join(f"{m['symbol']} ({m['phenomenon']})" for m in jf_markers[:5])
            annotations.append(f"  📝 JEFFERSON: {jf_summary}")

        if annotations:
            for a in annotations:
                lines.append(a)

        prev_end = end

    lines += [
        "",
        "---",
        "",
        "## Glossary Quick Reference",
        "",
        "| [G:N] | Term | Category | First at |",
        "|-------|------|----------|----------|",
    ]
    for entry in glossary:
        lines.append(
            f"| [G:{entry['id']}] | {entry['term']} "
            f"| {entry['category']} | {entry['first_appears_at']} |"
        )

    lines += [
        "",
        "---",
        f"_Generated by Emotion Audio Analyser v3.0_",
        f"_All Jefferson markers ON | Deception indicators ON | Veracity indicators ON | Voice dynamics ON_",
        f"_Paste transcript.md into Claude with the `emotion-audio-analyser` skill for full annotation_",
    ]
    return "\n".join(lines)


# ─── Omni Output (single comprehensive file with EVERYTHING) ──────────────────

def build_omni_md(segments: list, emotions_data: dict, things: dict,
                  glossary: list, noteworthy: list, voice_dynamics: list,
                  meta: dict, audio_path: Path, config_summary: dict,
                  cost_estimate: dict) -> str:
    """Build omni.md — a single comprehensive markdown file containing EVERYTHING:
    - Full annotated transcript with all inline markers
    - Emotion timeline
    - Deception indicator matrix
    - Veracity indicator matrix
    - Voice dynamics report
    - Clinical markers report
    - Environmental events log
    - Entity register
    - Speaker manifest
    - Noteworthy items
    - Glossary
    - Acoustic-prosodic summary
    - Cost/token estimate
    - Config summary
    """
    em_by_index = {e["index"]: e for e in emotions_data["segments"]}
    vd_by_index = {v["index"]: v for v in voice_dynamics} if voice_dynamics else {}

    lines = [
        f"# OMNI OUTPUT — {audio_path.name}",
        "",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
        f"_Schema: Affective-Clinical-MD v3.0 (Omni)_",
        f"_All indicators ON by default — see config summary below_",
        "",
        "---",
        "",
        "## Table of Contents",
        "1. [Recording Metadata](#recording-metadata)",
        "2. [Cost & Token Estimate](#cost--token-estimate)",
        "3. [Entity Register](#entity-register)",
        "4. [Speaker Manifest](#speaker-manifest)",
        "5. [Emotion Timeline](#emotion-timeline)",
        "6. [Deception Indicator Matrix](#deception-indicator-matrix)",
        "7. [Veracity Indicator Matrix](#veracity-indicator-matrix)",
        "8. [Voice Dynamics Report](#voice-dynamics-report)",
        "9. [Clinical Markers Report](#clinical-markers-report)",
        "10. [Jefferson Paralinguistic Markers](#jefferson-paralinguistic-markers)",
        "11. [Environmental Events Log](#environmental-events-log)",
        "12. [Noteworthy Items](#noteworthy-items)",
        "13. [Full Annotated Transcript](#full-annotated-transcript)",
        "14. [Glossary](#glossary)",
        "15. [Configuration Summary](#configuration-summary)",
        "",
        "---",
        "",
    ]

    # ── 1. Recording Metadata ──
    lines += [
        "## Recording Metadata",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| File | {meta.get('audio_file', '')} |",
        f"| Duration | {meta.get('duration_formatted', '')} ({meta.get('duration_s', 0)}s) |",
        f"| Whisper model | {meta.get('whisper_model', '')} |",
        f"| Language | {meta.get('language', '')} |",
        f"| Context | {meta.get('context_type', '')} |",
        f"| Schema | {meta.get('schema_version', '')} |",
        f"| Privacy | {'✅ Local only' if meta.get('wispr_privacy_mode') else '⚠️ Unknown'} |",
        f"| Segments | {meta.get('segment_count', 0)} |",
        f"| Words | {meta.get('word_count', 0)} |",
        f"| Hashtags | {' '.join(meta.get('hashtags', []))} |",
        "",
    ]

    # ── 2. Cost & Token Estimate ──
    lines += [
        "## Cost & Token Estimate",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Estimated words | {cost_estimate.get('estimated_words', '?')} |",
        f"| Estimated tokens | {cost_estimate.get('estimated_tokens', '?')} |",
        f"| Model used | {cost_estimate.get('model', '?')} |",
        f"| Est. processing time | {cost_estimate.get('estimated_process_minutes', '?')} min |",
        f"| Cost (local Whisper) | ${cost_estimate.get('cost_usd', 0):.2f} |",
        f"| Note | {cost_estimate.get('note', '')} |",
        "",
        "**Token Min-Maxing Tips:**",
        "- Use `--auto-model` to auto-select Whisper model based on duration",
        "- For batch processing, split long files and use `tiny` for drafts, `base` for final",
        "- Sub-agents can process different files in parallel with different models",
        "- Cloud LLM annotation pass costs ~$0.01-0.05 per transcript via OpenRouter",
        "",
    ]

    # ── 3. Entity Register ──
    lines += [
        "## Entity Register",
        "",
        "| Entity | Type | [C:] | Occurrences | Notes |",
        "|--------|------|------|-------------|-------|",
    ]
    for p in things.get("people", []):
        flag = p.get("flag", "") or ""
        lines.append(f"| {p['name']} | Person | [C:{p['certainty']:.2f}] | {p['occurrences']} | {p.get('source', '')} {flag} |")
    for pl in things.get("places", []):
        lines.append(f"| {pl['place']} | Place | [C:{pl['certainty']:.2f}] | {pl['occurrences']} | |")
    for d in things.get("dates", []):
        lines.append(f"| {d['value']} | Date ({d['type']}) | [C:{d['certainty']:.2f}] | | |")
    for t in things.get("times", []):
        lines.append(f"| {t['value']} | Time | [C:{t['certainty']:.2f}] | | |")
    lines.append("")

    # ── 4. Speaker Manifest ──
    lines += [
        "## Speaker Manifest",
        "",
        f"| Speaker | Method |",
        f"|---------|--------|",
    ]
    dia = meta.get("diarization", {})
    for spk in dia.get("speaker_labels", []):
        lines.append(f"| {spk} | {dia.get('method', 'unknown')} |")
    for vm in dia.get("voice_matching", []):
        renamed = vm.get("renamed_to", "")
        if renamed:
            lines.append(f"| → renamed to: {renamed} | matched: {vm['best_match_speaker']} [C:{vm['certainty']:.2f}] |")
    lines.append("")

    # ── 5. Emotion Timeline ──
    lines += [
        "## Emotion Timeline",
        "",
        "| Time | Speaker | Emoji | Affect | Intensity | Pauses | Question | Raised |",
        "|------|---------|-------|--------|-----------|--------|----------|--------|",
    ]
    for seg in emotions_data["segments"]:
        lines.append(
            f"| {seg['timestamp']} | {seg['speaker']} | {seg['emoji']} | {seg['affect_label']} "
            f"| {seg['intensity']}/10 | {seg['pause_before_s']:.1f}s | "
            f"{'?' if seg['has_question'] else ''} | "
            f"{'⚠️' if seg['has_raised_voice'] else ''} |"
        )
    lines.append("")

    # Emotion distribution
    affects = {}
    for seg in emotions_data["segments"]:
        label = seg["affect_label"]
        affects[label] = affects.get(label, 0) + 1
    lines += [
        "### Emotion Distribution",
        "",
        "| Affect | Count | % |",
        "|--------|-------|---|",
    ]
    total = sum(affects.values()) or 1
    for label, count in sorted(affects.items(), key=lambda x: -x[1]):
        lines.append(f"| {label} | {count} | {count/total*100:.0f}% |")
    lines.append("")

    # ── 6. Deception Indicator Matrix ──
    all_deception = emotions_data.get("deception_indicators", [])
    lines += [
        "## Deception Indicator Matrix",
        "",
        f"**Total deception indicators detected: {len(all_deception)}**",
        "",
    ]
    if all_deception:
        # Group by type
        by_type = {}
        for d in all_deception:
            t = d.get("type", "unknown")
            by_type.setdefault(t, []).append(d)

        lines += [
            "| Type | Symbol | Count | Avg Certainty | Examples |",
            "|------|--------|-------|---------------|----------|",
        ]
        for dtype, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
            avg_cert = sum(i.get("certainty", 0.5) for i in items) / len(items)
            examples = "; ".join(i.get("note", "")[:60] for i in items[:3])
            sym = items[0].get("symbol", "")
            lines.append(f"| {dtype} | {sym} | {len(items)} | [C:{avg_cert:.2f}] | {examples} |")
        lines.append("")

        lines += [
            "### Deception Indicators Detail",
            "",
            "| Time | Type | Note | Symbol | [C:] |",
            "|------|------|------|--------|------|",
        ]
        for d in all_deception:
            lines.append(f"| {d.get('timestamp', '')} | {d.get('type', '')} | {d.get('note', '')} | {d.get('symbol', '')} | [C:{d.get('certainty', 0.5):.2f}] |")
        lines.append("")
    else:
        lines += ["_No deception indicators detected._", ""]

    lines += [
        "> ⚠️ **IMPORTANT**: Deception indicators are NOT proof of deception. They are patterns",
        "> that *may* indicate cognitive load, rehearsal, or evasive behaviour. Single indicators",
        "> are meaningless — look for clusters and patterns. Always consider context, baseline",
        "> behaviour, and alternative explanations. These are heuristic text-pattern matches, not",
        "> voice-stress analysis or scientific deception detection.",
        "",
    ]

    # ── 7. Veracity Indicator Matrix ──
    all_veracity = emotions_data.get("veracity_indicators", [])
    lines += [
        "## Veracity Indicator Matrix",
        "",
        f"**Total veracity indicators detected: {len(all_veracity)}**",
        "",
    ]
    if all_veracity:
        by_type = {}
        for v in all_veracity:
            t = v.get("type", "unknown")
            by_type.setdefault(t, []).append(v)

        lines += [
            "| Type | Symbol | Count | Avg Certainty | Examples |",
            "|------|--------|-------|---------------|----------|",
        ]
        for vtype, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
            avg_cert = sum(i.get("certainty", 0.5) for i in items) / len(items)
            examples = "; ".join(i.get("note", "")[:60] for i in items[:3])
            sym = items[0].get("symbol", "")
            lines.append(f"| {vtype} | {sym} | {len(items)} | [C:{avg_cert:.2f}] | {examples} |")
        lines.append("")

        lines += [
            "### Veracity Indicators Detail",
            "",
            "| Time | Type | Note | Symbol | [C:] |",
            "|------|------|------|--------|------|",
        ]
        for v in all_veracity:
            lines.append(f"| {v.get('timestamp', '')} | {v.get('type', '')} | {v.get('note', '')} | {v.get('symbol', '')} | [C:{v.get('certainty', 0.5):.2f}] |")
        lines.append("")
    else:
        lines += ["_No veracity indicators detected._", ""]

    # Deception vs Veracity ratio
    deco_count = len(all_deception)
    ver_count = len(all_veracity)
    total_indicators = deco_count + ver_count
    if total_indicators > 0:
        deco_pct = deco_count / total_indicators * 100
        ver_pct = ver_count / total_indicators * 100
        lines += [
            "### Deception vs Veracity Balance",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Deception indicators | {deco_count} ({deco_pct:.0f}%) |",
            f"| Veracity indicators | {ver_count} ({ver_pct:.0f}%) |",
            f"| Ratio (veracity:deception) | {ver_count/max(deco_count,1):.1f}:1 |",
            f"| Interpretation | {'More veracity signals — likely truthful overall' if ver_pct > 60 else 'More deception signals — review carefully' if deco_pct > 60 else 'Balanced — inconclusive from indicators alone'} |",
            "",
        ]

    return "\n".join(lines)


    # ── 8. Voice Dynamics Report ──
    lines += [
        "## Voice Dynamics Report",
        "",
    ]
    if voice_dynamics:
        # Summary stats
        levels = {}
        shaky_count = 0
        for vd in voice_dynamics:
            level = vd.get("voice_level", "unknown")
            levels[level] = levels.get(level, 0) + 1
            if vd.get("shaky_voice"):
                shaky_count += 1

        lines += [
            "### Voice Level Distribution",
            "",
            "| Level | Count | % | Jefferson |",
            "|-------|-------|---|-----------|",
        ]
        total_vd = len(voice_dynamics) or 1
        jf_map = {"raised_voice": "WORD (CAPS)", "normal": "—", "quiet": "°word°",
                  "whisper": "°word°", "sub_vocal": "((murmured))"}
        for level in ["raised_voice", "normal", "quiet", "whisper", "sub_vocal"]:
            count = levels.get(level, 0)
            if count:
                lines.append(f"| {level.replace('_', ' ').title()} | {count} | {count/total_vd*100:.0f}% | {jf_map.get(level, '')} |")
        lines.append("")

        if shaky_count:
            lines += [f"**Shaky/crying voice detected in {shaky_count} segments** (~{shaky_count/total_vd*100:.0f}%)\n"]

        lines += [
            "### Voice Dynamics Detail",
            "",
            "| Time | Speaker | Level | RMS | F0 Mean | F0 Std | Rate | Shaky |",
            "|------|---------|-------|-----|---------|--------|------|-------|",
        ]
        for vd in voice_dynamics:
            shaky = "⚠️ yes" if vd.get("shaky_voice") else ""
            f0m = f"{vd['f0_mean_hz']:.0f}Hz" if vd.get("f0_mean_hz") else "—"
            f0s = f"{vd['f0_std_hz']:.0f}Hz" if vd.get("f0_std_hz") else "—"
            rate = f"{vd['speaking_rate_wps']:.1f}w/s" if vd.get("speaking_rate_wps") else "—"
            lines.append(f"| {vd['timestamp']} | {vd['speaker']} | {vd['voice_label']} | {vd['rms_energy']:.4f} | {f0m} | {f0s} | {rate} | {shaky} |")
        lines.append("")
    else:
        lines += ["_Voice dynamics analysis not available (librosa may not be installed)._\n"]

    # ── 9. Clinical Markers Report ──
    all_clinical = emotions_data.get("clinical_markers", [])
    lines += [
        "## Clinical Markers Report",
        "",
        f"**Total clinical markers detected: {len(all_clinical)}**",
        "",
    ]
    if all_clinical:
        by_phenotype = {}
        for c in all_clinical:
            ph = c.get("phenotype", "unknown")
            by_phenotype.setdefault(ph, []).append(c)

        for ph, items in sorted(by_phenotype.items()):
            lines += [f"### {ph} Markers ({len(items)} detected)", ""]
            lines += [
                "| Time | Type | Note | TEI | [C:] |",
                "|------|------|------|-----|------|",
            ]
            for c in items:
                lines.append(f"| {c.get('timestamp', '')} | {c.get('type', '')} | {c.get('note', '')} | {c.get('tei', '')} | [C:{c.get('certainty', 0.4):.2f}] |")
            lines.append("")
    else:
        lines += ["_No clinical markers detected._", ""]

    # ── 10. Jefferson Paralinguistic Markers ──
    lines += [
        "## Jefferson Paralinguistic Markers",
        "",
    ]
    all_jf = {}
    for seg in emotions_data["segments"]:
        for jf in seg.get("jefferson_markers", []):
            sym = jf.get("symbol", "")
            all_jf.setdefault(sym, {"count": 0, "phenomenon": jf.get("phenomenon", ""), "clinical": jf.get("clinical_note", "")})
            all_jf[sym]["count"] += 1

    if all_jf:
        lines += [
            "| Symbol | Phenomenon | Count | Clinical Note |",
            "|--------|-----------|-------|---------------|",
        ]
        for sym, info in sorted(all_jf.items(), key=lambda x: -x[1]["count"]):
            lines.append(f"| `{sym}` | {info['phenomenon']} | {info['count']} | {info['clinical']} |")
        lines.append("")
    else:
        lines += ["_No Jefferson markers detected._", ""]

    # ── 11. Environmental Events Log ──
    lines += [
        "## Environmental Events Log",
        "",
    ]
    env_events = emotions_data.get("environmental_events", [])
    if env_events:
        lines += [
            "| Time | Duration | Type | [C:] |",
            "|------|----------|------|------|",
        ]
        for e in env_events[:30]:
            lines.append(f"| {e.get('timestamp', '')} | {e.get('duration_s', '')}s | {e.get('type', '')} | [C:{e.get('certainty', 0.5):.2f}] |")
        if len(env_events) > 30:
            lines.append(f"| ... | ... | _{len(env_events) - 30} more events_ | |")
        lines.append("")
    else:
        lines += ["_No environmental events detected._", ""]

    # Freeze events
    if emotions_data.get("freeze_events"):
        lines += [
            "### 🚨 Freeze Events (>10s silence)",
            "",
            "| Time | Duration | [C:] | Note |",
            "|------|----------|------|------|",
        ]
        for fe in emotions_data["freeze_events"]:
            lines.append(f"| {fe['timestamp']} | {fe['duration_s']}s | [C:{fe['certainty']:.2f}] | {fe['note']} |")
        lines.append("")

    # ── 12. Noteworthy Items ──
    lines += [
        "## Noteworthy Items",
        "",
        f"**Total noteworthy items: {len(noteworthy)}**",
        "",
    ]
    if noteworthy:
        # Group by type
        by_type = {}
        for item in noteworthy:
            t = item.get("type", "unknown")
            by_type.setdefault(t, []).append(item)

        for ntype, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
            icon = "🚨" if "freeze" in ntype else "⚠️" if "deception" in ntype else "✓" if "veracity" in ntype else "🏥" if "clinical" in ntype else "🔍"
            lines += [f"### {icon} {ntype.replace('_', ' ').title()} ({len(items)})", ""]
            lines += [
                "| Time | [C:] | Note |",
                "|------|------|------|",
            ]
            for item in items[:20]:
                lines.append(f"| {item.get('timestamp', '')} | [C:{item.get('certainty', 0.5):.2f}] | {item.get('note', '')} |")
            if len(items) > 20:
                lines.append(f"| ... | | _{len(items) - 20} more items_ |")
            lines.append("")
    else:
        lines += ["_No noteworthy items._", ""]

    # ── 13. Full Annotated Transcript ──
    lines += [
        "## Full Annotated Transcript",
        "",
        "---",
        "",
    ]

    prev_end = 0.0
    prev_speaker = None
    for i, seg in enumerate(segments):
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "").strip()
        speaker = seg.get("speaker", "Speaker")
        em = em_by_index.get(i, {})
        vd = vd_by_index.get(i, {})
        pause_before = max(0.0, start - prev_end)

        if pause_before > 10:
            m_v = int(pause_before // 60)
            s_v = pause_before % 60
            lines.append(f"\n`({m_v:02d}:{s_v:06.3f})` 🚨 **EXTENDED FREEZE**\n")
        elif pause_before > 5:
            lines.append(f"\n`({pause_before:.2f})` ⚠️ significant pause\n")
        elif pause_before > 1.5:
            lines.append(f"\n`({pause_before:.2f})`\n")
        elif 0.08 <= pause_before <= 0.2:
            lines.append(f"\n`(.)`\n")

        if speaker != prev_speaker:
            emoji = em.get("emoji", "😐")
            affect = em.get("affect_label", "Neutral")
            intensity = em.get("intensity", 5)
            voice_info = ""
            if vd and vd.get("voice_level", "normal") != "normal":
                voice_info = f" [{vd.get('voice_label', '')}]"
            lines.append(
                f"\n**[{fmt_ms(start)}] {{{speaker}}} "
                f"[{emoji} {affect} : {intensity}/10]{voice_info} [C:0.70]:**"
            )
            prev_speaker = speaker
        else:
            lines.append(f"[{fmt_ms(start)}]")

        lines.append(text)

        # All inline annotations
        for d in em.get("deception_markers", []):
            lines.append(f"  ⚠️ DECEPTION: {d.get('note', '')} {d.get('symbol', '')} [C:{d.get('certainty', 0.5):.2f}]")
        for v in em.get("veracity_markers", []):
            lines.append(f"  ✓ VERACITY: {v.get('note', '')} {v.get('symbol', '')} [C:{v.get('certainty', 0.5):.2f}]")
        for c in em.get("clinical_markers", []):
            lines.append(f"  🏥 CLINICAL: {c.get('note', '')} {c.get('tei', '')} [C:{c.get('certainty', 0.4):.2f}]")
        jf_list = em.get("jefferson_markers", [])
        if jf_list:
            jf_summary = ", ".join(f"{m['symbol']} ({m['phenomenon']})" for m in jf_list[:5])
            lines.append(f"  📝 JEFFERSON: {jf_summary}")

        prev_end = end

    # ── 14. Glossary ──
    lines += [
        "",
        "---",
        "",
        "## Glossary",
        "",
        "| [G:N] | Term | Category | Definition | First at | [C:] |",
        "|-------|------|----------|------------|----------|------|",
    ]
    for entry in glossary:
        lines.append(
            f"| [G:{entry['id']}] | {entry['term']} | {entry['category']} "
            f"| {entry['definition']} | {entry['first_appears_at']} | [C:{entry['certainty']:.2f}] |"
        )
    lines.append("")

    # ── 15. Configuration Summary ──
    lines += [
        "---",
        "",
        "## Configuration Summary",
        "",
        f"| Option | Status |",
        f"|--------|--------|",
    ]
    summary = emotions_data.get("summary", {})
    for key in ["jefferson_enabled", "deception_enabled", "veracity_enabled",
                 "clinical_enabled", "emotional_enabled"]:
        status = "✅ ON" if summary.get(key, True) else "❌ OFF"
        lines.append(f"| {key} | {status} |")

    lines += [
        f"| voice_dynamics | {'✅ ON' if voice_dynamics else '⚠️ unavailable'} |",
        f"| omni_output | ✅ ON |",
        f"| auto_model | {'✅ ' + cost_estimate.get('model', '') if config_summary.get('auto_model') else '❌ manual'} |",
        "",
        "---",
        "",
        "_Generated by Emotion Audio Analyser v3.0 — Omni Output_",
        "_All indicators, all markers, all views — in one file._",
    ]

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

class MatchVoiceAction(argparse.Action):
    """Custom action to collect --match-voice pairs: path name"""
    def __call__(self, parser, namespace, values, option_string=None):
        items = getattr(namespace, self.dest, None) or []
        items.append(tuple(values))
        setattr(namespace, self.dest, items)


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio → structured analysis folder (v3.0 — Omni)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("audio", help="Path to audio file (m4a/mp3/wav/etc.)")
    parser.add_argument("--model", default="base",
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Whisper model size (default: base)")
    parser.add_argument("--auto-model", action="store_true",
                        help="Auto-select Whisper model based on audio duration (token min-maxing)")
    parser.add_argument("--language", default="en",
                        help="Language code (default: en)")
    parser.add_argument("--context", default="general",
                        help="Context type label (default: general)")
    parser.add_argument("--output-dir", default="",
                        help="Where to create output folder (default: current dir)")

    # Speaker diarization
    diar_group = parser.add_mutually_exclusive_group()
    diar_group.add_argument("--diarise-local", action="store_true",
                             help="Local voice clustering via Resemblyzer (no internet, no token)")
    diar_group.add_argument("--diarise", action="store_true",
                             help="Speaker diarization via pyannote.audio (requires HuggingFace token)")

    parser.add_argument("--hf-token", default="",
                        help="HuggingFace token for --diarise (or set HF_TOKEN env var)")
    parser.add_argument("--n-speakers", type=int, default=None,
                        help="Expected number of speakers (optional — auto-detected if omitted)")
    parser.add_argument("--match-voice", nargs=2, metavar=("AUDIO_PATH", "NAME"),
                        action=MatchVoiceAction, dest="voice_refs",
                        help="Match a known voice clip to a speaker label. Repeatable.")
    parser.add_argument("--subfolder-suffix", default="_subfile",
                        help="Suffix to append to the audio filename for the output subfolder (default: _subfile)")
    parser.add_argument("--no-copy-audio", dest="copy_audio", action="store_false",
                        help="Do not copy the original audio file into the output folder")
    parser.add_argument("--no-viewer", dest="generate_viewer", action="store_false",
                        help="Do not generate the embedded HTML viewer in the output folder")

    # Omni output (ON by default)
    parser.add_argument("--omni", dest="generate_omni", action="store_true", default=True,
                        help="Generate omni.md (comprehensive single-file output) — DEFAULT ON")
    parser.add_argument("--no-omni", dest="generate_omni", action="store_false",
                        help="Skip omni.md generation")

    # Feature toggles (all ON by default)
    parser.add_argument("--no-jefferson", dest="enable_jefferson", action="store_false", default=True,
                        help="Disable Jefferson paralinguistic marker detection")
    parser.add_argument("--no-deception", dest="enable_deception", action="store_false", default=True,
                        help="Disable deception indicator detection")
    parser.add_argument("--no-veracity", dest="enable_veracity", action="store_false", default=True,
                        help="Disable truthfulness/veracity indicator detection")
    parser.add_argument("--no-voice-dynamics", dest="enable_voice_dynamics", action="store_false", default=True,
                        help="Disable voice dynamics analysis (raised voice, whisper, etc.)")
    parser.add_argument("--no-clinical", dest="enable_clinical", action="store_false", default=True,
                        help="Disable clinical marker detection (PTSD/ASD/ADHD)")
    parser.add_argument("--no-emotional", dest="enable_emotional", action="store_false", default=True,
                        help="Disable emotional analysis (affect heuristics)")

    # Cost estimation
    parser.add_argument("--estimate-cost", action="store_true",
                        help="Print token/cost estimation before running")

    args = parser.parse_args()

    # Load user config
    script_path = Path(__file__).resolve()
    print("Loading config...")
    load_config(script_path)

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"ERROR: File not found: {audio_path}")
        sys.exit(1)

    if args.voice_refs and not (args.diarise or args.diarise_local):
        print("WARNING: --match-voice requires --diarise or --diarise-local. "
              "Enabling --diarise-local automatically.")
        args.diarise_local = True

    # ── Get audio duration for model selection ──
    print("\nChecking audio duration...")
    try:
        import librosa
        duration_s = librosa.get_duration(path=str(audio_path))
    except Exception:
        # Fallback: use ffprobe
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
                capture_output=True, text=True
            )
            duration_s = float(r.stdout.strip()) if r.stdout.strip() else 0
        except Exception:
            duration_s = 0

    print(f"  Duration: {fmt_ms(duration_s) if duration_s else 'unknown'} ({duration_s:.0f}s)")

    # ── Auto model selection ──
    if args.auto_model and duration_s > 0:
        selected = auto_select_model(duration_s)
        print(f"  → Auto-selected model: {selected} (based on {duration_s:.0f}s duration)")
        args.model = selected

    # ── Cost estimation ──
    cost = estimate_tokens(duration_s, args.model)
    if args.estimate_cost:
        print(f"\n  Cost Estimate:")
        print(f"    Model: {cost['model']}")
        print(f"    Est. words: {cost['estimated_words']}")
        print(f"    Est. tokens: {cost['estimated_tokens']}")
        print(f"    Est. processing time: {cost['estimated_process_minutes']} min")
        print(f"    Cost: ${cost['cost_usd']:.2f} (local Whisper is free)")
        print()

    # Output folder
    base_dir = Path(args.output_dir) if args.output_dir else audio_path.parent
    out_folder = base_dir / (audio_path.stem + str(args.subfolder_suffix))
    out_folder.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput folder: {out_folder}\n")

    # ── Transcribe ──
    result = transcribe(audio_path, model_size=args.model, language=args.language)
    segments = result.get("segments", [])

    # ── Speaker Diarization ──
    voice_match_results = []
    diarization_method = "none (Whisper turn heuristics only)"

    if args.diarise_local:
        print("\nRunning local voice clustering (Resemblyzer)...")
        turns = diarise_local(audio_path, n_speakers=args.n_speakers)
        if turns:
            segments = assign_speakers_from_turns(segments, turns)
            result["segments"] = segments
            diarization_method = "Resemblyzer local clustering (no internet)"

    elif args.diarise:
        print("\nRunning pyannote speaker diarization...")
        turns = diarise_pyannote(audio_path, args.hf_token)
        if turns:
            segments = assign_speakers_from_turns(segments, turns)
            result["segments"] = segments
            diarization_method = "pyannote.audio (HuggingFace)"

    # ── Voice Matching ──
    if args.voice_refs:
        print("\nRunning voice matching against reference clips...")
        voice_match_results = match_known_voices(audio_path, segments, args.voice_refs)
        result["segments"] = segments

    discovered_speakers = sorted(set(s.get("speaker", "Speaker_01") for s in segments))

    # ── Environment Scans ──
    print("\nScanning audio...")
    print("  → Environmental audio (music/radio/AI)...")
    env_events = detect_environmental_ffmpeg(audio_path)
    print("  → Acoustic events (horns/slams/alarms)...")
    acoustic = detect_acoustic_events_ffmpeg(audio_path)
    print("  → Room changes (door events)...")
    room = detect_room_changes_ffmpeg(audio_path)

    # ── Voice Dynamics ──
    voice_dynamics = []
    if args.enable_voice_dynamics:
        print("\nAnalyzing voice dynamics (raised voice, whisper, shaky voice)...")
        voice_dynamics = analyze_voice_dynamics(segments, audio_path)
        if voice_dynamics:
            raised = sum(1 for v in voice_dynamics if v.get("voice_level") == "raised_voice")
            quiet = sum(1 for v in voice_dynamics if v.get("voice_level") in ("quiet", "whisper"))
            shaky = sum(1 for v in voice_dynamics if v.get("shaky_voice"))
            print(f"  → {raised} raised voice, {quiet} quiet/whisper, {shaky} shaky voice segments")

    # ── Build Structured Data ──
    print("\nBuilding analysis...")
    print("  → Extracting entities...")
    things = extract_things(segments, discovered_speakers)
    print("  → Detecting glossary terms...")
    glossary = detect_glossary_terms(segments)
    print("  → Building emotions + all indicators...")
    emotions = build_emotions(segments, env_events, acoustic, room,
                              enable_jefferson=args.enable_jefferson,
                              enable_deception=args.enable_deception,
                              enable_veracity=args.enable_veracity,
                              enable_clinical=args.enable_clinical,
                              enable_emotional=args.enable_emotional)
    print(f"  → {emotions['summary']['total_deception_markers']} deception, "
          f"{emotions['summary']['total_veracity_markers']} veracity, "
          f"{emotions['summary']['total_clinical_markers']} clinical markers")
    print("  → Building noteworthy items...")
    noteworthy = build_noteworthy(emotions, env_events, acoustic, room, things, glossary)
    hashtags = generate_hashtags(things, segments, args.context)

    # ── Meta ──
    duration_s_final = segments[-1]["end"] if segments else duration_s
    meta = {
        "audio_file": audio_path.name,
        "audio_path": str(audio_path),
        "duration_s": round(duration_s_final, 1),
        "duration_formatted": fmt_ms(duration_s_final),
        "transcription_timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "whisper_model": args.model,
        "language": result.get("language", args.language),
        "context_type": args.context,
        "schema_version": "Affective-Clinical-MD-v3.0-Omni",
        "wispr_privacy_mode": True,
        "diarization": {
            "method": diarization_method,
            "n_speakers_detected": len(discovered_speakers),
            "speaker_labels": discovered_speakers,
            "voice_matching": voice_match_results,
            "note": "Speaker labels are discovered automatically — names are not assumed.",
        },
        "segment_count": len(segments),
        "word_count": len(result.get("text", "").split()),
        "hashtags": hashtags,
        "output_folder": str(out_folder),
        "output_files": [
            "transcript.md", "emotions.json", "things.json",
            "meta.json", "glossary.json", "noteworthy.json",
            "omni.md", "analysis.json",
        ],
        "features_enabled": {
            "jefferson": args.enable_jefferson,
            "deception": args.enable_deception,
            "veracity": args.enable_veracity,
            "voice_dynamics": args.enable_voice_dynamics,
            "clinical": args.enable_clinical,
            "emotional": args.enable_emotional,
            "omni": args.generate_omni,
        },
        "cost_estimate": cost,
    }

    # ── Build outputs ──
    print("  → Building transcript.md...")
    transcript_md = build_transcript_md(segments, emotions, glossary, audio_path, voice_dynamics)

    # ── Write Files ──
    print("\nWriting files...")
    outputs = {
        "transcript.md":   transcript_md,
        "emotions.json":   json.dumps(emotions, indent=2, ensure_ascii=False),
        "things.json":     json.dumps(things, indent=2, ensure_ascii=False),
        "meta.json":       json.dumps(meta, indent=2, ensure_ascii=False),
        "glossary.json":   json.dumps({"entries": glossary}, indent=2, ensure_ascii=False),
        "noteworthy.json": json.dumps({"items": noteworthy}, indent=2, ensure_ascii=False),
    }

    # Analysis.json — structured indicator data
    analysis_data = {
        "deception_indicators": emotions.get("deception_indicators", []),
        "veracity_indicators": emotions.get("veracity_indicators", []),
        "clinical_markers": emotions.get("clinical_markers", []),
        "voice_dynamics": voice_dynamics,
        "jefferson_summary": {},
        "summary": emotions.get("summary", {}),
        "cost_estimate": cost,
    }
    # Jefferson summary
    for seg in emotions.get("segments", []):
        for jf in seg.get("jefferson_markers", []):
            sym = jf.get("symbol", "")
            if sym not in analysis_data["jefferson_summary"]:
                analysis_data["jefferson_summary"][sym] = {"count": 0, "phenomenon": jf.get("phenomenon", "")}
            analysis_data["jefferson_summary"][sym]["count"] += 1

    outputs["analysis.json"] = json.dumps(analysis_data, indent=2, ensure_ascii=False)

    # Omni output
    if args.generate_omni:
        print("  → Building omni.md (comprehensive single-file output)...")
        config_summary = {
            "auto_model": args.auto_model,
            "jefferson": args.enable_jefferson,
            "deception": args.enable_deception,
            "veracity": args.enable_veracity,
            "voice_dynamics": args.enable_voice_dynamics,
            "clinical": args.enable_clinical,
            "emotional": args.enable_emotional,
        }
        omni_md = build_omni_md(segments, emotions, things, glossary, noteworthy,
                                voice_dynamics, meta, audio_path, config_summary, cost)
        outputs["omni.md"] = omni_md

    for filename, content_str in outputs.items():
        (out_folder / filename).write_text(content_str, encoding="utf-8")
        print(f"  ✅ {filename}")

    # Copy audio
    try:
        if args.copy_audio:
            dest_audio = out_folder / audio_path.name
            if not dest_audio.exists():
                shutil.copy2(audio_path, dest_audio)
                print(f"  ✅ copied audio: {dest_audio.name}")
    except Exception as e:
        print(f"  ⚠️ could not copy audio: {e}")

    # ── Generate HTML viewer (optional) ──
    if getattr(args, "generate_viewer", True):
        try:
            segments_json = json.dumps(segments, ensure_ascii=False)
            emotions_json = outputs.get("emotions.json", "{}")
            things_json = outputs.get("things.json", "{}")
            glossary_json = outputs.get("glossary.json", "{}")
            noteworthy_json = outputs.get("noteworthy.json", "{}")
            meta_json = outputs.get("meta.json", "{}")
            transcript_text = transcript_md.replace("</script>", "</scr" + "ipt>")

            viewer_html = """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Emotion Audio Viewer — {audio_name}</title>
    <style>
        body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin:0; height:100vh; display:flex; flex-direction:column; }}
        #top {{ padding:8px; display:flex; gap:8px; align-items:center; background:#1a1a2e; color:#fff; }}
        #timeline {{ height:120px; background:#111; color:#fff; position:relative; display:flex; align-items:center; padding:10px; }}
        #timeline .bar {{ position:relative; height:8px; background:#333; width:100%; border-radius:4px; }}
        .marker {{ position:absolute; top:6px; width:8px; height:8px; background:#ffcc00; border-radius:50%; transform:translateX(-50%); cursor:pointer; }}
        #controls {{ display:flex; gap:8px; align-items:center; }}
        #transcript {{ height:50vh; overflow:auto; border-top:1px solid #ddd; padding:12px; }}
        .segment {{ padding:6px 0; border-bottom:1px dashed #eee; }}
        .timestamp {{ color:#666; margin-right:8px; cursor:pointer; }}
        .deception {{ background:#ffe0e0; padding:2px 4px; border-radius:3px; }}
        .veracity {{ background:#e0ffe0; padding:2px 4px; border-radius:3px; }}
    </style>
</head>
<body>
    <div id="top">
        <div id="controls">
            <button id="play">Play</button>
            <button id="pause">Pause</button>
            <label>Zoom: <input type="range" id="zoom" min="1" max="10" value="3" /></label>
            <span id="time">00:00 / 00:00</span>
        </div>
    </div>
    <div id="timeline"><div class="bar" id="bar"></div></div>
    <div id="transcript"></div>
    <audio id="audio" controls style="width:0;height:0;opacity:0;position:fixed;left:-9999px;" src="{audio_name}"></audio>
    <script>
        const segments = {SEGMENTS_JSON_PLACEHOLDER};
        const emotions = {EMOTIONS_JSON_PLACEHOLDER};
        const noteworthy = {NOTEWORTHY_JSON_PLACEHOLDER};
        const meta = {META_JSON_PLACEHOLDER};
        const audio = document.getElementById('audio');
        const bar = document.getElementById('bar');
        const tEl = document.getElementById('transcript');
        segments.forEach(s => {
            const d = document.createElement('div'); d.className='segment';
            const ts = document.createElement('span'); ts.className='timestamp';
            const mm = Math.floor(s.start/60).toString().padStart(2,'0');
            const ss = Math.floor(s.start%60).toString().padStart(2,'0');
            ts.textContent = `[${mm}:${ss}]`;
            ts.onclick = () => { audio.currentTime = s.start; audio.play(); };
            d.appendChild(ts);
            const txt = document.createElement('span'); txt.textContent = ` {${s.get('speaker','')}} ${s.get('text','')}`;
            d.appendChild(txt);
            tEl.appendChild(d);
        });
        document.getElementById('play').onclick = () => audio.play();
        document.getElementById('pause').onclick = () => audio.pause();
        audio.ontimeupdate = () => {
            const cur = audio.currentTime||0, dur = audio.duration||meta.duration_s||0;
            const mm = Math.floor(cur/60).toString().padStart(2,'0');
            const ss = Math.floor(cur%60).toString().padStart(2,'0');
            const dmm = Math.floor(dur/60).toString().padStart(2,'0');
            const dss = Math.floor(dur%60).toString().padStart(2,'0');
            document.getElementById('time').textContent = `${mm}:${ss} / ${dmm}:${dss}`;
        };
        function renderMarkers() {
            bar.innerHTML='';
            const dur = audio.duration || meta.duration_s || 0;
            segments.forEach(s => {
                const el = document.createElement('div'); el.className='marker';
                el.style.left = (s.start / dur * 100) + '%';
                el.title = `${s.start.toFixed(1)}s`;
                el.onclick = (e) => { e.stopPropagation(); audio.currentTime = s.start; audio.play(); };
                bar.appendChild(el);
            });
        }
        audio.onloadedmetadata = () => { renderMarkers(); };
    </script>
</body>
</html>"""

            viewer_html = viewer_html.replace('{SEGMENTS_JSON_PLACEHOLDER}', segments_json)
            viewer_html = viewer_html.replace('{EMOTIONS_JSON_PLACEHOLDER}', emotions_json)
            viewer_html = viewer_html.replace('{NOTEWORTHY_JSON_PLACEHOLDER}', noteworthy_json)
            viewer_html = viewer_html.replace('{META_JSON_PLACEHOLDER}', meta_json)
            viewer_html = viewer_html.replace('{audio_name}', audio_path.name)

            (out_folder / "viewer.html").write_text(viewer_html, encoding="utf-8")
            print("  ✅ viewer.html")
        except Exception as e:
            print(f"  ⚠️ could not generate viewer: {e}")

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"✅ Done — {len(outputs)} files in:")
    print(f"   {out_folder}")
    print(f"\n   Speakers detected: {', '.join(discovered_speakers)}")
    print(f"   Segments: {len(segments)}")
    summary = emotions.get("summary", {})
    print(f"   Deception indicators: {summary.get('total_deception_markers', 0)}")
    print(f"   Veracity indicators: {summary.get('total_veracity_markers', 0)}")
    print(f"   Clinical markers: {summary.get('total_clinical_markers', 0)}")
    print(f"   Freeze events: {summary.get('freeze_events_count', 0)}")
    if voice_dynamics:
        raised = sum(1 for v in voice_dynamics if v.get("voice_level") == "raised_voice")
        quiet = sum(1 for v in voice_dynamics if v.get("voice_level") in ("quiet", "whisper"))
        print(f"   Voice dynamics: {raised} raised, {quiet} quiet/whisper")
    print(f"   Cost: ${cost['cost_usd']:.2f} | Est. tokens: {cost['estimated_tokens']}")
    print(f"\n   📂 omni.md contains EVERYTHING — all views, all indicators")
    print(f"   📂 analysis.json has structured indicator data")
    print(f"\n   Next: paste transcript.md into Claude with the emotion-audio-analyser skill")
    print(f"         for full Jefferson/TEI/CHAT annotation and clinical analysis.")


if __name__ == "__main__":
    main()
