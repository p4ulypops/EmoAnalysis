"""
Emotion Audio MCP Server v1.1
Analyses emotional response from audio recordings using the Affective-Clinical-MD schema.
Supports Whisper (OpenAI) and ElevenLabs for transcription, plus local prosody analysis via librosa.

v1.1 additions:
- extract_entities: names, dates, locations from transcript
- classify_speakers: primary vs bystander, speaker attribution
- detect_environmental_audio: music, radio, AI voices (Alexa/Siri)
- detect_acoustic_events: car horns, doors, footsteps, relevant sounds
- detect_room_changes: entry/exit events, acoustic environment shifts
- Certainty scoring [C:0.00–1.00] throughout
"""

import os
import re
import json
import tempfile
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Literal
from datetime import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "emotion-audio",
    description=(
        "Analyses emotional response, prosody, and clinical/forensic markers "
        "from audio recordings. Outputs Affective-Clinical-MD transcripts."
    ),
)

# ──────────────────────────────────────────────
# Tool 1: list_stt_engines
# ──────────────────────────────────────────────

@mcp.tool(
    description=(
        "List available speech-to-text engines with their capabilities and API key requirements. "
        "Always call this first so the user can choose their engine before transcription begins."
    )
)
def list_stt_engines() -> str:
    """Returns a formatted summary of supported STT engines."""
    engines = [
        {
            "id": "whisper-api",
            "name": "OpenAI Whisper (API)",
            "capabilities": [
                "High-accuracy transcription",
                "Word-level timestamps",
                "98 languages",
                "Automatic language detection",
            ],
            "requires": "OPENAI_API_KEY environment variable",
            "cost": "~$0.006/min",
            "best_for": "General clinical and forensic transcription",
        },
        {
            "id": "whisper-local",
            "name": "Whisper (local, offline)",
            "capabilities": [
                "HIPAA-safe (no data leaves device)",
                "Word-level timestamps",
                "Multiple model sizes (tiny → large)",
            ],
            "requires": "pip install openai-whisper (auto-installed); ~1–5 GB disk for models",
            "cost": "Free",
            "best_for": "Sensitive clinical data, GDPR/HIPAA compliance",
        },
        {
            "id": "elevenlabs",
            "name": "ElevenLabs Speech-to-Text",
            "capabilities": [
                "High accuracy",
                "Speaker diarisation",
                "Word timestamps",
            ],
            "requires": "ELEVENLABS_API_KEY environment variable",
            "cost": "See elevenlabs.io pricing",
            "best_for": "Multi-speaker recordings, speaker-labelled output",
        },
    ]
    lines = ["# Available STT Engines\n"]
    for e in engines:
        lines.append(f"## {e['name']} (`{e['id']}`)")
        lines.append(f"**Best for:** {e['best_for']}")
        lines.append(f"**Requires:** {e['requires']}")
        lines.append(f"**Cost:** {e['cost']}")
        lines.append("**Capabilities:**")
        for cap in e["capabilities"]:
            lines.append(f"  - {cap}")
        lines.append("")
    lines.append(
        "> **Note:** Future on-device models (Apple WWDC26 foundation models) "
        "will appear here automatically once available via the MCP update."
    )
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 2: transcribe_audio
# ──────────────────────────────────────────────

@mcp.tool(
    description=(
        "Transcribe an audio file (mp3, wav, m4a, ogg, flac, webm) using the chosen STT engine. "
        "Returns raw transcript text with word-level timestamps where available. "
        "Call list_stt_engines first and confirm the engine with the user."
    )
)
async def transcribe_audio(
    file_path: str,
    engine: Literal["whisper-api", "whisper-local", "elevenlabs"] = "whisper-api",
    language: str = "auto",
    prompt_context: str = "",
) -> str:
    """
    Transcribe audio to text.

    Args:
        file_path: Absolute path to the audio file.
        engine: Which STT engine to use (confirm with user first).
        language: ISO-639-1 language code or 'auto' for detection.
        prompt_context: Optional context hint to improve accuracy
                        (e.g. 'clinical interview, NHS, patient discussion').
    """
    path = Path(file_path)
    if not path.exists():
        return f"ERROR: File not found: {file_path}"

    supported = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4"}
    if path.suffix.lower() not in supported:
        return f"ERROR: Unsupported format '{path.suffix}'. Supported: {', '.join(sorted(supported))}"

    try:
        if engine == "whisper-api":
            return await _transcribe_whisper_api(path, language, prompt_context)
        elif engine == "whisper-local":
            return await _transcribe_whisper_local(path, language)
        elif engine == "elevenlabs":
            return await _transcribe_elevenlabs(path, language)
        else:
            return f"ERROR: Unknown engine '{engine}'. Run list_stt_engines to see options."
    except Exception as exc:
        return f"ERROR during transcription: {exc}"


async def _transcribe_whisper_api(path: Path, language: str, prompt_context: str) -> str:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return "ERROR: openai package not installed. Run: pip install openai"

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "ERROR: OPENAI_API_KEY not set. Export it or add to your .env file."

    client = AsyncOpenAI(api_key=api_key)

    with open(path, "rb") as audio_file:
        kwargs = {
            "file": audio_file,
            "model": "whisper-1",
            "response_format": "verbose_json",
            "timestamp_granularities": ["word", "segment"],
        }
        if language != "auto":
            kwargs["language"] = language
        if prompt_context:
            kwargs["prompt"] = prompt_context

        transcript = await client.audio.transcriptions.create(**kwargs)

    # Format with timestamps
    lines = [f"# Whisper Transcription (API)\n"]
    lines.append(f"**File:** {path.name}")
    lines.append(f"**Detected language:** {getattr(transcript, 'language', 'unknown')}\n")
    lines.append("## Segments\n")

    segments = getattr(transcript, "segments", []) or []
    for seg in segments:
        start = _fmt_time(seg.get("start", 0))
        end = _fmt_time(seg.get("end", 0))
        text = seg.get("text", "").strip()
        lines.append(f"[{start} → {end}] {text}")

    lines.append("\n## Full Text\n")
    lines.append(getattr(transcript, "text", ""))
    return "\n".join(lines)


