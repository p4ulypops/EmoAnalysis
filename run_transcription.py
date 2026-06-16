#!/usr/bin/env python3
"""
Emotion Audio — Local Transcription + Analysis Script  v2.1

Creates a folder named after the audio file containing:
    transcript.md    — verbatim transcript with timings + [G:N] glossary refs
    emotions.json    — per-segment emotion, intensity, emoji, pauses
    things.json      — people, places, dates, times
    meta.json        — recording metadata, speakers, hashtags, file info
    glossary.json    — medical/legal/tech terms + acronyms found in speech
    noteworthy.json  — flagged moments (freezes, events, uncertainties)

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

  Voice matching (after any diarization tier):
    --match-voice '/path/to/known_voice.m4a' 'Name'
    Can be repeated for multiple known speakers:
    --match-voice '/clips/natalia.m4a' 'Natalia' --match-voice '/clips/jacky.m4a' 'Jacky'

Usage:
    python3 '/Users/user/Library/Application Support/Claude/local-agent-mode-sessions/9f946972-8ad4-4a83-bda4-fd9d7e621aad/b6e0b069-0598-4b7f-bfaf-fa7c4d9e0e64/local_152db07a-1520-4dae-aa27-00751e5d4cdf/outputs/run_transcription.py' '/path/to/audio.m4a'
    python3 '...run_transcription.py' '/path/to/audio.m4a' --diarise-local
    python3 '...run_transcription.py' '/path/to/audio.m4a' --diarise --hf-token hf_xxx
    python3 '...run_transcription.py' '/path/to/audio.m4a' --diarise-local --match-voice '/clip.m4a' 'Pauly'
    python3 '...run_transcription.py' '/path/to/audio.m4a' --output-dir ~/Desktop
"""

import argparse
import json
import re
import subprocess
import sys
import shutil
from datetime import datetime, timedelta
from pathlib import Path


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

# Holds custom definitions from wordlists.json "custom" list
CUSTOM_GLOSSARY_DEFS: list = []
# Holds extra place names from places.json
EXTRA_PLACES: list = []


