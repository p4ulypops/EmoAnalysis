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

    config_dir = script_path.parent.parent / "config"
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
    # ── High arousal negative ──────────────────────────────────────────────────
    (r'\b(angry|furious|rage|livid|unacceptable|outrageous|how dare)\b',         "😡", "Furious",       9),
    (r'\b(scared|terrified|afraid|fear|frightened|panic|petrified)\b',           "😱", "Fearful",       8),
    (r'\b(frustrated|stuck|blocked|can\'t get|won\'t let|fed up|sick of)\b',     "😤", "Frustrated",    6),
    (r'\b(cry|crying|tears|sobbing|breaking down|wept|weeping)\b',               "😭", "Grief",         8),
    (r'\b(upset|hurt|wounded|heartbroken|devastated|shattered|broken)\b',        "💔", "Heartbroken",   7),
    (r'\b(betrayed|lied to|deceived|stabbed|let down|abandoned)\b',              "😔", "Betrayed",      7),
    (r'\b(shock|shocked|disbelief|can\'t believe|jaw drop|stunned)\b',           "😲", "Shocked",       7),
    (r'\b(embarrass|ashamed|humiliat|mortif|cringe|pathetic)\b',                 "😳", "Embarrassed",   5),
    (r'\b(guilt|guilty|to blame|my fault|i should have|i failed)\b',             "😞", "Guilty",        5),
    (r'\b(disgust|revolting|disgusting|nauseating|sick)\b',                      "🤢", "Disgusted",     6),
    # ── High arousal positive ──────────────────────────────────────────────────
    (r'\b(love|adore|wonderful|amazing|fantastic|brilliant|incredible)\b',       "🤩", "Elated",        8),
    (r'\b(laugh|haha|funny|hilarious|joke|cracking up|chuckl)\b',                "😂", "Amused",        6),
    (r'\b(excit|thrilled|can\'t wait|pumped|buzzing|over the moon)\b',           "🎉", "Excited",       8),
    (r'\b(proud|achievement|managed|succeeded|pulled it off|nailed)\b',          "🥹", "Proud",         7),
    (r'\b(grateful|thankful|blessed|appreciate|means a lot|so kind)\b',          "🙏", "Grateful",      6),
    (r'\b(hopeful|optimistic|looking forward|positive about|believe in)\b',      "🌟", "Hopeful",       6),
    (r'\b(surprise|surpris|wow|oh my god|oh wow|no way|really\?)\b',             "😮", "Surprised",     6),
    # ── Low arousal negative ───────────────────────────────────────────────────
    (r'\b(sad|saddened|unfortunate|it\'s a shame|what a shame|pity)\b',          "😢", "Sad",           5),
    (r'\b(worried|anxious|nervous|on edge|tense|dreading|apprehensive)\b',       "😟", "Anxious",       5),
    (r'\b(tired|exhausted|burnt out|drained|depleted|giving up|done with)\b',    "😔", "Depleted",      3),
    (r'\b(lonely|alone|isolated|no one|nobody|by myself|left out)\b',            "🫂", "Lonely",        4),
    (r'\b(helpless|powerless|hopeless|no point|what\'s the point|can\'t win)\b', "😞", "Hopeless",      3),
    (r'\b(pain|suffering|agony|unbearable|torture|hell)\b',                      "😣", "Pained",        7),
    (r'\b(sorry|apolog|forgive me|I shouldn\'t have|my mistake)\b',              "😟", "Apologetic",    4),
    (r'\b(miss|missedI miss|i miss|wish you were|gone and i)\b',                 "🥺", "Longing",       5),
    # ── Low arousal positive ───────────────────────────────────────────────────
    (r'\b(calm|peace|peaceful|serene|settled|at ease|content)\b',                "😌", "Peaceful",      4),
    (r'\b(happy|happily|glad|pleased|delighted|lovely|nice)\b',                  "😊", "Happy",         6),
    (r'\b(reliev|thank god|finally|at last|phew|luckily|turned out)\b',          "😅", "Relieved",      5),
    (r'\b(nostalgic|remember when|back then|used to|those days|childhood)\b',    "🥲", "Nostalgic",     4),
    (r'\b(curious|fascinated|interesting|wonder|intrigued|tells us)\b',          "🤔", "Curious",       5),
    (r'\b(reflective|thinking about|realise|realised|realized|it struck me)\b',  "💭", "Reflective",    4),
    (r'\b(gentle|soft|tender|warm|touching|moved|touch\w* by)\b',                "🥰", "Warm",          5),
    # ── Cognitive / speech states ─────────────────────────────────────────────
    (r'\b(confused|don\'t understand|lost me|what do you mean|makes no sense)\b',"😕", "Confused",      4),
    (r'\b(don\'t know|not sure|maybe|perhaps|could be|might be|unsure)\b',       "🤷", "Uncertain",     3),
    (r'\b(no|never|won\'t|refuse|absolutely not|not going to|I won\'t)\b',       "🙅", "Refusing",      6),
    (r'\b(help|please|desperate|need you|i need|can you|would you)\b',           "🙏", "Pleading",      5),
    (r'\b(sarcas|ironically|yeah right|oh sure|of course not|as if)\b',          "😏", "Sarcastic",     5),
    (r'\b(proud|incredible|i did it|we did it|we made it|success)\b',            "💪", "Empowered",     7),
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

    # Output folder — version if it already exists
    base_dir = Path(args.output_dir) if args.output_dir else audio_path.parent
    base_name = audio_path.stem + str(args.subfolder_suffix)
    out_folder = base_dir / base_name
    if out_folder.exists():
        n = 1
        while (base_dir / f"{base_name}[{n}]").exists():
            n += 1
        out_folder = base_dir / f"{base_name}[{n}]"
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
<meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1" />
<title>🎙️ {audio_name}</title>
<style>
:root {
  --bg:#0f0f1a; --bg2:#1a1a2e; --bg3:#252542; --border:#2d2d55;
  --text:#e0e0f0; --muted:#7a7aa0; --accent:#7a9ecf;
  --green:#4caf82; --red:#e05555; --yellow:#f0c040; --purple:#b07aff; --orange:#f08040;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column;overflow:hidden}
/* Header */
#hdr{background:var(--bg2);border-bottom:1px solid var(--border);padding:10px 16px;flex-shrink:0}
#title-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
#title-text{font-size:1.05em;font-weight:700}
#title-meta{display:flex;gap:10px;align-items:center;flex-wrap:wrap;color:var(--muted);font-size:0.82em}
.htag{background:var(--bg3);color:var(--accent);padding:1px 8px;border-radius:10px;font-size:0.8em}
/* TLDR */
#tldr{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:8px 12px;font-size:0.85em}
#tldr.hidden{display:none}
#tldr-head{font-weight:600;color:var(--accent);margin-bottom:5px;font-size:0.82em;text-transform:uppercase;letter-spacing:.05em}
#tldr-stats{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:4px}
.tstat .lbl{color:var(--muted)}
.tstat .val{font-weight:600}
#tldr-ents{color:var(--muted);font-size:0.9em;line-height:1.7}
/* Controls */
#ctrl{background:var(--bg2);border-bottom:1px solid var(--border);padding:6px 16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;flex-shrink:0}
button.pb{background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 12px;cursor:pointer;font-size:0.88em}
button.pb:hover{background:var(--accent);color:#fff}
#tdisp{color:var(--muted);font-size:0.85em;font-variant-numeric:tabular-nums;min-width:90px}
.toggles{display:flex;gap:5px;flex-wrap:wrap;margin-left:auto}
button.tog{background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:3px 9px;cursor:pointer;font-size:0.78em;color:var(--muted);white-space:nowrap}
button.tog.on{border-color:var(--accent);color:var(--text);background:rgba(122,158,207,.12)}
/* Timeline */
#tl{height:80px;background:#06060f;border-bottom:1px solid var(--border);position:relative;flex-shrink:0;overflow:hidden}
#tlsvg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#tlbar{position:absolute;left:16px;right:16px;bottom:14px;height:0;/* anchor for markers */}
.tlm{position:absolute;transform:translateX(-50%);cursor:pointer;line-height:1;user-select:none;transition:transform .15s ease, filter .15s;bottom:2px}
.tlm:hover{transform:translateX(-50%) translateY(-8px) scale(1.15);filter:brightness(1.3) drop-shadow(0 2px 6px rgba(0,0,0,.5))}
.tlm.xdec{filter:drop-shadow(0 0 4px var(--red))}
.tlm.xclin{filter:drop-shadow(0 0 4px var(--purple))}
#tlph{position:absolute;top:0;bottom:0;width:2px;background:rgba(122,158,207,.8);pointer-events:none;transition:left .15s linear;left:16px}
/* Transcript */
#tx{flex:1;overflow-y:auto;padding:10px 16px}
#tx::-webkit-scrollbar{width:5px}
#tx::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.seg{padding:7px 0;border-bottom:1px solid rgba(255,255,255,.05)}
.seg.playing{background:rgba(122,158,207,.09);border-left:3px solid var(--accent);padding-left:8px;margin-left:-3px;border-radius:0 6px 6px 0}
.seg.nav-hi{outline:2px solid var(--accent);border-radius:6px;outline-offset:2px}
.w{display:inline}
.w.word-on{background:rgba(122,158,207,.45);border-radius:2px;outline:1px solid rgba(122,158,207,.6)}
#btm{background:var(--bg2);border-top:1px solid var(--border);padding:6px 14px;display:flex;align-items:center;gap:8px;flex-shrink:0;flex-wrap:wrap}
.btab{background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:3px 10px;cursor:pointer;font-size:0.78em;color:var(--muted);white-space:nowrap}
.btab.on{border-color:var(--accent);color:var(--text);background:rgba(122,158,207,.12)}
.btab .bc{font-weight:700;margin-left:4px}
#bnav{display:flex;align-items:center;gap:5px;margin-left:auto}
#bnav button{background:var(--bg3);border:1px solid var(--border);border-radius:4px;padding:3px 10px;cursor:pointer;color:var(--text);font-size:.85em}
#bnav button:hover{background:var(--accent);color:#fff}
#bnav button:disabled{opacity:.3;cursor:default}
#bpos{color:var(--muted);font-size:.8em;font-variant-numeric:tabular-nums;min-width:44px;text-align:center}
.seg-row{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap}
.ts{color:var(--accent);font-size:0.8em;font-variant-numeric:tabular-nums;cursor:pointer;font-weight:500;flex-shrink:0}
.ts:hover{color:#fff}
.semo{font-size:.95em;cursor:pointer;flex-shrink:0}
.spktag{background:rgba(122,158,207,.14);color:var(--accent);font-size:0.75em;font-weight:600;padding:1px 6px;border-radius:10px;flex-shrink:0}
.stxt{color:var(--text);line-height:1.65;flex:1;min-width:0}
.abtn{background:none;border:none;color:var(--muted);font-size:0.72em;cursor:pointer;padding:0 3px;flex-shrink:0;opacity:.55}
.abtn:hover{opacity:1;color:var(--accent)}
.bdec{color:var(--red);font-size:.8em;flex-shrink:0}
.bclin{color:var(--purple);font-size:.8em;flex-shrink:0}
/* Analysis drawer */
.adr{display:none;margin:5px 0 3px 28px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.adr.open{display:block}
.atabs{display:flex;background:var(--bg2);border-bottom:1px solid var(--border);overflow-x:auto}
.atab{padding:5px 11px;font-size:0.78em;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap;flex-shrink:0}
.atab.on{color:var(--text);border-bottom-color:var(--accent)}
.apnl{padding:9px 11px;display:none;font-size:0.83em}
.apnl.on{display:block}
.emo-big{font-size:1.7em}
.ibar{height:5px;background:var(--border);border-radius:3px;width:100px;overflow:hidden;display:inline-block;vertical-align:middle}
.ifill{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--green),var(--yellow),var(--red))}
.mi{padding:3px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:.9em}
.mi:last-child{border-bottom:none}
.mtype{color:var(--muted);font-size:.82em}
.mnone{color:var(--muted);font-style:italic}
/* Entity marks */
mark.ep{background:rgba(240,192,64,.18);color:var(--yellow);padding:0 2px;border-radius:2px;border-bottom:1px dotted rgba(240,192,64,.5)}
mark.epl{background:rgba(76,175,130,.18);color:var(--green);padding:0 2px;border-radius:2px;border-bottom:1px dotted rgba(76,175,130,.5)}
/* Indicator word highlights */
.w-dec{background:rgba(224,85,85,.25);border-radius:2px;border-bottom:1px solid rgba(224,85,85,.6)}
.w-ver{background:rgba(76,175,130,.2);border-radius:2px;border-bottom:1px solid rgba(76,175,130,.5)}
/* Body-level hide flags */
body.hide-dec .bdec{display:none}
body.hide-clin .bclin{display:none}
/* Timeline overlay toggles */
#tl-overlays{position:absolute;top:4px;right:8px;display:flex;gap:4px;z-index:10}
.ovbtn{background:rgba(0,0,0,.5);border:1px solid rgba(255,255,255,.2);border-radius:4px;padding:2px 7px;font-size:0.72em;cursor:pointer;color:rgba(255,255,255,.6)}
.ovbtn.on{border-color:var(--accent);color:#fff}
/* Tension glow on high-intensity markers */
#tl.ov-tension .tlm[data-hi]{filter:drop-shadow(0 0 6px var(--red)) drop-shadow(0 0 12px rgba(224,85,85,.6))}
#tl.ov-tension .tlm[data-hi].xdec{filter:drop-shadow(0 0 8px var(--red))}
/* Deception pins */
.tlov-dec{position:absolute;top:0;bottom:14px;width:1px;background:var(--red);opacity:0;pointer-events:none;transition:opacity .15s}
.tlov-dec::after{content:'⚠';position:absolute;top:2px;left:50%;transform:translateX(-50%);font-size:9px;color:var(--red);line-height:1}
#tl.ov-dec .tlov-dec{opacity:.85;pointer-events:auto}
/* People labels */
.tlov-ppl{position:absolute;bottom:4px;background:rgba(240,192,64,.18);color:var(--yellow);border:1px solid rgba(240,192,64,.4);border-radius:3px;padding:0 4px;font-size:9px;white-space:nowrap;opacity:0;pointer-events:none;transition:opacity .15s;transform:translateX(-50%);line-height:1.6}
#tl.ov-ppl .tlov-ppl{opacity:1;pointer-events:auto}
/* Noteworthy event dots */
.tl-event{position:absolute;width:6px;height:6px;background:var(--yellow);border-radius:50%;transform:translateX(-50%);cursor:pointer;opacity:0;transition:opacity .15s;bottom:8px}
#tl.ov-dec .tl-event{opacity:1}
/* Granularity slider */
#tl-gran-wrap{display:flex;align-items:center;gap:4px;font-size:10px;color:rgba(255,255,255,.5)}
#tl-gran{width:60px;height:3px;accent-color:var(--accent)}
</style>
</head>
<body>
<div id="hdr">
  <div id="title-row"><span>🎙️</span><span id="title-text"></span><div id="title-meta"></div></div>
  <div id="tldr"><div id="tldr-head">📋 Summary</div><div id="tldr-stats"></div><div id="tldr-ents"></div></div>
</div>
<div id="ctrl">
  <button class="pb" id="play">▶ Play</button>
  <button class="pb" id="pause">⏸ Pause</button>
  <span id="tdisp">00:00 / 00:00</span>
  <label style="color:var(--muted);font-size:.82em;display:flex;gap:5px;align-items:center">🔍<input type="range" id="zoom" min="1" max="10" value="3" /></label>
</div>
<div id="tl">
  <svg id="tlsvg" preserveAspectRatio="none"></svg>
  <div id="tlbar"></div>
  <div id="tlph"></div>
  <div id="tl-overlays">
    <button class="ovbtn" data-ov="tension" title="Highlight high-intensity segments (>=7)">TENSION</button>
    <button class="ovbtn" data-ov="dec"     title="Show deception marker pins">DECEPTION</button>
    <button class="ovbtn" data-ov="ppl"     title="Show named-person labels">PEOPLE</button>
    <div id="tl-gran-wrap"><span>GRAN</span><input type="range" id="tl-gran" min="1" max="100" value="100"><span id="tl-gran-val">100%</span></div>
  </div>
</div>
<div id="tx"></div>
<div id="btm">
  <div id="btm-tabs"></div>
  <div id="togs"></div>
  <div id="bnav">
    <button id="bnav-p" disabled>←</button>
    <span id="bpos">—</span>
    <button id="bnav-n" disabled>→</button>
  </div>
</div>
<audio id="aud" src="{audio_name}" style="display:none"></audio>
<script>
const segments   = {SEGMENTS_JSON_PLACEHOLDER};
const emotions   = {EMOTIONS_JSON_PLACEHOLDER};
const noteworthy = {NOTEWORTHY_JSON_PLACEHOLDER};
const meta       = {META_JSON_PLACEHOLDER};
const things     = {THINGS_JSON_PLACEHOLDER};

const aud = document.getElementById('aud');
aud.onerror = () => console.warn('Audio not found — playback unavailable (file:// path or missing audio)');
const state = { tldr:true, dec:true, ver:true, clin:true, jeff:true, names:true, nums:true };

// Build emotion lookup by start time
const emoMap = {};
(emotions.segments||[]).forEach(e => { emoMap[e.start_s] = e; });

// Entity lists — filter low-confidence and common false-positives
const SKIP = /^(All|Our|But|The|And|She|He|It|We|They|You|I|My|His|Her|Its|Their|This|That)$/i;
const people = (things.people||[]).filter(p => p.certainty > 0.6 && p.name && p.name.length > 2 && !SKIP.test(p.name));
const places  = (things.places||[]).filter(p => p.certainty > 0.5 && p.name && p.name.length > 2);

function escH(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function hilite(text) {
  let s = escH(text);
  places.forEach(p => { s = s.split(p.name).join('<mark class="epl" title="Place: ' + escH(p.name) + '">' + escH(p.name) + '</mark>'); });
  people.forEach(p => { s = s.split(p.name).join('<mark class="ep" title="Person: ' + escH(p.name) + '">' + escH(p.name) + '</mark>'); });
  return s;
}
// Highlight entities within pre-built word-span HTML (no nested regex escaping)
function hiliteWords(html, words) {
  const eMap = {};
  places.forEach(p => { if (p.name) eMap[p.name.trim()] = {cls:'epl', kind:'Place'}; });
  people.forEach(p => { if (p.name) eMap[p.name.trim()] = {cls:'ep',  kind:'Person'}; });
  return html.replace(/<span class="w" data-s="([^"]+)" data-e="([^"]+)">([^<]*)<\/span>/g,
    (m, ds, de, word) => {
      const clean = word.trim();
      const ent = eMap[clean];
      if (!ent) return m;
      return `<span class="w" data-s="${ds}" data-e="${de}"><mark class="${ent.cls}" title="${ent.kind}: ${escH(clean)}">${escH(clean)}</mark></span>`;
    }
  );
}

function applyPrivacy(html) {
  if (!state.names) html = html.replace(/<mark class="ep"[^>]*>([^<]+)<\\/mark>/g, '<mark class="ep">[NAME]</mark>');
  if (!state.nums)  html = html.replace(/\\b\\d+(\\.\\d+)?\\b/g, '[NUM]');
  return html;
}

// ── Header ─────────────────────────────────────────────────────────────────
function renderHeader() {
  const rawName = meta.audio_file || '{audio_name}';
  const name = rawName.replace(/\\.[^.]+$/, '');
  document.getElementById('title-text').textContent = name;
  document.title = '🎙️ ' + name;
  const meta2 = document.getElementById('title-meta');
  if (meta.duration_formatted) meta2.insertAdjacentHTML('beforeend', '<span>' + escH(meta.duration_formatted) + '</span>');
  if (meta.whisper_model) meta2.insertAdjacentHTML('beforeend', '<span>Whisper ' + escH(meta.whisper_model) + '</span>');
  (meta.hashtags||[]).forEach(h => meta2.insertAdjacentHTML('beforeend', '<span class="htag">' + escH(h) + '</span>'));
}

// ── TLDR ───────────────────────────────────────────────────────────────────
function renderTldr() {
  const segs = emotions.segments || [];
  const cnts = {}; let nDec=0, nVer=0, nClin=0;
  segs.forEach(e => {
    cnts[e.affect_label] = (cnts[e.affect_label]||0) + 1;
    nDec  += (e.deception_markers||[]).length;
    nVer  += (e.veracity_markers||[]).length;
    nClin += (e.clinical_markers||[]).length;
  });
  const topE = Object.entries(cnts).sort((a,b)=>b[1]-a[1])[0];
  const stats = document.getElementById('tldr-stats');
  const items = [
    topE ? `<span class="tstat"><span class="val">${escH(topE[0])}</span> <span class="lbl">dominant tone</span></span>` : '',
    `<span class="tstat"><span class="val">${meta.segment_count||segs.length}</span> <span class="lbl">segments</span></span>`,
    nDec  ? `<span class="tstat"><span class="val" style="color:var(--red)">⚠ ${nDec}</span> <span class="lbl">deception</span></span>` : '',
    nVer  ? `<span class="tstat"><span class="val" style="color:var(--green)">✓ ${nVer}</span> <span class="lbl">veracity</span></span>` : '',
    nClin ? `<span class="tstat"><span class="val" style="color:var(--purple)">◈ ${nClin}</span> <span class="lbl">clinical</span></span>` : '',
  ].filter(Boolean);
  stats.innerHTML = items.join('');
  const entsEl = document.getElementById('tldr-ents');
  const pm = people.slice(0,8).map(p => '<mark class="ep">' + escH(p.name) + '</mark>');
  const plm = places.slice(0,6).map(p => '<mark class="epl">' + escH(p.name) + '</mark>');
  const all = [...pm,...plm];
  if (all.length) entsEl.innerHTML = 'Mentions: ' + all.join(' ');
}

// ── Toggles ────────────────────────────────────────────────────────────────
const TOGS = [
  {k:'tldr',  lbl:'📋 TLDR',      fn: v => document.getElementById('tldr').classList.toggle('hidden',!v)},
  {k:'dec',   lbl:'⚠ Deception',  fn: v => document.body.classList.toggle('hide-dec',!v)},
  {k:'ver',   lbl:'✓ Veracity',   fn: v => {}},
  {k:'clin',  lbl:'◈ Clinical',   fn: v => document.body.classList.toggle('hide-clin',!v)},
  {k:'jeff',  lbl:'~ Jefferson',  fn: v => {}},
  {k:'names', lbl:'👤 Names',     fn: v => rerenderTexts()},
  {k:'nums',  lbl:'🔢 Numbers',   fn: v => rerenderTexts()},
];
function renderToggles() {
  const wrap = document.getElementById('togs');
  TOGS.forEach(t => {
    const b = document.createElement('button');
    b.className = 'tog on'; b.dataset.k = t.k;
    b.innerHTML = '✅ ' + t.lbl;
    b.onclick = () => {
      state[t.k] = !state[t.k];
      b.className = 'tog ' + (state[t.k] ? 'on' : '');
      b.innerHTML = (state[t.k] ? '✅ ' : '🚫 ') + t.lbl;
      t.fn(state[t.k]);
    };
    wrap.appendChild(b);
  });
}

// ── Timeline waveform + emoji markers ─────────────────────────────────────
function renderTimeline() {
  const tl  = document.getElementById('tl');
  const svg = document.getElementById('tlsvg');
  const bar = document.getElementById('tlbar');
  // Clear previous markers and overlay elements
  bar.querySelectorAll('.tlm').forEach(el => el.remove());
  tl.querySelectorAll('.tlov-dec,.tlov-ppl,.tl-event').forEach(el => el.remove());

  const dur  = aud.duration || meta.duration_s || 1;
  const segs = emotions.segments || [];
  const W = tl.offsetWidth || 800;
  const H = tl.offsetHeight || 80;
  const PAD = 16;
  const bw  = W - PAD * 2;
  const MID = H * 0.55;  // baseline sits slightly below centre
  const AMP = H * 0.38;  // max swing above/below baseline

  // Build waveform: dark fill + per-segment colored stroke paths
  if (segs.length > 1) {
    const pts = segs.map(e => ({
      x: PAD + (e.start_s / dur) * bw,
      y: MID - ((e.intensity || 5) - 5) / 5 * AMP,
      intensity: e.intensity || 5,
    }));
    pts.unshift({x: PAD,      y: MID, intensity: 5});
    pts.push(   {x: PAD + bw, y: MID, intensity: 5});

    // Full outline path for dark fill area
    let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const cx = (pts[i].x + pts[i+1].x) / 2;
      const cy = (pts[i].y + pts[i+1].y) / 2;
      d += ` Q ${pts[i].x.toFixed(1)} ${pts[i].y.toFixed(1)} ${cx.toFixed(1)} ${cy.toFixed(1)}`;
    }
    d += ` L ${pts[pts.length-1].x.toFixed(1)} ${pts[pts.length-1].y.toFixed(1)}`;

    // Per-segment colored stroke paths — color by local intensity
    // ponytail: threshold coloring — green>=7, yellow 4-6, red<=3
    let segPaths = '';
    for (let i = 1; i < pts.length; i++) {
      const inten = pts[i].intensity;
      const col = inten >= 7 ? '#4caf82' : inten >= 4 ? '#f0c040' : '#e05555';
      const px = pts[i-1], nx = pts[i];
      const cx = (px.x + nx.x) / 2, cy = (px.y + nx.y) / 2;
      const sd = `M ${px.x.toFixed(1)} ${px.y.toFixed(1)} Q ${px.x.toFixed(1)} ${px.y.toFixed(1)} ${cx.toFixed(1)} ${cy.toFixed(1)}`;
      segPaths += `<path d="${sd}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linecap="round"/>`;
    }

    const fillD = d + ` L ${PAD+bw} ${H} L ${PAD} ${H} Z`;
    svg.innerHTML = `
      <path d="${fillD}" fill="rgba(0,0,0,0.3)"/>
      ${segPaths}
      <line x1="${PAD}" y1="${MID.toFixed(1)}" x2="${PAD+bw}" y2="${MID.toFixed(1)}"
            stroke="rgba(255,255,255,0.1)" stroke-width="1" stroke-dasharray="4,6"/>
    `;
  }

  // Granularity filter — sort by importance, keep top N%
  const granEl = document.getElementById('tl-gran');
  const gran = granEl ? parseInt(granEl.value, 10) : 100;

  // ponytail: importance score — deception > clinical > hi-intensity > veracity > rest
  function segImportance(e) {
    if ((e.deception_markers||[]).length) return 4;
    if ((e.clinical_markers||[]).length)  return 3;
    if ((e.intensity||5) >= 7)            return 2;
    if ((e.veracity_markers||[]).length)  return 1;
    return 0;
  }

  let visSegs = segs.slice();
  if (gran < 100) {
    const scored = visSegs.map(e => ({e, s: segImportance(e) * 10 + (e.intensity||5)}));
    scored.sort((a, b) => b.s - a.s);
    const keep = Math.max(1, Math.ceil(scored.length * gran / 100));
    const kept = new Set(scored.slice(0, keep).map(x => x.e));
    visSegs = visSegs.filter(e => kept.has(e));
  }

  // Emoji markers — placed AT the waveform y position
  visSegs.forEach(e => {
    const x = PAD + (e.start_s / dur) * bw;
    const y = MID - ((e.intensity||5) - 5) / 5 * AMP;
    const pct = (x / W * 100).toFixed(2);
    const bottom = (H - y - 8).toFixed(0);
    const el = document.createElement('span'); el.className = 'tlm';
    if ((e.deception_markers||[]).length) el.classList.add('xdec');
    if ((e.clinical_markers||[]).length)  el.classList.add('xclin');
    if ((e.intensity||5) >= 7) el.dataset.hi = '1';  // ponytail: tension flag
    const sz = 10 + Math.round((e.intensity||5) * 0.8);
    el.style.cssText = `font-size:${sz}px;left:${pct}%;bottom:${bottom}px`;
    el.textContent = e.emoji || '💬';
    el.title = `${e.timestamp} — ${e.affect_label||''} (${e.intensity||5}/10)`;
    el.onclick = () => { aud.currentTime = e.start_s; aud.play(); };
    bar.appendChild(el);
  });

  // Overlay: deception pins — one vertical line per segment with deception markers
  segs.forEach(e => {
    if (!(e.deception_markers||[]).length) return;
    const pct = ((PAD + (e.start_s / dur) * bw) / W * 100).toFixed(2);
    const pin = document.createElement('div'); pin.className = 'tlov-dec';
    pin.style.left = pct + '%';
    pin.title = `Deception markers @ ${e.timestamp}: ${(e.deception_markers||[]).join(', ')}`;
    pin.onclick = () => { aud.currentTime = e.start_s; aud.play(); };
    tl.appendChild(pin);
  });

  // Overlay: noteworthy event dots (certainty > 0.7, visible when DECEPTION overlay on)
  const nwItems = (noteworthy && noteworthy.items) ? noteworthy.items : [];
  nwItems.forEach(item => {
    if ((item.certainty || 0) <= 0.7) return;
    const t = item.start_s != null ? item.start_s : item.time_s;
    if (t == null) return;
    const pct = ((PAD + (t / dur) * bw) / W * 100).toFixed(2);
    const dot = document.createElement('div'); dot.className = 'tl-event';
    dot.style.left = pct + '%';
    dot.title = (item.note || item.text || '').slice(0, 15);
    dot.onclick = () => { aud.currentTime = t; aud.play(); };
    tl.appendChild(dot);
  });

  // Overlay: people labels — first mention per person, matched by segment text
  const seen = new Set();
  segments.forEach(s => {
    people.forEach(p => {
      if (seen.has(p.name)) return;
      if (!s.text || !s.text.includes(p.name)) return;
      seen.add(p.name);
      const pct = ((PAD + (s.start / dur) * bw) / W * 100).toFixed(2);
      const lbl = document.createElement('div'); lbl.className = 'tlov-ppl';
      lbl.style.left = pct + '%';
      lbl.textContent = p.name;
      lbl.title = `Person: ${p.name} first mentioned @ ${Math.floor(s.start/60)}:${String(Math.floor(s.start%60)).padStart(2,'0')}`;
      lbl.onclick = () => { aud.currentTime = s.start; aud.play(); };
      tl.appendChild(lbl);
    });
  });
}
aud.onloadedmetadata = () => renderTimeline();
window.addEventListener('resize', () => { if (aud.duration) renderTimeline(); });

// Granularity slider wiring
const _granEl = document.getElementById('tl-gran');
const _granVal = document.getElementById('tl-gran-val');
if (_granEl) {
  _granEl.addEventListener('input', () => {
    if (_granVal) _granVal.textContent = _granEl.value + '%';
    if (aud.duration || meta.duration_s) renderTimeline();
  });
}

// Overlay toggle buttons
document.querySelectorAll('.ovbtn').forEach(btn => {
  btn.onclick = () => {
    const ov = btn.dataset.ov;
    const cls = 'ov-' + ov;
    const tl = document.getElementById('tl');
    const on = tl.classList.toggle(cls);
    btn.classList.toggle('on', on);
  };
});

// ── Word indicator coloring ────────────────────────────────────────────────
// ponytail: heuristic word-match against marker types; no NLP, pattern lists only
const DEC_WORDS = {
  false_start:           /\b(I mean|actually|no wait|sorry)\b/gi,
  spontaneous_correction:/\b(I mean|I meant|sorry|rather|or rather)\b/gi,
  stalling_repetition:   null, // handled via repeated-word scan below
  memory_disclaimer:     /\b(I think|I'm not sure|maybe|I don't remember|I don't recall)\b/gi,
  defensive_language:    /\b(honestly|to be honest|I swear|believe me|truthfully)\b/gi,
};
const VER_WORDS = {
  sensory_detail:        /\b(see|hear|feel|smell|touch|saw|heard|felt|smelled)\b/gi,
  temporal_sequencing:   /\b(then|after|before|when|next|first|finally|while|during)\b/gi,
  contextual_embedding:  /\b(at|in|near|inside|outside|there|here|beside|behind|across)\b/gi,
  qualified_certainty:   /\b(definitely|certainly|I know|clearly|I'm certain|I'm sure)\b/gi,
};

function colorWords(segIdx, wordHtml) {
  const emo = emoMap[segments[segIdx].start] || {};
  const decMkrs = emo.deception_markers || [];
  const verMkrs = emo.veracity_markers  || [];
  if (!decMkrs.length && !verMkrs.length) return wordHtml;

  // Build a plain-text version of the segment for repeated-word detection
  const plainWords = (segments[segIdx].words || []).map(w => w.word.trim().toLowerCase());

  // Collect word-level classes keyed by word text (lowercased)
  const wCls = {}; // word_text_lc -> Set of classes

  decMkrs.forEach(m => {
    const pat = DEC_WORDS[m.type];
    if (pat) {
      pat.lastIndex = 0;
      const segText = segments[segIdx].text || '';
      let match;
      while ((match = pat.exec(segText)) !== null) {
        const wl = match[0].toLowerCase();
        if (!wCls[wl]) wCls[wl] = new Set();
        wCls[wl].add('w-dec');
      }
    } else if (m.type === 'stalling_repetition') {
      // color words appearing 2+ times in this segment
      const freq = {};
      plainWords.forEach(w => { freq[w] = (freq[w]||0) + 1; });
      Object.keys(freq).forEach(w => { if (freq[w] >= 2) { if (!wCls[w]) wCls[w]=new Set(); wCls[w].add('w-dec'); } });
    }
  });

  verMkrs.forEach(m => {
    const pat = VER_WORDS[m.type];
    if (!pat) return;
    pat.lastIndex = 0;
    const segText = segments[segIdx].text || '';
    let match;
    while ((match = pat.exec(segText)) !== null) {
      const wl = match[0].toLowerCase();
      if (!wCls[wl]) wCls[wl] = new Set();
      wCls[wl].add('w-ver');
    }
  });

  if (!Object.keys(wCls).length) return wordHtml;

  // Inject classes into existing word spans
  return wordHtml.replace(/<span class="(w[^"]*)" data-s="([^"]+)" data-e="([^"]+)">([^<]*)<\/span>/g,
    (m, cls, ds, de, word) => {
      const extra = wCls[word.trim().toLowerCase()];
      if (!extra || !extra.size) return m;
      const newCls = cls + ' ' + [...extra].join(' ');
      return `<span class="${newCls}" data-s="${ds}" data-e="${de}">${word}</span>`;
    }
  );
}

// ── Transcript ─────────────────────────────────────────────────────────────
const segEls = [];
function renderTranscript() {
  const tx = document.getElementById('tx');
  segments.forEach((s, i) => {
    const emo = emoMap[s.start] || {};
    const mm = Math.floor(s.start/60).toString().padStart(2,'0');
    const ss2 = Math.floor(s.start%60).toString().padStart(2,'0');
    const hasDec  = (emo.deception_markers||[]).length > 0;
    const hasVer  = (emo.veracity_markers||[]).length > 0;
    const hasClin = (emo.clinical_markers||[]).length > 0;
    const hasJeff = (emo.jefferson_markers||[]).length > 0;
    const hasAny  = hasDec || hasVer || hasClin || hasJeff;

    const wrap = document.createElement('div'); wrap.className='seg'; wrap.dataset.i=i; wrap.dataset.st=s.start;

    const row = document.createElement('div'); row.className='seg-row';

    const tsEl = document.createElement('span'); tsEl.className='ts';
    tsEl.textContent = `[${mm}:${ss2}]`;
    tsEl.onclick = () => { aud.currentTime = s.start; aud.play(); };

    const emoEl = document.createElement('span'); emoEl.className='semo';
    emoEl.textContent = emo.emoji||'💬'; emoEl.title = emo.affect_label||'';
    if (hasAny) emoEl.onclick = () => toggleDrawer(i);

    row.appendChild(tsEl); row.appendChild(emoEl);
    if (hasDec)  { const b=document.createElement('span'); b.className='bdec'; b.textContent='⚠'; b.title='Deception'; row.appendChild(b); }
    if (hasClin) { const b=document.createElement('span'); b.className='bclin'; b.textContent='◈'; b.title='Clinical'; row.appendChild(b); }
    if (s.speaker) { const sp=document.createElement('span'); sp.className='spktag'; sp.textContent=s.speaker; row.appendChild(sp); }

    // Word spans for timing; fall back to plain text
    const txtEl = document.createElement('span'); txtEl.className='stxt';
    txtEl.dataset.raw = s.text||'';
    if (s.words && s.words.length) {
      const wordHtml = s.words.map(w =>
        `<span class="w" data-s="${w.start}" data-e="${w.end}">${escH(w.word)}</span>`
      ).join('');
      txtEl.innerHTML = applyPrivacy(hiliteWords(colorWords(i, wordHtml), s.words));
    } else {
      txtEl.innerHTML = applyPrivacy(hilite(s.text||''));
    }

    row.appendChild(txtEl);
    if (hasAny) {
      const aBtn = document.createElement('button'); aBtn.className='abtn'; aBtn.textContent='▼'; aBtn.title='Analysis';
      aBtn.onclick = () => toggleDrawer(i);
      row.appendChild(aBtn);
    }
    wrap.appendChild(row);

    const drawer = document.createElement('div'); drawer.className='adr'; drawer.id='adr'+i;
    wrap.appendChild(drawer);
    tx.appendChild(wrap);
    segEls.push(wrap);
  });
}

function buildDrawer(i) {
  const emo = emoMap[segments[i].start] || {};
  const tabs = [
    {id:'emo',  lbl:'😊 Emotion'},
    {id:'dec',  lbl:'⚠ Deception'},
    {id:'ver',  lbl:'✓ Veracity'},
    {id:'clin', lbl:'◈ Clinical'},
    {id:'jeff', lbl:'〜 Jefferson'},
  ];
  const tabsH = tabs.map((t,idx) => `<div class="atab${idx===0?' on':''}" data-t="${t.id}">${t.lbl}</div>`).join('');
  const pnls = [
    buildEmoPanel(emo),
    buildMkrPanel(emo.deception_markers||[], 'red'),
    buildMkrPanel(emo.veracity_markers||[], 'green'),
    buildMkrPanel(emo.clinical_markers||[], 'purple'),
    buildMkrPanel(emo.jefferson_markers||[], 'orange'),
  ];
  const pnlsH = tabs.map((t,idx) => `<div class="apnl${idx===0?' on':''}" data-t="${t.id}">${pnls[idx]}</div>`).join('');
  return `<div class="atabs">${tabsH}</div>${pnlsH}`;
}

function buildEmoPanel(emo) {
  const pct = ((emo.intensity||5)/10*100).toFixed(0);
  return `<div style="display:flex;gap:10px;align-items:center">
    <span class="emo-big">${emo.emoji||'💬'}</span>
    <div>
      <div style="font-weight:600">${escH(emo.affect_label||'Unknown')}</div>
      <div style="margin-top:4px;display:flex;align-items:center;gap:8px">
        <span class="ibar"><span class="ifill" style="width:${pct}%"></span></span>
        <span style="color:var(--muted);font-size:.82em">${emo.intensity||5}/10</span>
      </div>
    </div>
  </div>
  ${emo.certainty!==undefined?`<div style="color:var(--muted);font-size:.8em;margin-top:5px">Certainty: ${(emo.certainty*100).toFixed(0)}%</div>`:''}
  ${(emo.pause_before_s||0)>1?`<div style="color:var(--muted);font-size:.8em;margin-top:3px">⏱ ${emo.pause_before_s.toFixed(1)}s pause before</div>`:''}`;
}

function buildMkrPanel(markers, col) {
  if (!markers.length) return `<div class="mnone">None detected</div>`;
  return markers.map(m => `<div class="mi">
    <span style="color:var(--${col});font-size:.82em">${escH(m.symbol||m.type||'')}</span>
    <span> ${escH(m.note||m.type||'')}</span>
    ${m.certainty!==undefined?`<span style="color:var(--muted);font-size:.8em"> [${(m.certainty*100).toFixed(0)}%]</span>`:''}
  </div>`).join('');
}

function toggleDrawer(i) {
  const dr = document.getElementById('adr'+i);
  if (!dr) return;
  const opening = !dr.classList.contains('open');
  dr.classList.toggle('open', opening);
  if (opening && !dr.innerHTML) {
    dr.innerHTML = buildDrawer(i);
    dr.querySelectorAll('.atab').forEach(tab => {
      tab.onclick = () => {
        const p = tab.closest('.adr');
        p.querySelectorAll('.atab').forEach(t => t.classList.remove('on'));
        p.querySelectorAll('.apnl').forEach(t => t.classList.remove('on'));
        tab.classList.add('on');
        p.querySelector('.apnl[data-t="'+tab.dataset.t+'"]').classList.add('on');
      };
    });
  }
}

function rerenderTexts() {
  segments.forEach((s, i) => {
    const el = segEls[i] && segEls[i].querySelector('.stxt');
    if (!el) return;
    if (s.words && s.words.length) {
      const wh = s.words.map(w => `<span class="w" data-s="${w.start}" data-e="${w.end}">${escH(w.word)}</span>`).join('');
      el.innerHTML = applyPrivacy(hiliteWords(colorWords(i, wh), s.words));
    } else {
      el.innerHTML = applyPrivacy(hilite(el.dataset.raw||''));
    }
  });
}

// ── Playback tracking ──────────────────────────────────────────────────────
let curIdx = -1;
aud.ontimeupdate = () => {
  const cur = aud.currentTime||0, dur = aud.duration||meta.duration_s||1;
  const f = t => [Math.floor(t/60),Math.floor(t%60)].map(n=>String(n).padStart(2,'0')).join(':');
  document.getElementById('tdisp').textContent = f(cur) + ' / ' + f(dur);
  const ph = document.getElementById('tlph');
  if (ph) ph.style.left = (cur/dur*100).toFixed(2)+'%';
  let ni = -1;
  for (let i=0;i<segments.length;i++) { if(segments[i].start<=cur) ni=i; else break; }
  if (ni !== curIdx) {
    if (curIdx>=0&&segEls[curIdx]) segEls[curIdx].classList.remove('playing');
    if (ni>=0&&segEls[ni]) { segEls[ni].classList.add('playing'); segEls[ni].scrollIntoView({behavior:'smooth',block:'nearest'}); }
    curIdx = ni;
  }
  // Word highlight
  if (curIdx >= 0 && segEls[curIdx]) {
    segEls[curIdx].querySelectorAll('.w').forEach(w => {
      w.classList.toggle('word-on', cur >= +w.dataset.s && cur < +w.dataset.e);
    });
  }
};
document.getElementById('play').onclick  = () => aud.play();
document.getElementById('pause').onclick = () => aud.pause();

// ── Bottom nav ─────────────────────────────────────────────────────────────
const BTYPES = [
  {id:'dec',  lbl:'⚠ Deception', key:'deception_markers',  col:'red'},
  {id:'ver',  lbl:'✓ Veracity',  key:'veracity_markers',   col:'green'},
  {id:'clin', lbl:'◈ Clinical',  key:'clinical_markers',   col:'purple'},
  {id:'jeff', lbl:'〜 Jefferson', key:'jefferson_markers',  col:'orange'},
];
const bidx = {};
BTYPES.forEach(t => {
  bidx[t.id] = (emotions.segments||[]).reduce((acc, e, i) => {
    if ((e[t.key]||[]).length) {
      const si = segments.findIndex(s => Math.abs(s.start - e.start_s) < 0.1);
      if (si >= 0) acc.push(si);
    }
    return acc;
  }, []);
});
let btype = null, bpos = 0;
function initBottomNav() {
  const wrap = document.getElementById('btm-tabs');
  BTYPES.forEach(t => {
    if (!bidx[t.id].length) return;
    const b = document.createElement('button'); b.className='btab'; b.dataset.t=t.id;
    b.innerHTML = t.lbl + ' <span class="bc" style="color:var(--'+t.col+')">' + bidx[t.id].length + '</span>';
    b.onclick = () => { btype=t.id; bpos=0; bSync(); };
    wrap.appendChild(b);
  });
  document.getElementById('bnav-p').onclick = () => { bpos--; bSync(); };
  document.getElementById('bnav-n').onclick = () => { bpos++; bSync(); };
}
function bSync() {
  if (!btype) return;
  const items = bidx[btype];
  bpos = Math.max(0, Math.min(items.length-1, bpos));
  document.querySelectorAll('.btab').forEach(b => b.classList.toggle('on', b.dataset.t===btype));
  document.getElementById('bpos').textContent = `${bpos+1} / ${items.length}`;
  document.getElementById('bnav-p').disabled = bpos === 0;
  document.getElementById('bnav-n').disabled = bpos === items.length-1;
  const si = items[bpos];
  if (segEls[si]) {
    segEls[si].scrollIntoView({behavior:'smooth', block:'center'});
    segEls[si].classList.add('nav-hi');
    setTimeout(() => segEls[si].classList.remove('nav-hi'), 900);
  }
}

// ── Init ───────────────────────────────────────────────────────────────────
renderHeader();
renderTldr();
renderToggles();
renderTranscript();
initBottomNav();
if (meta.duration_s) renderTimeline();
</script>
</body>
</html>"""

            viewer_html = viewer_html.replace('{SEGMENTS_JSON_PLACEHOLDER}', segments_json)
            viewer_html = viewer_html.replace('{EMOTIONS_JSON_PLACEHOLDER}', emotions_json)
            viewer_html = viewer_html.replace('{NOTEWORTHY_JSON_PLACEHOLDER}', noteworthy_json)
            viewer_html = viewer_html.replace('{META_JSON_PLACEHOLDER}', meta_json)
            viewer_html = viewer_html.replace('{THINGS_JSON_PLACEHOLDER}', things_json)
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