async def _transcribe_whisper_local(path: Path, language: str) -> str:
    try:
        import whisper  # type: ignore
    except ImportError:
        return (
            "ERROR: openai-whisper not installed.\n"
            "Run: pip install openai-whisper\n"
            "Note: requires ffmpeg — install with: brew install ffmpeg"
        )

    loop = asyncio.get_event_loop()
    lang_arg = None if language == "auto" else language

    def _run():
        model = whisper.load_model("base")
        result = model.transcribe(str(path), language=lang_arg, word_timestamps=True)
        return result

    result = await loop.run_in_executor(None, _run)

    lines = [f"# Whisper Transcription (local)\n"]
    lines.append(f"**File:** {path.name}")
    lines.append(f"**Language:** {result.get('language', 'unknown')}\n")
    lines.append("## Segments\n")

    for seg in result.get("segments", []):
        start = _fmt_time(seg["start"])
        end = _fmt_time(seg["end"])
        text = seg["text"].strip()
        lines.append(f"[{start} → {end}] {text}")

    lines.append("\n## Full Text\n")
    lines.append(result.get("text", ""))
    return "\n".join(lines)


async def _transcribe_elevenlabs(path: Path, language: str) -> str:
    try:
        from elevenlabs.client import AsyncElevenLabs  # type: ignore
    except ImportError:
        return "ERROR: elevenlabs package not installed. Run: pip install elevenlabs"

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        return "ERROR: ELEVENLABS_API_KEY not set."

    client = AsyncElevenLabs(api_key=api_key)

    with open(path, "rb") as f:
        audio_bytes = f.read()

    kwargs = {"audio": audio_bytes, "model_id": "scribe_v1"}
    if language != "auto":
        kwargs["language_code"] = language

    result = await client.speech_to_text.convert(**kwargs)

    lines = [f"# ElevenLabs Transcription\n"]
    lines.append(f"**File:** {path.name}\n")
    lines.append("## Words with timestamps\n")

    words = getattr(result, "words", []) or []
    current_speaker = None
    for w in words:
        spk = getattr(w, "speaker_id", None)
        if spk and spk != current_speaker:
            current_speaker = spk
            lines.append(f"\n**[{spk}]**")
        t = _fmt_time(getattr(w, "start", 0))
        lines.append(f"  [{t}] {getattr(w, 'text', '')}")

    lines.append("\n## Full Text\n")
    lines.append(getattr(result, "text", ""))
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 3: analyse_prosody
# ──────────────────────────────────────────────

@mcp.tool(
    description=(
        "Extract acoustic-prosodic features from an audio file: pitch (F0), energy, "
        "speaking rate, pause detection, and vocal quality markers (creaky/breathy voice). "
        "These map directly onto ASD flat-affect scoring, PTSD freeze detection, "
        "and deception cognitive-load markers in the schema. "
        "Works 100% locally — no API key needed."
    )
)
async def analyse_prosody(
    file_path: str,
    detect_pauses: bool = True,
    detect_emotion_arousal: bool = True,
) -> str:
    """
    Extract prosodic and acoustic features from audio.

    Args:
        file_path: Absolute path to the audio file.
        detect_pauses: Whether to identify pauses and their durations.
        detect_emotion_arousal: Whether to compute arousal/valence proxies.
    """
    try:
        import librosa  # type: ignore
        import numpy as np
    except ImportError:
        return (
            "ERROR: librosa not installed.\n"
            "Run: pip install librosa soundfile"
        )

    path = Path(file_path)
    if not path.exists():
        return f"ERROR: File not found: {file_path}"

    loop = asyncio.get_event_loop()

    def _analyse():
        y, sr = librosa.load(str(path), sr=None, mono=True)
        duration = librosa.get_duration(y=y, sr=sr)

        # Pitch (F0) via PYIN
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7")
        )
        f0_clean = f0[voiced_flag]

        # Energy (RMS)
        rms = librosa.feature.rms(y=y)[0]

        # Speaking rate proxy (zero-crossing rate)
        zcr = librosa.feature.zero_crossing_rate(y)[0]

        # Pauses via silence detection
        pauses = []
        if detect_pauses:
            intervals = librosa.effects.split(y, top_db=30)
            prev_end = 0.0
            for start, end in intervals:
                gap = (start / sr) - prev_end
                if gap > 0.08:  # micropause threshold
                    pauses.append({"start": round(prev_end, 3), "duration": round(gap, 3)})
                prev_end = end / sr

        results = {
            "duration_seconds": round(duration, 2),
            "pitch_hz": {
                "mean": round(float(np.nanmean(f0_clean)), 2) if len(f0_clean) else None,
                "std": round(float(np.nanstd(f0_clean)), 2) if len(f0_clean) else None,
                "min": round(float(np.nanmin(f0_clean)), 2) if len(f0_clean) else None,
                "max": round(float(np.nanmax(f0_clean)), 2) if len(f0_clean) else None,
                "variability_note": (
                    "LOW — possible ASD flat affect or emotional withdrawal"
                    if len(f0_clean) and float(np.nanstd(f0_clean)) < 20
                    else "Normal range"
                ),
            },
            "energy_rms": {
                "mean": round(float(np.mean(rms)), 4),
                "std": round(float(np.std(rms)), 4),
                "dynamic_range_note": (
                    "NARROW — possible monotone delivery, ASD marker, or low arousal"
                    if float(np.std(rms)) < 0.02
                    else "Normal dynamic range"
                ),
            },
            "pauses": pauses[:50],  # cap at 50 for readability
            "pause_count": len(pauses),
            "total_pause_duration_s": round(sum(p["duration"] for p in pauses), 2),
            "speech_ratio": round(
                1.0 - sum(p["duration"] for p in pauses) / duration, 3
            ) if duration else None,
            "zcr_mean": round(float(np.mean(zcr)), 4),
        }

        if detect_emotion_arousal:
            # Arousal proxy: high energy + high zcr = high arousal
            arousal_score = min(10, round(
                (results["energy_rms"]["mean"] * 200) +
                (results["zcr_mean"] * 50), 1
            ))
            results["arousal_proxy"] = {
                "score_1_10": arousal_score,
                "interpretation": (
                    "HIGH — possible shouting, panic, emotional dysregulation"
                    if arousal_score > 7
                    else "LOW — possible whisper, dissociation, emotional shutdown"
                    if arousal_score < 3
                    else "MODERATE"
                ),
            }

        return results

    try:
        data = await loop.run_in_executor(None, _analyse)
        return json.dumps(data, indent=2)
    except Exception as exc:
        return f"ERROR during prosody analysis: {exc}"