def load_config(script_path: Path) -> None:
    """Load user config files from config/ next to the script and merge into globals."""
    global MEDICAL_TERMS, LEGAL_TERMS, TECH_TERMS, AFFECT_HEURISTICS
    global CUSTOM_GLOSSARY_DEFS, EXTRA_PLACES

    config_dir = script_path.parent / "config"
    if not config_dir.exists():
        return

    # ── emotions.json ──
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

    # ── places.json ──
    places_file = config_dir / "places.json"
    if places_file.exists():
        try:
            data = json.loads(places_file.read_text(encoding="utf-8"))
            EXTRA_PLACES = [str(p) for p in data.get("locations", [])]
            print(f"  ✓ config/places.json — {len(EXTRA_PLACES)} custom locations loaded")
        except Exception as e:
            print(f"  ⚠️ config/places.json parse error: {e}")

    # ── wordlists.json ──
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
    """Tier 3: pyannote.audio — best accuracy, requires HuggingFace token."""
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
    """Tier 2: Resemblyzer — fully local, no token, no internet.
    pip3 install resemblyzer scikit-learn --break-system-packages
    """
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
    sr = 16000  # Resemblyzer always uses 16kHz

    print("Extracting voice embeddings per segment...")
    embeddings = []
    valid_indices = []

    # We'll use the Whisper segments as our time windows
    # This function is called before segments exist, so we build windows ourselves
    # Use 3-second sliding windows for embedding
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

    embeds_arr = embeddings  # list of 256-dim arrays

    # Estimate speaker count if not given
    if n_speakers is None:
        # Heuristic: start at 2, cap at 6
        n_speakers = min(6, max(2, len(embeddings) // 20))
        print(f"  → Auto-estimating {n_speakers} speakers")

    print(f"  → Clustering voice embeddings into {n_speakers} speaker groups...")
    import numpy as np
    clustering = AgglomerativeClustering(n_clusters=n_speakers,
                                         metric="cosine",
                                         linkage="average")
    labels = clustering.fit_predict(embeds_arr)

    # Build speaker turn list from windows
    turns = []
    for i, window in enumerate(windows):
        turns.append({
            "start": window["start"],
            "end": window["end"],
            "speaker": label_from_cluster(int(labels[i])),
        })

    return turns


def assign_speakers_from_turns(segments: list, speaker_turns: list) -> list:
    """Map Whisper segments to diarized speaker turns by timestamp overlap."""
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
    """
    Match known voice clips against diarized speaker clusters.
    voice_refs: list of (audio_path, name) tuples.
    Returns list of match results, and renames speaker labels in segments in-place.
    """
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

    # Build average embedding per discovered speaker
    speaker_clip_embeds: dict = {}
    for seg in segments:
        spk = seg.get("speaker", "Speaker_01")
        start_i = int(seg["start"] * sr)
        end_i = int(seg["end"] * sr)
        clip = audio_wav[start_i:end_i]
        if len(clip) < sr * 0.5:  # skip clips under 0.5s
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
    rename_map: dict = {}  # old_label -> new_name

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

        # Only rename if similarity is convincing (>0.60)
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

    # Apply renames to segments
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

    # Acronyms (2-5 uppercase letters, not trivial)
    trivial = {"I", "UK", "US", "TV", "OK", "AM", "PM", "GP"}
    for m in re.finditer(r'\b([A-Z]{2,5})\b', full_text):
        ac = m.group(1)
        if ac not in trivial:
            add(ac, "acronym", "Acronym — definition unknown; please fill in", 0.55)

    # Medical
    for term in MEDICAL_TERMS:
        if re.search(r'\b' + re.escape(term) + r'\b', full_text, re.IGNORECASE):
            add(term, "medical/clinical",
                "Medical or clinical term — see NHS guidance or professional definition", 0.82)

    # Legal
    for term in LEGAL_TERMS:
        if re.search(r'\b' + re.escape(term) + r'\b', full_text, re.IGNORECASE):
            add(term, "legal",
                "Legal or regulatory term — consult solicitor or official guidance", 0.82)

    # Tech
    for term in TECH_TERMS:
        if re.search(r'\b' + re.escape(term) + r'\b', full_text, re.IGNORECASE):
            add(term, "technical", "Technical/digital term", 0.78)

    # Drug name patterns
    drug_re = re.compile(
        r'\b([A-Za-z]{3,}(?:ol|ine|mab|nib|stat|pril|sartan|azole|mycin|cillin))\b',
        re.IGNORECASE
    )
    for m in drug_re.finditer(full_text):
        term = m.group(1)
        if term.lower() not in seen:
            add(term, "medication",
                "Possible medication — verify: dosage, purpose, side effects", 0.65)

    # Similes / metaphors
    for m in re.finditer(r'\b(?:like|as)\s+(?:a|an|the)\s+(\w+)', full_text, re.IGNORECASE):
        phrase = f"like a {m.group(1)}"
        if phrase.lower() not in seen:
            add(phrase, "metaphor/simile",
                "Figurative expression — contextual interpretation may be needed", 0.45)

    # Custom definitions from config/wordlists.json
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
    """term_lower -> gid"""
    return {e["term"].lower(): e["id"] for e in glossary}


def mark_glossary_inline(text: str, term_index: dict, already_marked: set) -> tuple:
    """Insert [G:N] on first occurrence of each term. Returns (marked_text, updated_set)."""
    result = text
    # Longest terms first to avoid partial matches
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

    # People
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

    # Places — built-in + config/places.json
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

    # Dates
    dates = []
    date_patterns = [
        (r'\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b', "absolute"),
        (r'\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:january|february|march|april|may|june|'
         r'july|august|september|october|november|december)(?:\s+\d{4})?)\b', "absolute"),
        (r'\b(yesterday|today|tomorrow|last\s+\w+|next\s+\w+|this\s+\w+)\b', "relative"),
    ]
    seen_dates = set()
    for pat, dtype in date_patterns:
        for m in re.findall(pat, full_text, re.IGNORECASE):
            val = m if isinstance(m, str) else m[0]
            if val.lower() not in seen_dates:
                seen_dates.add(val.lower())
                dates.append({"value": val, "type": dtype, "certainty": 0.88})

    # Times
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


# ─── Emotions ─────────────────────────────────────────────────────────────────

def build_emotions(segments: list, env_events: list, acoustic: list, room: list) -> dict:
    emotion_segments = []
    pauses = []
    freeze_events = []
    prev_end = 0.0

    for i, seg in enumerate(segments):
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "").strip()
        speaker = seg.get("speaker", "Speaker")
        pause_before = max(0.0, round(start - prev_end, 2))

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

        emoji = "😐"
        affect = "Neutral"
        intensity = 5
        for pattern, em, label, inten in AFFECT_HEURISTICS:
            if re.search(pattern, text, re.IGNORECASE):
                emoji = em
                affect = label
                intensity = inten
                break

        has_caps = bool(re.search(r'\b[A-Z]{3,}\b', text))
        if has_caps:
            intensity = min(10, intensity + 2)
            emoji = "😠"
            affect = "Raised voice / emphasis"

        jefferson = []
        if has_caps:
            jefferson.append("CAPS — shouting or strong emphasis")
        if "?" in text:
            jefferson.append("? — question / uncertainty")
        if pause_before > 1.5:
            jefferson.append(f"({pause_before:.1f}) — pause before utterance")

        emotion_segments.append({
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
            "jefferson_markers": jefferson,
            "certainty": 0.65,
        })
        prev_end = end

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


# ─── Transcript MD ────────────────────────────────────────────────────────────

def build_transcript_md(segments: list, emotions_data: dict,
                        glossary: list, audio_path: Path) -> str:
    term_index = build_term_index(glossary)
    already_marked: set = set()
    em_by_index = {e["index"]: e for e in emotions_data["segments"]}

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
        "",
        "> `[G:N]` after a word → see entry N in glossary.json",
        "> `[C:0.00–1.00]` certainty — below 0.70 is ⚠️ verify",
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
        pause_before = max(0.0, start - prev_end)

        if pause_before > 10:
            m_v = int(pause_before // 60)
            s_v = pause_before % 60
            lines.append(f"\n`({m_v:02d}:{s_v:06.3f})` 🚨 **EXTENDED FREEZE**\n")
        elif pause_before > 5:
            lines.append(f"\n`({pause_before:.2f})` ⚠️ significant pause\n")
        elif pause_before > 1.5:
            lines.append(f"\n`({pause_before:.2f})`\n")

        if speaker != prev_speaker:
            emoji = em.get("emoji", "😐")
            affect = em.get("affect_label", "Neutral")
            intensity = em.get("intensity", 5)
            lines.append(
                f"\n**[{fmt_ms(start)}] {{{speaker}}} "
                f"[{emoji} {affect} : {intensity}/10] [C:0.70]:**"
            )
            prev_speaker = speaker
        else:
            lines.append(f"[{fmt_ms(start)}]")

        marked_text, already_marked = mark_glossary_inline(text, term_index, already_marked)
        lines.append(marked_text)
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
        "_Generated by Emotion Audio Analyser v2.0_",
        "_Paste transcript.md into Claude with the `emotion-audio-analyser` skill for full annotation_",
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
        description="Transcribe audio → structured analysis folder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("audio", help="Path to audio file (m4a/mp3/wav/etc.)")
    parser.add_argument("--model", default="base",
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Whisper model size (default: base)")
    parser.add_argument("--language", default="en",
                        help="Language code (default: en)")
    parser.add_argument("--context", default="general",
                        help="Context type label (default: general)")
    parser.add_argument("--output-dir", default="",
                        help="Where to create output folder (default: current dir)")

    # Speaker diarization — mutually exclusive tiers
    diar_group = parser.add_mutually_exclusive_group()
    diar_group.add_argument("--diarise-local", action="store_true",
                             help="Local voice clustering via Resemblyzer (no internet, no token). "
                                  "Install: pip3 install resemblyzer scikit-learn --break-system-packages")
    diar_group.add_argument("--diarise", action="store_true",
                             help="Speaker diarization via pyannote.audio (requires HuggingFace token). "
                                  "Install: pip3 install pyannote.audio --break-system-packages")

    parser.add_argument("--hf-token", default="",
                        help="HuggingFace token for --diarise (or set HF_TOKEN env var)")
    parser.add_argument("--n-speakers", type=int, default=None,
                        help="Expected number of speakers (optional — auto-detected if omitted)")
    parser.add_argument("--match-voice", nargs=2, metavar=("AUDIO_PATH", "NAME"),
                        action=MatchVoiceAction, dest="voice_refs",
                        help="Match a known voice clip to a speaker label. "
                             "Repeatable: --match-voice clip1.m4a Pauly --match-voice clip2.m4a Mum. "
                             "Requires --diarise or --diarise-local.")
    parser.add_argument("--subfolder-suffix", default="_subfile",
                        help="Suffix to append to the audio filename for the output subfolder (default: _subfile)")
    parser.add_argument("--no-copy-audio", dest="copy_audio", action="store_false",
                        help="Do not copy the original audio file into the output folder")
    parser.add_argument("--no-viewer", dest="generate_viewer", action="store_false",
                        help="Do not generate the embedded HTML viewer in the output folder")
    args = parser.parse_args()

    # Load user config (config/ folder next to this script)
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

    # Output folder
    base_dir = Path(args.output_dir) if args.output_dir else audio_path.parent
    out_folder = base_dir / (audio_path.stem + str(args.subfolder_suffix))
    out_folder.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput folder: {out_folder}\n")

    # ── Transcribe ──────────────────────────────────────────────────────────
    result = transcribe(audio_path, model_size=args.model, language=args.language)
    segments = result.get("segments", [])

    # ── Speaker Diarization ─────────────────────────────────────────────────
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

    # ── Voice Matching ──────────────────────────────────────────────────────
    if args.voice_refs:
        print("\nRunning voice matching against reference clips...")
        voice_match_results = match_known_voices(audio_path, segments, args.voice_refs)
        result["segments"] = segments  # segments may have been renamed

    # Collect discovered speaker labels
    discovered_speakers = sorted(set(s.get("speaker", "Speaker_01") for s in segments))

    # ── Environment Scans ───────────────────────────────────────────────────
    print("\nScanning audio...")
    print("  → Environmental audio (music/radio/AI)...")
    env_events = detect_environmental_ffmpeg(audio_path)
    print("  → Acoustic events (horns/slams/alarms)...")
    acoustic = detect_acoustic_events_ffmpeg(audio_path)
    print("  → Room changes (door events)...")
    room = detect_room_changes_ffmpeg(audio_path)

    # ── Build Structured Data ───────────────────────────────────────────────
    print("\nBuilding analysis...")
    print("  → Extracting entities...")
    things = extract_things(segments, discovered_speakers)
    print("  → Detecting glossary terms...")
    glossary = detect_glossary_terms(segments)
    print("  → Building emotions data...")
    emotions = build_emotions(segments, env_events, acoustic, room)
    print("  → Building noteworthy items...")
    noteworthy = build_noteworthy(emotions, env_events, acoustic, room, things, glossary)
    hashtags = generate_hashtags(things, segments, args.context)

    # ── Meta ────────────────────────────────────────────────────────────────
    duration_s = segments[-1]["end"] if segments else 0
    meta = {
        "audio_file": audio_path.name,
        "audio_path": str(audio_path),
        "duration_s": round(duration_s, 1),
        "duration_formatted": fmt_ms(duration_s),
        "transcription_timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "whisper_model": args.model,
        "language": result.get("language", args.language),
        "context_type": args.context,
        "schema_version": "Affective-Clinical-MD-v2.6",
        "wispr_privacy_mode": True,
        "diarization": {
            "method": diarization_method,
            "n_speakers_detected": len(discovered_speakers),
            "speaker_labels": discovered_speakers,
            "voice_matching": voice_match_results,
            "note": "Speaker labels are discovered automatically — names are not assumed. "
                    "Use --match-voice to attach names to voice clusters.",
        },
        "segment_count": len(segments),
        "word_count": len(result.get("text", "").split()),
        "hashtags": hashtags,
        "output_folder": str(out_folder),
        "output_files": [
            "transcript.md", "emotions.json", "things.json",
            "meta.json", "glossary.json", "noteworthy.json",
        ],
    }

    # ── Build Transcript ─────────────────────────────────────────────────────
    print("  → Building transcript.md...")
    transcript_md = build_transcript_md(segments, emotions, glossary, audio_path)

    # ── Write Files ──────────────────────────────────────────────────────────
    print("\nWriting files...")
    outputs = {
        "transcript.md":   transcript_md,
        "emotions.json":   json.dumps(emotions, indent=2, ensure_ascii=False),
        "things.json":     json.dumps(things, indent=2, ensure_ascii=False),
        "meta.json":       json.dumps(meta, indent=2, ensure_ascii=False),
        "glossary.json":   json.dumps({"entries": glossary}, indent=2, ensure_ascii=False),
        "noteworthy.json": json.dumps({"items": noteworthy}, indent=2, ensure_ascii=False),
    }
    for filename, content in outputs.items():
        (out_folder / filename).write_text(content, encoding="utf-8")
        print(f"  ✅ {filename}")

        # Copy audio into output folder by default (optional)
        try:
                if args.copy_audio:
                        dest_audio = out_folder / audio_path.name
                        if not dest_audio.exists():
                                shutil.copy2(audio_path, dest_audio)
                                print(f"  ✅ copied audio: {dest_audio.name}")
        except Exception as e:
                print(f"  ⚠️ could not copy audio: {e}")

        # Generate a single-file HTML viewer that embeds the outputs and audio (optional)
        if getattr(args, "generate_viewer", True):
                try:
                        # Prepare embedded JSON and transcript (escape closing script tags)
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
    <title>Emotion Audio Viewer — {audio_path.name}</title>
    <style>
        body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin:0; height:100vh; display:flex; flex-direction:column; }
        #top { padding:8px; display:flex; gap:8px; align-items:center; }
        #timeline { height:120px; background:#111; color:#fff; position:relative; display:flex; align-items:center; padding:10px; }
        #timeline .bar { position:relative; height:8px; background:#333; width:100%; border-radius:4px; }
        .marker { position:absolute; top:6px; width:8px; height:8px; background:#ffcc00; border-radius:50%; transform:translateX(-50%); cursor:pointer; }
        #controls { display:flex; gap:8px; align-items:center; }
        #transcript { height:40vh; overflow:auto; border-top:1px solid #ddd; padding:12px; }
        .segment { padding:6px 0; border-bottom:1px dashed #eee; }
        .timestamp { color:#666; margin-right:8px; cursor:pointer; }
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
    <div id="timeline">
        <div class="bar" id="bar"></div>
    </div>
    <div id="transcript"></div>

    <audio id="audio" controls style="width:0;height:0;opacity:0;position:fixed;left:-9999px;" src="{audio_path.name}"></audio>

    <script>
        const segments = {SEGMENTS_JSON_PLACEHOLDER};
        const emotions = {EMOTIONS_JSON_PLACEHOLDER};
        const things = {THINGS_JSON_PLACEHOLDER};
        const glossary = {GLOSSARY_JSON_PLACEHOLDER};
        const noteworthy = {NOTEWORTHY_JSON_PLACEHOLDER};
        const meta = {META_JSON_PLACEHOLDER};
        const transcript = `{TRANSCRIPT_PLACEHOLDER}`;

        const audio = document.getElementById('audio');
        const playBtn = document.getElementById('play');
        const pauseBtn = document.getElementById('pause');
        const bar = document.getElementById('bar');
        const timeline = document.getElementById('timeline');
        const timeLabel = document.getElementById('time');
        const zoom = document.getElementById('zoom');

        // Render transcript
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

        // Build markers using segments (start times)
        function renderMarkers() {
            bar.innerHTML='';
            const dur = audio.duration || meta.duration_s || 0;
            const scale = parseFloat(zoom.value);
            segments.forEach(s => {
                const el = document.createElement('div'); el.className='marker';
                const pct = (s.start / dur) * 100;
                el.style.left = pct + '%';
                el.title = `${s.start.toFixed(1)}s`;
                el.onclick = (e) => { e.stopPropagation(); audio.currentTime = s.start; audio.play(); };
                bar.appendChild(el);
            });
            // noteworthy markers
            try {
                const items = (noteworthy.items) || [];
                items.forEach(it => {
                    if (it.time || it.start) {
                        const t = it.time || it.start;
                        const el = document.createElement('div'); el.className='marker'; el.style.background='#ff66cc';
                        const pct = (t / dur) * 100;
                        el.style.left = pct + '%';
                        el.title = it.note || it.desc || 'noteworthy';
                        el.onclick = (e) => { e.stopPropagation(); audio.currentTime = t; audio.play(); };
                        bar.appendChild(el);
                    }
                });
            } catch(e){}
        }

        playBtn.onclick = () => audio.play();
        pauseBtn.onclick = () => audio.pause();
        audio.ontimeupdate = () => {
            const cur = audio.currentTime || 0;
            const dur = audio.duration || meta.duration_s || 0;
            const mm = Math.floor(cur/60).toString().padStart(2,'0');
            const ss = Math.floor(cur%60).toString().padStart(2,'0');
            const dmm = Math.floor(dur/60).toString().padStart(2,'0');
            const dss = Math.floor(dur%60).toString().padStart(2,'0');
            timeLabel.textContent = `${mm}:${ss} / ${dmm}:${dss}`;
            // progress indicator
            const pct = (cur / (dur || 1)) * 100;
            bar.style.setProperty('--pos', pct + '%');
        };

        // scrubbing
        bar.parentElement.onclick = (e) => {
            const rect = bar.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const pct = x / rect.width;
            const dur = audio.duration || meta.duration_s || 0;
            audio.currentTime = pct * dur;
        };

        zoom.oninput = () => { renderMarkers(); };

        audio.onloadedmetadata = () => { renderMarkers(); };

    </script>
</body>
</html>
"""

                        # Replace placeholders safely (avoid Python f-string conflicts with JS braces)
                        viewer_html = viewer_html.replace('{SEGMENTS_JSON_PLACEHOLDER}', segments_json)
                        viewer_html = viewer_html.replace('{EMOTIONS_JSON_PLACEHOLDER}', emotions_json)
                        viewer_html = viewer_html.replace('{THINGS_JSON_PLACEHOLDER}', things_json)
                        viewer_html = viewer_html.replace('{GLOSSARY_JSON_PLACEHOLDER}', glossary_json)
                        viewer_html = viewer_html.replace('{NOTEWORTHY_JSON_PLACEHOLDER}', noteworthy_json)
                        viewer_html = viewer_html.replace('{META_JSON_PLACEHOLDER}', meta_json)
                        # transcript_text may contain backticks or closing script tags; it was pre-escaped earlier
                        viewer_html = viewer_html.replace('{TRANSCRIPT_PLACEHOLDER}', transcript_text)
                        # audio src
                        viewer_html = viewer_html.replace('{audio_path.name}', audio_path.name)

                        (out_folder / "viewer.html").write_text(viewer_html, encoding="utf-8")
                        print("  ✅ viewer.html")
                except Exception as e:
                        print(f"  ⚠️ could not generate viewer: {e}")

    print(f"\n✅ Done — {len(outputs)} files in:")
    print(f"   {out_folder}")
    print(f"\n   Speakers detected: {', '.join(discovered_speakers)}")
    if voice_match_results:
        for r in voice_match_results:
            renamed = f" → renamed to '{r['renamed_to']}'" if r.get("renamed_to") else " (not renamed — low confidence)"
            print(f"   Voice match: {r['reference_name']} = {r['best_match_speaker']}{renamed} [C:{r['certainty']:.2f}]")
    print(f"\nNext: paste transcript.md into Claude with the emotion-audio-analyser skill")
    print(f"      for full Jefferson/TEI/CHAT annotation and clinical analysis.")


if __name__ == "__main__":
    main()