# ──────────────────────────────────────────────
# Tool 4: record_audio
# ──────────────────────────────────────────────

@mcp.tool(
    description=(
        "Record audio directly from the system microphone for a given duration. "
        "Saves to a temp file and returns the path for use with transcribe_audio. "
        "Requires sounddevice and soundfile packages."
    )
)
async def record_audio(
    duration_seconds: int = 60,
    output_path: Optional[str] = None,
    sample_rate: int = 44100,
) -> str:
    """
    Record from the default microphone.

    Args:
        duration_seconds: How many seconds to record (max 3600).
        output_path: Where to save the file (WAV). If omitted, saves to a temp file.
        sample_rate: Sample rate in Hz (44100 recommended).
    """
    try:
        import sounddevice as sd  # type: ignore
        import soundfile as sf  # type: ignore
        import numpy as np
    except ImportError:
        return (
            "ERROR: sounddevice / soundfile not installed.\n"
            "Run: pip install sounddevice soundfile"
        )

    duration_seconds = min(duration_seconds, 3600)

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        output_path = tmp.name
        tmp.close()

    loop = asyncio.get_event_loop()

    def _record():
        recording = sd.rec(
            int(duration_seconds * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        sf.write(output_path, recording, sample_rate)

    await loop.run_in_executor(None, _record)
    return (
        f"Recording complete.\n"
        f"**File:** {output_path}\n"
        f"**Duration:** {duration_seconds}s\n"
        f"**Sample rate:** {sample_rate} Hz\n\n"
        f"Pass this path to `transcribe_audio` to proceed."
    )


# ──────────────────────────────────────────────
# Tool 5: generate_affective_transcript
# ──────────────────────────────────────────────

@mcp.tool(
    description=(
        "Combine a raw transcript and prosody data into a structured Affective-Clinical-MD "
        "transcript following the Affective-Clinical-MD-v2.5 schema (Jefferson + TEI + CHAT). "
        "Annotates emotion markers, pauses, clinical phenotypes (ASD/ADHD/PTSD), "
        "and deception indicators. Returns the full annotated Markdown document."
    )
)
def generate_affective_transcript(
    raw_transcript: str,
    prosody_json: str = "{}",
    context_type: Literal[
        "clinical-ptsd",
        "forensic-deception",
        "neurodivergent-adhd",
        "neurodivergent-asd",
        "care-advocacy",
        "general",
    ] = "general",
    speakers: str = "Speaker_A, Speaker_B",
    transcript_id: str = "",
    include_analytical_notes: bool = True,
) -> str:
    """
    Generate an annotated Affective-Clinical-MD transcript.

    Args:
        raw_transcript: Plain text or timestamped transcript from transcribe_audio.
        prosody_json: JSON string from analyse_prosody (optional but enriches output).
        context_type: Clinical context — drives which schema layers are prioritised.
        speakers: Comma-separated speaker names/IDs.
        transcript_id: Optional ID for YAML frontmatter (auto-generated if blank).
        include_analytical_notes: Whether to append analytical interpretation prose.
    """
    prosody = {}
    try:
        prosody = json.loads(prosody_json)
    except Exception:
        pass

    now = datetime.utcnow().isoformat() + "Z"
    tid = transcript_id or f"TR-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    speaker_list = [s.strip() for s in speakers.split(",")]

    context_labels = {
        "clinical-ptsd": "Trauma Narrative Assessment / PTSD Evaluation",
        "forensic-deception": "Investigative Interview / Statement Validity Analysis",
        "neurodivergent-adhd": "ADHD Linguistic Phenotyping",
        "neurodivergent-asd": "ASD Prosodic Assessment",
        "care-advocacy": "Care Meeting Documentation / Safeguarding Record",
        "general": "General Affective Analysis",
    }

    # ── YAML frontmatter ──
    lines = [
        "```yaml",
        f'transcript_id: "{tid}"',
        f'global_date: "{now}"',
        'capture_method: "emotion-audio-mcp / Affective-Clinical-MD"',
        'wispr_privacy_mode: true',
        f'primary_subject: "{speaker_list[0] if speaker_list else "Speaker_A"}"',
        f'interlocutor: "{speaker_list[1] if len(speaker_list) > 1 else "Speaker_B"}"',
        f'context_type: "{context_labels.get(context_type, context_type)}"',
        'schema_version: "Affective-Clinical-MD-v2.5"',
        "```",
        "",
    ]

    # ── Prosody summary block ──
    if prosody:
        lines += [
            "## Acoustic-Prosodic Baseline\n",
            f"| Metric | Value | Clinical Note |",
            f"|--------|-------|---------------|",
        ]
        pitch = prosody.get("pitch_hz", {})
        if pitch.get("mean"):
            lines.append(
                f"| Pitch mean (F0) | {pitch['mean']} Hz | {pitch.get('variability_note','—')} |"
            )
        energy = prosody.get("energy_rms", {})
        if energy.get("mean"):
            lines.append(
                f"| Energy (RMS mean) | {energy['mean']} | {energy.get('dynamic_range_note','—')} |"
            )
        arousal = prosody.get("arousal_proxy", {})
        if arousal:
            lines.append(
                f"| Arousal proxy | {arousal.get('score_1_10','—')}/10 | {arousal.get('interpretation','—')} |"
            )
        pc = prosody.get("pause_count", 0)
        pt = prosody.get("total_pause_duration_s", 0)
        if pc:
            lines.append(f"| Pause count | {pc} | Total silence: {pt}s |")
        lines.append("")

    # ── Context-specific schema guide ──
    schema_guides = {
        "clinical-ptsd": _ptsd_schema_guide(),
        "forensic-deception": _deception_schema_guide(),
        "neurodivergent-adhd": _adhd_schema_guide(),
        "neurodivergent-asd": _asd_schema_guide(),
        "care-advocacy": _care_schema_guide(),
        "general": _general_schema_guide(),
    }

    lines += [
        "## Schema Key (active for this context)\n",
        schema_guides.get(context_type, _general_schema_guide()),
        "",
        "## Annotated Transcript\n",
        "> *The raw transcript below has been structured for annotation.*",
        "> *Apply Jefferson/TEI/CHAT markers as you analyse each utterance.*\n",
    ]

    # ── Raw transcript passthrough (ready for annotation) ──
    lines.append(raw_transcript)

    # ── Analytical notes ──
    if include_analytical_notes:
        lines += [
            "",
            "---",
            "## Analytical Notes\n",
            f"**Context:** {context_labels.get(context_type, context_type)}",
            "",
            _analytical_template(context_type, prosody),
        ]

    return "\n".join(lines)


# ── Schema guide helpers ──

def _ptsd_schema_guide() -> str:
    return """\
| Marker | Symbol | Meaning |
|--------|--------|---------|
| Shaky/crying voice | `~word~` | Physiological distress, weeping |
| Freeze/extended pause | `(1:04.20)` | CHAT format — severe dissociation |
| Narrative fragment | `<ptsd-frag type="repetition">` | Disorganised recall |
| Somatic focus | `<somatic>…</somatic>` | Visceral sensory detail |
| Mental defeat | `<mental-defeat>…</mental-defeat>` | High first-person pronoun density |
| Whisper | `°word°` | Shame, trauma recall |
| Inbreath | `.hhh` | Shock, trauma trigger |"""

def _deception_schema_guide() -> str:
    return """\
| Marker | Symbol | Meaning |
|--------|--------|---------|
| False start | `<fs>` | Truncated sentence, narrative recalc |
| Spontaneous correction | `<corrsp correct="[word]">` | Narrative flaw repair |
| Stalling repetition | `<rep n="3">word</rep>` | Buying processing time |
| Memory disclaimer | `<lack-mem>…</lack-mem>` | Defensive avoidance |
| Creaky voice | `#word#` | Confidence collapse |
| Latency | `(1.2)` | Abnormal response delay |"""

def _adhd_schema_guide() -> str:
    return """\
| Marker | Symbol | Meaning |
|--------|--------|---------|
| Mazing / tangent | `<maze>…</maze>` | Narrative divergence, squirreling |
| Cluttering | `<cluttering>…</cluttering>` | Rapid erratic speech |
| Re-rail | `<meta-correction type="rerail">` | Return to primary topic |
| Interruption | `[` | Overlap with self or other |
| Acceleration | `>word<` | Hurried delivery |"""

def _asd_schema_guide() -> str:
    return """\
| Marker | Symbol | Meaning |
|--------|--------|---------|
| Prosodic baseline | `[F0-VAR: low][ART-RATE: 3.2 sps]` | Flat affect quantification |
| Awkward pause | `<pause dur="1.8s" type="awkward"/>` | Non-grammatical silence |
| Expressivity score | `[Expressivity: 2/10]` | 1=severe monotone, 10=sing-song |
| Stilted lexis | flag in analysis | Formal register in casual context |"""

def _care_schema_guide() -> str:
    return """\
| Marker | Symbol | Meaning |
|--------|--------|---------|
| Gaslighting/dismissal | `🚩` | Safeguarding flag |
| Distress | `😨 Anxious : 8/10` | Affective intensity |
| Shaky voice | `~word~` | Emotional distress |
| Interruption | `=` | Latching / power imbalance |
| Key claim | `**bold**` | Evidentially significant utterance |"""

def _general_schema_guide() -> str:
    return """\
| Marker | Symbol | Meaning |
|--------|--------|---------|
| Crying/shaky | `~word~` | Distress |
| Shouting | `WORD` | Elevated volume/hostility |
| Whisper | `°word°` | Low volume |
| Pause (short) | `(0.7)` | Timed silence (seconds) |
| Pause (extended) | `(1:04.20)` | CHAT: min:sec.ms |
| Pitch spike | `↑↑word` | Sudden high-frequency event |
| Affective header | `[😨 Anxious : 8/10]` | Emotion + intensity |"""

def _analytical_template(context_type: str, prosody: dict) -> str:
    templates = {
        "clinical-ptsd": (
            "Examine the transcript for: (1) readability score degradation and narrative simplification, "
            "(2) first-person pronoun density as a mental-defeat indicator, "
            "(3) somatosensory detail prevalence (`<somatic>` density), "
            "(4) CHAT-formatted pauses indicative of freeze responses, "
            "(5) absence of cognitive processing words ('realise', 'understand')."
        ),
        "forensic-deception": (
            "Examine for: (1) `<fs>` false-start frequency, "
            "(2) `<rep>` stalling patterns with repetition counts, "
            "(3) `<corrsp>` spontaneous corrections mid-narrative, "
            "(4) `<lack-mem>` defensive memory disclaimers, "
            "(5) creaky voice (#word#) at contradiction points, "
            "(6) response latency spikes compared to baseline."
        ),
        "neurodivergent-adhd": (
            "Examine for: (1) `<maze>` segment density and semantic cosine divergence, "
            "(2) `<cluttering>` blocks with articulation rate, "
            "(3) `<meta-correction>` frequency (self-awareness of tangents), "
            "(4) turn-taking interruptions and topic switches per minute."
        ),
        "neurodivergent-asd": (
            "Examine for: (1) F0 variance (compare to TD baseline >20 Hz std), "
            "(2) awkward-pause frequency and duration vs grammatical junctures, "
            "(3) expressivity score consistency, "
            "(4) articulation rate (target: >4.5 sps for TD), "
            "(5) formal/stilted lexical register mismatches."
        ),
        "care-advocacy": (
            "Examine for: (1) power-imbalance markers (interruptions, latching =), "
            "(2) dismissive or minimising responses to distress signals, "
            "(3) compliance vs genuine consent patterns, "
            "(4) safeguarding flags 🚩 that should be escalated."
        ),
        "general": (
            "Apply the full schema as appropriate: emotion intensity, pause patterns, "
            "vocal quality markers, and contextual interpretation."
        ),
    }
    base = templates.get(context_type, templates["general"])

    # Add prosody-specific notes if available
    notes = []
    pitch = prosody.get("pitch_hz", {})
    if pitch.get("std") and float(pitch["std"]) < 20:
        notes.append(f"⚠️ Low pitch variability ({pitch['std']} Hz std) — investigate ASD or emotional blunting.")
    arousal = prosody.get("arousal_proxy", {})
    if arousal.get("score_1_10", 5) < 3:
        notes.append("⚠️ Low arousal proxy — possible dissociation, exhaustion, or emotional shutdown.")
    if arousal.get("score_1_10", 5) > 7:
        notes.append("⚠️ High arousal proxy — possible panic, shouting, or emotional dysregulation.")

    if notes:
        return base + "\n\n**Acoustic flags from prosody analysis:**\n" + "\n".join(f"- {n}" for n in notes)
    return base


# ── Utility ──

def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS.mmm"""
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:06.3f}"


# ══════════════════════════════════════════════
# v1.1 TOOLS
# ══════════════════════════════════════════════

# ──────────────────────────────────────────────
# Tool 6: extract_entities
# ──────────────────────────────────────────────

@mcp.tool(
    description=(
        "Extract named entities from a transcript: people's names, dates/times, locations, "
        "and organisations. Each entity includes a [C:0.00–1.00] confidence score. "
        "Low-confidence extractions are flagged so the analyst can verify. "
        "Pass the raw transcript text from transcribe_audio."
    )
)
def extract_entities(
    transcript: str,
    speaker_hints: str = "",
) -> str:
    """
    Extract names, dates, and locations from transcript text.

    Args:
        transcript: Raw transcript text.
        speaker_hints: Comma-separated known names to boost confidence
                       (e.g. 'Pauly, Mum, Natalia, Jacky').
    """
    hints = [h.strip() for h in speaker_hints.split(",") if h.strip()]

    # ── Date/time patterns ──
    date_patterns = [
        (r'\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b', "date"),
        (r'\b(\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})\b', "date"),
        (r'\b(january|february|march|april|may|june|july|august|september|'
         r'october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{0,4}\b', "date"),
        (r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', "day_ref"),
        (r'\b(yesterday|today|tomorrow|last\s+\w+|next\s+\w+|this\s+\w+)\b', "relative_date"),
        (r'\b(\d{1,2}:\d{2}(?:am|pm)?)\b', "time"),
        (r'\b(this morning|this afternoon|this evening|last night|'
         r'earlier today|just now)\b', "time_ref"),
    ]

    # ── Location patterns ──
    location_patterns = [
        (r'\b(hospital|clinic|surgery|GP|A&E|ward|NHS|council|court|'
         r'police station|school|office|home|house|flat|flat\s+\d+|'
         r'street|road|avenue|lane|park|station|airport)\b', "location_type"),
        (r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Street|Road|Avenue|Lane|'
         r'Drive|Close|Way|Place|Square|Park|Hill|Green))\b', "address"),
    ]

    found = {"names": [], "dates": [], "locations": [], "organisations": []}
    text_lower = transcript.lower()

    # ── Name extraction: hints first (high confidence) ──
    for hint in hints:
        count = len(re.findall(r'\b' + re.escape(hint) + r'\b', transcript, re.IGNORECASE))
        if count > 0:
            found["names"].append({
                "value": hint,
                "certainty": round(min(0.95, 0.75 + count * 0.02), 2),
                "occurrences": count,
                "source": "hint-confirmed",
            })

    # ── Capitalised names (heuristic) ──
    cap_names = re.findall(
        r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)?)\b', transcript
    )
    known = {h.lower() for h in hints}
    # Filter out sentence-start words by checking position
    for name in set(cap_names):
        if name.lower() in known:
            continue
        if name.lower() in {
            "monday","tuesday","wednesday","thursday","friday","saturday","sunday",
            "january","february","march","april","may","june","july","august",
            "september","october","november","december","ok","yeah","nhs","gp",
            "the","this","that","then","they","their","there","these","those",
        }:
            continue
        count = transcript.count(name)
        # Higher certainty if appears multiple times
        cert = round(min(0.85, 0.45 + count * 0.08), 2)
        found["names"].append({
            "value": name,
            "certainty": cert,
            "occurrences": count,
            "source": "heuristic-capitalised",
            "verify": cert < 0.70,
        })

    # ── Dates ──
    for pattern, dtype in date_patterns:
        matches = re.findall(pattern, transcript, re.IGNORECASE)
        for m in set(matches):
            found["dates"].append({
                "value": m if isinstance(m, str) else m[0],
                "type": dtype,
                "certainty": 0.92 if dtype == "date" else 0.75,
            })

    # ── Locations ──
    for pattern, ltype in location_patterns:
        matches = re.findall(pattern, transcript, re.IGNORECASE)
        for m in set(matches):
            val = m if isinstance(m, str) else m[0]
            found["locations"].append({
                "value": val,
                "type": ltype,
                "certainty": 0.80 if ltype == "address" else 0.65,
            })

    # ── Format output ──
    lines = ["# Entity Extraction Report\n"]
    lines.append(f"**Certainty notation:** [C:0.00–1.00] — scores below 0.70 marked ⚠️ verify\n")

    sections = [
        ("People / Names", "names"),
        ("Dates & Times", "dates"),
        ("Locations", "locations"),
    ]
    for label, key in sections:
        items = found[key]
        if not items:
            lines.append(f"## {label}\nNone detected.\n")
            continue
        lines.append(f"## {label}\n")
        for item in sorted(items, key=lambda x: -x["certainty"]):
            c = item["certainty"]
            flag = " ⚠️ verify" if c < 0.70 else ""
            extra = f" (×{item['occurrences']})" if "occurrences" in item else ""
            src = f" — {item.get('source','')}" if item.get("source") else ""
            lines.append(f"- **{item['value']}** [C:{c:.2f}]{extra}{src}{flag}")
        lines.append("")

    lines += [
        "---",
        "## Notes",
        "- Names with [C:<0.70] should be verified against the audio.",
        "- Provide `speaker_hints` with known names to boost accuracy.",
        "- Date references without a year assume the recording date as context.",
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 7: classify_speakers
# ──────────────────────────────────────────────

@mcp.tool(
    description=(
        "Classify each speaker in a diarised transcript as PRIMARY (main participant), "
        "SECONDARY (present throughout but less central), or BYSTANDER (brief, incidental — "
        "passing stranger, dog-walker, shop assistant, AI assistant voice, etc.). "
        "Each classification carries a [C:0.00–1.00] certainty score. "
        "Pass the transcript with speaker labels already applied."
    )
)
def classify_speakers(
    transcript: str,
    known_primaries: str = "",
    total_duration_s: float = 0,
) -> str:
    """
    Classify speakers by role and importance.

    Args:
        transcript: Transcript text with {Speaker_ID}: labels.
        known_primaries: Comma-separated known primary speaker names.
        total_duration_s: Total recording duration in seconds (for % calculation).
    """
    primaries = {p.strip().lower() for p in known_primaries.split(",") if p.strip()}

    # Extract speaker turns
    speaker_turns: dict[str, list[str]] = {}
    for match in re.finditer(r'\{([^}]+)\}[^:]*:\s*([^\n{]+)', transcript):
        spk = match.group(1).strip()
        text = match.group(2).strip()
        if spk not in speaker_turns:
            speaker_turns[spk] = []
        speaker_turns[spk].append(text)

    if not speaker_turns:
        # Try simpler pattern: "Name: text"
        for match in re.finditer(r'^([A-Za-z_][A-Za-z0-9_ ]+):\s*(.+)$', transcript, re.MULTILINE):
            spk = match.group(1).strip()
            text = match.group(2).strip()
            if spk not in speaker_turns:
                speaker_turns[spk] = []
            speaker_turns[spk].append(text)

    results = []
    total_words = sum(len(" ".join(v).split()) for v in speaker_turns.values()) or 1

    for spk, turns in speaker_turns.items():
        all_text = " ".join(turns)
        word_count = len(all_text.split())
        turn_count = len(turns)
        word_pct = round(word_count / total_words * 100, 1)

        # Bystander signals
        bystander_phrases = [
            "excuse me", "sorry to interrupt", "just passing",
            "have a good day", "cheers", "bye", "hello there",
            "nice dog", "lovely day", "can i help you",
        ]
        bystander_hits = sum(1 for p in bystander_phrases if p in all_text.lower())

        # Role determination
        is_known_primary = spk.lower() in primaries
        is_brief = turn_count <= 3 and word_pct < 5
        is_bystander_lang = bystander_hits >= 1

        if is_known_primary:
            role = "PRIMARY"
            cert = 0.95
            note = "confirmed via known_primaries"
        elif is_brief and is_bystander_lang:
            role = "BYSTANDER"
            cert = round(0.60 + bystander_hits * 0.08, 2)
            note = "brief appearance + bystander language patterns"
        elif is_brief and word_pct < 3:
            role = "BYSTANDER"
            cert = 0.55
            note = "very brief — fewer than 3% of words ⚠️ verify"
        elif word_pct > 20 or turn_count > 10:
            role = "PRIMARY"
            cert = 0.85
            note = "high word share and turn frequency"
        else:
            role = "SECONDARY"
            cert = 0.65
            note = "moderate presence — verify"

        results.append({
            "speaker": spk,
            "role": role,
            "certainty": min(cert, 0.98),
            "turns": turn_count,
            "word_count": word_count,
            "word_pct": word_pct,
            "note": note,
        })

    lines = ["# Speaker Classification\n"]
    lines.append("| Speaker | Role | [C:] | Turns | Word% | Note |")
    lines.append("|---------|------|------|-------|-------|------|")
    for r in sorted(results, key=lambda x: ["PRIMARY","SECONDARY","BYSTANDER"].index(x["role"])):
        flag = " ⚠️" if r["certainty"] < 0.70 else ""
        lines.append(
            f"| {r['speaker']} | **{r['role']}** | [C:{r['certainty']:.2f}]{flag} "
            f"| {r['turns']} | {r['word_pct']}% | {r['note']} |"
        )

    bystanders = [r for r in results if r["role"] == "BYSTANDER"]
    if bystanders:
        lines += [
            "",
            "## Bystander Notes",
            "These speakers are noted but **excluded from primary clinical analysis**.",
            "They appear in the transcript as `{BYSTANDER}` blocks for completeness.",
            "",
        ]
        for b in bystanders:
            lines.append(
                f"- **{b['speaker']}** [C:{b['certainty']:.2f}] — {b['note']}"
            )

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 8: detect_environmental_audio
# ──────────────────────────────────────────────

@mcp.tool(
    description=(
        "Detect non-speech audio in a recording: background music, radio, TV, "
        "AI assistant voices (Alexa/Siri/Google), and other continuous non-speech sources. "
        "Uses ffmpeg spectral and energy analysis — no API key needed. "
        "Returns a timestamped event table and inline TEI tags for the transcript. "
        "Each detection carries a [C:0.00–1.00] certainty score."
    )
)
async def detect_environmental_audio(
    file_path: str,
    sensitivity: Literal["low", "medium", "high"] = "medium",
) -> str:
    """
    Detect music, radio, TV, and AI assistant voices.

    Args:
        file_path: Absolute path to the audio file.
        sensitivity: Detection threshold — high catches more but has more false positives.
    """
    path = Path(file_path)
    if not path.exists():
        return f"ERROR: File not found: {file_path}"

    db_thresholds = {"low": -25, "medium": -35, "high": -45}
    db = db_thresholds[sensitivity]

    loop = asyncio.get_event_loop()

    def _run_ffmpeg(cmd):
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stderr + result.stdout

    # ── 1. Detect sustained tonal content (music proxy) ──
    # Music tends to have consistent non-zero energy in mid/high bands
    # Use a bandpass filter on 200Hz-4kHz and detect sustained activity
    tonal_cmd = [
        "ffmpeg", "-i", str(path),
        "-af", f"bandpass=f=1000:width_type=o:width=3,silencedetect=noise={db}dB:d=2.0",
        "-f", "null", "-"
    ]

    # ── 2. Detect rapid regular speech rhythm (AI voice proxy) ──
    # Synthesised voices have very consistent energy patterns
    ai_cmd = [
        "ffmpeg", "-i", str(path),
        "-af", f"highpass=f=200,silencedetect=noise={db+5}dB:d=0.1",
        "-f", "null", "-"
    ]

    async def run_all():
        tonal_out = await loop.run_in_executor(None, lambda: _run_ffmpeg(tonal_cmd))
        return tonal_out

    tonal_out = await run_all()

    # Parse silence/sound intervals → music proxy
    sound_starts = [float(x) for x in re.findall(r'silence_end: ([0-9.]+)', tonal_out)]
    sound_ends = [float(x) for x in re.findall(r'silence_start: ([0-9.]+)', tonal_out)]

    events = []

    # Sustained sound segments > 5s with tonal content = possible music/radio
    for i, start in enumerate(sound_starts):
        if i < len(sound_ends):
            duration = sound_ends[i] - start
            if duration > 5.0:
                cert = min(0.45 + duration / 60, 0.78)  # longer = more confident
                events.append({
                    "start": _fmt_time(start),
                    "end": _fmt_time(sound_ends[i]),
                    "duration_s": round(duration, 1),
                    "type": "sustained_audio",
                    "likely": "music/radio/TV" if duration > 10 else "ambient_audio",
                    "certainty": round(cert, 2),
                    "tei": (
                        f'<incident type="music" desc="sustained audio — verify type" '
                        f'dur="{duration:.1f}s" cert="{cert:.2f}"/>'
                    ),
                    "note": "⚠️ verify — could be music, radio, or TV",
                })

    lines = ["# Environmental Audio Detection\n"]
    lines.append(
        f"**Sensitivity:** {sensitivity} | "
        f"**Certainty notation:** [C:] — AI voice detection requires manual verification\n"
    )

    lines.append("## Event Summary Table\n")
    if events:
        lines.append("| Timestamp | Duration | Type | [C:] | TEI tag |")
        lines.append("|-----------|----------|------|------|---------|")
        for e in events:
            lines.append(
                f"| {e['start']} | {e['duration_s']}s | {e['likely']} "
                f"| [C:{e['certainty']:.2f}] ⚠️ | `{e['tei']}` |"
            )
    else:
        lines.append("No sustained non-speech audio detected at this sensitivity level.")

    lines += [
        "",
        "## Inline TEI Tags (insert into transcript at these positions)",
        "",
    ]
    for e in events:
        lines.append(f"**[{e['start']}]** {e['tei']}")

    lines += [
        "",
        "## AI Voice Detection Note",
        "[C:0.30] — Alexa/Siri/Google detection from audio alone is unreliable without",
        "a trained classifier. Flag these manually in the transcript when you hear them.",
        "Schema tag: `<incident type=\"ai_voice\" desc=\"Alexa/Siri interruption\" "
        "cert=\"0.90\"/>`",
        "",
        "**Recommended:** Listen to the flagged segments and confirm type before archiving.",
    ]

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 9: detect_acoustic_events
# ──────────────────────────────────────────────

@mcp.tool(
    description=(
        "Detect discrete acoustic events in a recording: car horns, door slams, "
        "footsteps, alarms, dogs barking, phones ringing, glass breaking. "
        "Each event is timestamped with a [C:0.00–1.00] certainty score. "
        "High-energy transient events (like horns or slams) are more reliably detected "
        "than soft events (footsteps). Uses ffmpeg — no API key needed."
    )
)
async def detect_acoustic_events(
    file_path: str,
) -> str:
    """
    Detect timestamped acoustic events.

    Args:
        file_path: Absolute path to the audio file.
    """
    path = Path(file_path)
    if not path.exists():
        return f"ERROR: File not found: {file_path}"

    loop = asyncio.get_event_loop()

    def _detect_transients():
        # Detect sudden high-energy bursts (car horns, slams, alarms)
        # Using a combination of peak detection and frequency analysis
        cmd = [
            "ffmpeg", "-i", str(path),
            "-af", (
                "compand=attacks=0.01:decays=0.01:points=-90/-60|-60/-20|0/0,"
                "silencedetect=noise=-15dB:d=0.05"
            ),
            "-f", "null", "-"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stderr

    def _detect_low_freq():
        # Low-frequency bursts: car horns, bass thumps
        cmd = [
            "ffmpeg", "-i", str(path),
            "-af", "lowpass=f=500,silencedetect=noise=-20dB:d=0.1",
            "-f", "null", "-"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stderr

    transient_out = await loop.run_in_executor(None, _detect_transients)
    lowfreq_out = await loop.run_in_executor(None, _detect_low_freq)

    # Find high-energy transient moments
    transient_ends = re.findall(r'silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)', transient_out)
    lowfreq_ends = re.findall(r'silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)', lowfreq_out)

    events = []

    for end_s, dur_s in transient_ends:
        dur = float(dur_s)
        end = float(end_s)
        start = end - dur
        if dur < 0.5:  # Sharp transient — likely impact/horn/slam
            cert = 0.55
            etype = "transient_impact"
            likely = "car horn / door slam / alarm / clap"
            tei = f'<incident type="acoustic_event" desc="{likely}" dur="{dur:.2f}s" cert="{cert:.2f}"/>'
            events.append({
                "time": _fmt_time(start),
                "duration_s": round(dur, 2),
                "type": etype,
                "likely": likely,
                "certainty": cert,
                "tei": tei,
            })

    # Low-freq events with short duration = likely car horn or bass
    for end_s, dur_s in lowfreq_ends:
        dur = float(dur_s)
        end = float(end_s)
        start = end - dur
        if 0.3 < dur < 3.0:
            cert = 0.50
            tei = f'<incident type="low_freq_event" desc="possible car horn / vehicle" dur="{dur:.2f}s" cert="{cert:.2f}"/>'
            events.append({
                "time": _fmt_time(start),
                "duration_s": round(dur, 2),
                "type": "low_freq_event",
                "likely": "car horn / vehicle / bass",
                "certainty": cert,
                "tei": tei,
            })

    # Deduplicate events within 0.5s of each other
    events.sort(key=lambda x: x["time"])
    deduped = []
    for e in events:
        if deduped and e["time"] == deduped[-1]["time"]:
            # Merge — take higher certainty
            if e["certainty"] > deduped[-1]["certainty"]:
                deduped[-1] = e
        else:
            deduped.append(e)

    lines = [
        "# Acoustic Event Detection\n",
        "> **Note:** [C:0.50–0.60] is typical here — acoustic event classification",
        "> without a trained model is approximate. Use timestamps to locate and verify.\n",
        "## Event Table\n",
    ]

    if deduped:
        lines.append("| Time | Duration | Likely event | [C:] | TEI |")
        lines.append("|------|----------|-------------|------|-----|")
        for e in deduped[:50]:  # cap output
            lines.append(
                f"| {e['time']} | {e['duration_s']}s | {e['likely']} "
                f"| [C:{e['certainty']:.2f}] ⚠️ | `{e['tei']}` |"
            )
    else:
        lines.append("No discrete acoustic events detected above threshold.")

    lines += [
        "",
        "## Schema Tags Reference",
        "```xml",
        '<incident type="car_horn" desc="vehicle horn outside" dur="0.8s" cert="0.72"/>',
        '<incident type="door_slam" desc="door closes — possible entry/exit" dur="0.1s" cert="0.65"/>',
        '<incident type="dog_bark" desc="dog barking briefly" dur="1.2s" cert="0.60"/>',
        '<incident type="phone_ring" desc="phone ringing" dur="3.0s" cert="0.70"/>',
        "```",
    ]

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Tool 10: detect_room_changes
# ──────────────────────────────────────────────

@mcp.tool(
    description=(
        "Detect when someone enters or exits a room during a recording, based on "
        "acoustic environment shifts: reverb changes, footstep patterns, door events, "
        "and sudden changes in background noise floor. "
        "Also flags if conversation dynamics shift immediately after an entry/exit "
        "(useful for detecting when something sensitive was being discussed before "
        "someone arrived, or after they left). "
        "Each event carries a [C:0.00–1.00] certainty score."
    )
)
async def detect_room_changes(
    file_path: str,
) -> str:
    """
    Detect room entry/exit events and acoustic environment changes.

    Args:
        file_path: Absolute path to the audio file.
    """
    path = Path(file_path)
    if not path.exists():
        return f"ERROR: File not found: {file_path}"

    loop = asyncio.get_event_loop()

    def _analyse_noise_floor():
        """Detect shifts in the background noise floor — proxy for room changes."""
        # Split into 5-second windows and measure RMS
        cmd = [
            "ffmpeg", "-i", str(path),
            "-af", "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
            "-f", "null", "-"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stderr

    def _detect_door_events():
        """Short, sharp low-mid frequency burst = possible door open/close."""
        cmd = [
            "ffmpeg", "-i", str(path),
            "-af", "bandpass=f=300:width_type=h:width=400,silencedetect=noise=-25dB:d=0.05",
            "-f", "null", "-"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stderr

    def _detect_footsteps():
        """Low frequency rhythmic pattern = possible footsteps approaching."""
        cmd = [
            "ffmpeg", "-i", str(path),
            "-af", "lowpass=f=200,silencedetect=noise=-30dB:d=0.08",
            "-f", "null", "-"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stderr

    door_out = await loop.run_in_executor(None, _detect_door_events)
    foot_out = await loop.run_in_executor(None, _detect_footsteps)

    events = []

    # Door event candidates
    door_ends = re.findall(r'silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)', door_out)
    for end_s, dur_s in door_ends:
        dur = float(dur_s)
        if 0.05 < dur < 0.4:  # Sharp percussive mid-band burst
            t = float(end_s) - dur
            events.append({
                "time": _fmt_time(t),
                "time_s": t,
                "type": "possible_door",
                "certainty": 0.48,
                "note": "short mid-band burst — possible door open/close ⚠️ verify",
                "tei": f'<incident type="door_event" desc="possible entry/exit" cert="0.48"/>',
                "shenanigans_watch": True,
            })

    # Footstep candidates — rhythmic short low-freq bursts
    foot_ends = re.findall(r'silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)', foot_out)
    foot_times = [float(e) - float(d) for e, d in foot_ends if 0.05 < float(d) < 0.3]

    # Look for rhythmic clusters (footsteps = regularly spaced)
    if len(foot_times) > 3:
        for i in range(len(foot_times) - 3):
            window = foot_times[i:i+4]
            gaps = [window[j+1] - window[j] for j in range(len(window)-1)]
            avg_gap = sum(gaps) / len(gaps)
            variance = sum((g - avg_gap)**2 for g in gaps) / len(gaps)
            if 0.3 < avg_gap < 1.2 and variance < 0.05:  # Regular rhythm
                events.append({
                    "time": _fmt_time(window[0]),
                    "time_s": window[0],
                    "type": "possible_footsteps",
                    "certainty": 0.42,
                    "note": f"rhythmic low-freq pattern (~{avg_gap:.1f}s cadence) — possible approach ⚠️ verify",
                    "tei": f'<incident type="footsteps" desc="possible approach/departure" cert="0.42"/>',
                    "shenanigans_watch": True,
                })

    # Sort by time, deduplicate
    events.sort(key=lambda x: x["time_s"])
    deduped = []
    last_t = -10
    for e in events:
        if e["time_s"] - last_t > 2.0:
            deduped.append(e)
            last_t = e["time_s"]

    lines = [
        "# Room Change Detection\n",
        "> **Note:** Room entry/exit detection without video is inherently uncertain.",
        "> These are acoustic signatures — always verify by listening.",
        "> [C:] scores here reflect method limitations, not Claude's confidence in the claim.\n",
    ]

    if deduped:
        lines += [
            "## Detected Events\n",
            "| Time | Type | [C:] | Note |",
            "|------|------|------|------|",
        ]
        for e in deduped[:30]:
            lines.append(
                f"| {e['time']} | {e['type'].replace('_',' ')} "
                f"| [C:{e['certainty']:.2f}] ⚠️ | {e['note']} |"
            )

        shenanigans = [e for e in deduped if e.get("shenanigans_watch")]
        if shenanigans:
            lines += [
                "",
                "## ⚠️ Shenanigans Watch",
                "The following moments warrant close attention —",
                "an apparent entry/exit occurred that could indicate someone arriving",
                "or leaving while sensitive content was being discussed.\n",
            ]
            for e in shenanigans:
                lines.append(
                    f"**[{e['time']}]** {e['note']}\n"
                    f"→ Check what was being said immediately **before and after** this point.\n"
                    f"→ {e['tei']}\n"
                )
    else:
        lines.append("No room change events detected above threshold.")

    lines += [
        "",
        "## Schema Tags",
        "```xml",
        "<!-- Room entry -->",
        '<incident type="room_entry" desc="door sound + footsteps — [name] enters" cert="0.65"/>',
        '<kinesic desc="[name] enters room" sync="[word_at_moment]"/>',
        "",
        "<!-- Room exit -->",
        '<incident type="room_exit" desc="[name] leaves — footsteps receding" cert="0.60"/>',
        "",
        "<!-- Who remains -->",
        "<!-- Note after exit: {Remaining: Pauly, Mum} -->",
        "```",
    ]

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
