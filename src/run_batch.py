#!/usr/bin/env python3
"""
EMOTION AUDIO ANALYSER — BATCH DASHBOARD v3.1
Fixed terminal dashboard with live toggles, dual-mode cards, 3-level privacy.

Usage:
    python3 run_batch.py                          # Default: all features ON
    python3 run_batch.py --fast                   # Quick draft
    python3 run_batch.py --forensic               # Deception + veracity + clinical
    python3 run_batch.py --dir /path/to/audios    # Custom directory
    python3 run_batch.py --parallel 4             # 4 simultaneous
    python3 run_batch.py --help                   # All options

Keyboard shortcuts (press key, no Enter needed):
    [N] Names privacy:      REDACTED -> EMOJI -> FULL
    [P] Numbers privacy:    REDACTED -> EMOJI -> FULL
    [F] Card mode:          Emotional -> Technical
    [D] Deception:          ON/OFF (affects next queued file)
    [V] Veracity:           ON/OFF
    [J] Jefferson:          ON/OFF
    [C] Clinical:           ON/OFF
    [Q] Quit gracefully     (finish current, stop queuing)
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import termios
import threading
import time
import tty
from pathlib import Path
from datetime import datetime

# ─── Constants ────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
TRANSCRIPT_SCRIPT = SCRIPT_DIR / "run_transcription.py"

# ANSI escape codes
CLEAR = "\033[2J"
CLEAR_LINE = "\033[2K"
HOME = "\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
SAVE = "\033[s"
RESTORE = "\033[u"

# Colors
R = "\033[0;31m"
G = "\033[0;32m"
Y = "\033[1;33m"
B = "\033[0;34m"
P = "\033[0;35m"
C = "\033[0;36m"
W = "\033[1;37m"
D = "\033[2m"
BD = "\033[1m"
NC = "\033[0m"

MODELS = ["tiny", "base", "small", "medium", "large"]

# ─── State ────────────────────────────────────────────────────────────────────

class BatchState:
    def __init__(self):
        self.files = []  # list of dicts: {path, duration, size, model, safe_name, status, pid, start_time, output_dir}
        self.total_duration = 0
        self.total_tokens = 0
        self.completed = 0
        self.failed = 0
        self.running = 0
        self.start_time = time.time()
        self.quit_requested = False

        # Toggles (all ON by default)
        self.deception = True
        self.veracity = True
        self.jefferson = True
        self.clinical = True
        self.voice_dynamics = True
        self.emotional = True
        self.omni = True
        self.viewer = False
        self.diarise_local = False

        # Privacy levels: 0=REDACTED, 1=EMOJI, 2=FULL
        self.name_privacy = 0
        self.num_privacy = 0

        # Card mode: 0=Emotional, 1=Technical, 2=Quotes, 3=BatchStats, 4=MicroRAG, 5=EventLog, 6=TechSpecs
        self.card_mode = 0

        # Current file being displayed in middle-right
        self.current_display_idx = -1

        # Last completed file data
        self.last_result: dict = {}

        # Event log — chronological list of events during this run
        self.event_log: list = []

        # Batch stats — aggregated across all completed files
        self.batch_stats: dict = {}

        # Micro RAG — cross-file entity index
        self.micro_rag: dict = {}

        # Max parallel processes
        self.max_parallel = 3

        # Selected file index (for arrow key navigation)
        self.selected_file_idx = 0

        # Auto-start: if False, wait for Enter before processing
        self.auto_start = False

        # Processing started flag
        self.started = False

        # Watch mode: monitor folder for new files
        self.watch_mode = False
        self.watch_dir = ""

        # Second Brain export format (0=none, selected via [E])
        self.export_format = 0  # 0=none, cycles through formats

        # Output formats list
        self.export_formats = [
            "Wiki MD", "Obsidian", "CSV", "JSON", "HTML", "SQL",
            "OPML", "Excel", "WordPress", "Substack", "CapCut", "Notion"
        ]

        # Terminal dimensions
        self.term_rows = 40
        self.term_cols = 120

        # Overlay state: None, "options", "help"
        self.overlay = None
        # Forced model for all pending files ("" = per-file auto-select)
        self.model_override = ""

    def get_cli_flags(self):
        flags = []
        if not self.deception: flags.append("--no-deception")
        if not self.veracity: flags.append("--no-veracity")
        if not self.jefferson: flags.append("--no-jefferson")
        if not self.clinical: flags.append("--no-clinical")
        if not self.voice_dynamics: flags.append("--no-voice-dynamics")
        if not self.emotional: flags.append("--no-emotional")
        if self.omni: flags.append("--omni")
        else: flags.append("--no-omni")
        if not self.viewer: flags.append("--no-viewer")
        if self.diarise_local: flags.append("--diarise-local")
        flags.append("--no-copy-audio")
        return flags

    def name_privacy_label(self):
        return ["REDACTED", "EMOJI", "FULL"][self.name_privacy]

    def num_privacy_label(self):
        return ["REDACTED", "EMOJI", "FULL"][self.num_privacy]

    def card_mode_label(self):
        return ["Emotional", "Technical", "Quotes", "Batch Stats", "Micro RAG", "Event Log", "Tech Specs"][self.card_mode]


STATE = BatchState()

# ─── Capability checks ───────────────────────────────────────────────────────

_has_librosa = False
try:
    import librosa  # noqa: F401
    _has_librosa = True
except ImportError:
    pass

_has_ffmpeg = False
try:
    subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    _has_ffmpeg = True
except Exception:
    pass

# ─── Privacy Filtering ────────────────────────────────────────────────────────

def filter_name(name):
    """Filter a name based on current privacy level."""
    if STATE.name_privacy == 2:  # FULL
        return name
    elif STATE.name_privacy == 1:  # EMOJI
        return "🗣️"
    else:  # REDACTED
        return "Speaker_XX"

def filter_number(num_str):
    """Filter a number/figure based on current privacy level."""
    if STATE.num_privacy == 2:  # FULL
        return num_str
    elif STATE.num_privacy == 1:  # EMOJI
        return "🔢"
    else:  # REDACTED
        return "[NUM]"

def filter_text(text):
    """Filter a text string, replacing names and numbers."""
    result = text
    if STATE.name_privacy < 2:
        # Replace Speaker_NN patterns
        result = re.sub(r'Speaker_\d+', filter_name(""), result)
        # Replace capitalized names (rough heuristic)
        if STATE.name_privacy == 0:
            result = re.sub(r'\b[A-Z][a-z]{2,}\b', '[NAME]', result)
        elif STATE.name_privacy == 1:
            result = re.sub(r'\b[A-Z][a-z]{2,}\b', '🗣️', result)
    if STATE.num_privacy < 2:
        # Replace standalone numbers
        if STATE.num_privacy == 0:
            result = re.sub(r'\b\d+\b', '[NUM]', result)
        elif STATE.num_privacy == 1:
            result = re.sub(r'\b\d+\b', '🔢', result)
    return result

def sanitize_filename(filename):
    """Strip personal content from filename for display."""
    result = re.sub(r'.*Voice Memo - [\d-]+ [\d ]+ - ', '', filename)
    result = re.sub(r'—.*', '', result)
    result = re.sub(r'-.*', '', result)
    result = re.sub(r'[^A-Za-z0-9]', '_', result)
    result = re.sub(r'_+', '_', result)
    return result[:22] if len(result) > 5 else f"File_{hash(filename) % 10000:04d}"


# ─── Terminal Helpers ─────────────────────────────────────────────────────────

def get_terminal_size():
    try:
        size = os.get_terminal_size()
        return size.lines, size.columns
    except Exception:
        return 40, 120

def move_cursor(row, col=1):
    return f"\033[{row};{col}H"

def nonblocking_getchar():
    """Read a single key press without blocking. Returns None if no input.
    Handles arrow key escape sequences."""
    try:
        import select
        if select.select([sys.stdin], [], [], 0.0)[0]:
            ch = sys.stdin.read(1)
            # Check for escape sequence (arrow keys)
            if ch == '\x1b':
                # Try to read the rest of the sequence
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    ch2 = sys.stdin.read(1)
                    if ch2 == '[':
                        if select.select([sys.stdin], [], [], 0.05)[0]:
                            ch3 = sys.stdin.read(1)
                            return f'\x1b[{ch3}'
                return ch  # just escape key
            return ch
    except Exception:
        pass
    return None

def init_raw_terminal():
    """Set terminal to raw mode for non-blocking key input."""
    try:
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        return old_settings
    except Exception:
        return None

def restore_terminal(old_settings):
    """Restore terminal to original settings."""
    if old_settings:
        try:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        except Exception:
            pass

# ─── File Discovery ───────────────────────────────────────────────────────────

def scan_files(directory):
    """Scan directory for .m4a files and gather metadata."""
    files = []
    audio_dir = Path(directory)

    for f in sorted(audio_dir.glob("*.m4a")):
        dur = get_duration(f)
        size_mb = f.stat().st_size / 1048576
        tok = int(dur / 60 * 112)

        if dur < 300:
            model = "tiny"
        elif dur < 1800:
            model = "base"
        else:
            model = "base"

        safe = sanitize_filename(f.name)

        files.append({
            "path": str(f),
            "name": f.name,
            "stem": f.stem,
            "duration": dur,
            "size_mb": size_mb,
            "model": model,
            "safe_name": safe,
            "tokens": tok,
            "status": "pending",  # pending, running, done, failed
            "pid": None,
            "start_time": None,
            "end_time": None,
            "output_dir": str(audio_dir / (f.stem + "_subfile")),
        })

    return files

def get_duration(path):
    """Get audio duration in seconds using ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10
        )
        return int(float(r.stdout.strip())) if r.stdout.strip() else 0
    except Exception:
        return 0

# ─── Process Management ───────────────────────────────────────────────────────

def start_file(file_entry):
    """Start processing a file in a subprocess."""
    flags = STATE.get_cli_flags()
    model = file_entry["model"]

    cmd = [
        sys.executable,
        str(TRANSCRIPT_SCRIPT),
        file_entry["path"],
        "--model", model,
        "--output-dir", str(Path(file_entry["path"]).parent),
    ] + flags

    file_entry["status"] = "running"
    file_entry["start_time"] = time.time()

    log_event("start", f"Started: {file_entry['safe_name']} ({file_entry['duration']//60}min, model:{model})", file_entry["safe_name"])

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(SCRIPT_DIR),
    )
    file_entry["pid"] = proc.pid
    file_entry["proc"] = proc

def check_running():
    """Check status of running processes, collect results."""
    for f in STATE.files:
        if f["status"] == "running" and f.get("proc"):
            proc = f["proc"]
            ret = proc.poll()
            if ret is not None:
                f["end_time"] = time.time()
                f["proc"] = None
                if ret == 0:
                    f["status"] = "done"
                    STATE.completed += 1
                    load_result_data(f)
                    r = f.get("result", {})
                    log_event("done", f"Done: {f['safe_name']} — {r.get('deception_count',0)} dec, {r.get('veracity_count',0)} ver, {r.get('freeze_count',0)} freezes", f["safe_name"])
                    update_batch_stats()
                    update_micro_rag()
                else:
                    f["status"] = "failed"
                    STATE.failed += 1
                    log_event("fail", f"Failed: {f['safe_name']} (exit {ret})", f["safe_name"])
                STATE.running -= 1
                STATE.current_display_idx = STATE.files.index(f)

def load_result_data(file_entry):
    """Load analysis data from completed file's output."""
    out_dir = Path(file_entry["output_dir"])
    result = {"file": file_entry["safe_name"], "duration": file_entry["duration"]}

    # Load analysis.json
    analysis_path = out_dir / "analysis.json"
    if analysis_path.exists():
        try:
            with open(analysis_path) as af:
                data = json.load(af)
                result["deception_count"] = len(data.get("deception_indicators", []))
                result["veracity_count"] = len(data.get("veracity_indicators", []))
                result["clinical_count"] = len(data.get("clinical_markers", []))
                result["voice_dynamics_count"] = len(data.get("voice_dynamics", []))
                result["jefferson_summary"] = data.get("jefferson_summary", {})
                result["summary"] = data.get("summary", {})
                result["cost"] = data.get("cost_estimate", {})
        except Exception:
            pass

    # Load emotions.json for quotes and emotion data
    emo_path = out_dir / "emotions.json"
    if emo_path.exists():
        try:
            with open(emo_path) as ef:
                emo = json.load(ef)
                segments = emo.get("segments", [])
                result["segment_count"] = len(segments)
                result["freeze_events"] = emo.get("freeze_events", [])
                result["freeze_count"] = len(result["freeze_events"])

                # Emotion distribution
                affects = {}
                for seg in segments:
                    label = seg.get("affect_label", "Neutral")
                    affects[label] = affects.get(label, 0) + 1
                result["emotion_dist"] = affects

                # Choice quotes — segments with high intensity or notable markers
                quotes = []
                for seg in segments:
                    intensity = seg.get("intensity", 5)
                    if intensity >= 7 or seg.get("deception_markers") or seg.get("freeze_events"):
                        text = seg.get("text_preview", "")
                        if text and len(text) > 10:
                            quotes.append({
                                "time": seg.get("timestamp", ""),
                                "emoji": seg.get("emoji", ""),
                                "affect": seg.get("affect_label", ""),
                                "intensity": intensity,
                                "text": text,
                            })
                result["quotes"] = quotes[:5]

                # Names/people found
                result["speakers"] = list(set(
                    seg.get("speaker", "") for seg in segments if seg.get("speaker")
                ))
        except Exception:
            pass

    # Load noteworthy.json
    nw_path = out_dir / "noteworthy.json"
    if nw_path.exists():
        try:
            with open(nw_path) as nf:
                nw = json.load(nf)
                result["noteworthy"] = nw.get("items", [])[:10]
                result["noteworthy_count"] = len(nw.get("items", []))
        except Exception:
            pass

    # Load things.json for people
    things_path = out_dir / "things.json"
    if things_path.exists():
        try:
            with open(things_path) as tf:
                things = json.load(tf)
                result["people"] = things.get("people", [])[:8]
                result["places"] = things.get("places", [])[:5]
        except Exception:
            pass

    # Load meta.json
    meta_path = out_dir / "meta.json"
    if meta_path.exists():
        try:
            with open(meta_path) as mf:
                meta = json.load(mf)
                result["model"] = meta.get("whisper_model", "?")
                result["word_count"] = meta.get("word_count", 0)
                result["hashtags"] = meta.get("hashtags", [])
        except Exception:
            pass

    file_entry["result"] = result
    STATE.last_result = result

# ─── Dashboard Rendering ──────────────────────────────────────────────────────

# ─── Event Log ────────────────────────────────────────────────────────────────

def log_event(event_type, message, file_name=""):
    """Add an event to the event log."""
    STATE.event_log.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "type": event_type,
        "message": message,
        "file": file_name,
    })
    # Keep last 100 events
    if len(STATE.event_log) > 100:
        STATE.event_log = STATE.event_log[-100:]

# ─── Batch Stats Aggregation ──────────────────────────────────────────────────

def update_batch_stats():
    """Aggregate statistics across all completed files."""
    stats = {
        "files_done": 0,
        "files_failed": 0,
        "total_segments": 0,
        "total_words": 0,
        "total_tokens": 0,
        "total_freezes": 0,
        "total_deception": 0,
        "total_veracity": 0,
        "total_clinical": 0,
        "total_noteworthy": 0,
        "emotion_dist": {},
        "jefferson_dist": {},
        "speakers_seen": set(),
        "people_seen": {},
        "places_seen": {},
    }

    for f in STATE.files:
        if f["status"] not in ("done", "failed"):
            continue
        if f["status"] == "done":
            stats["files_done"] += 1
        else:
            stats["files_failed"] += 1

        r = f.get("result", {})
        stats["total_segments"] += r.get("segment_count", 0)
        stats["total_words"] += r.get("word_count", 0)
        stats["total_tokens"] += r.get("duration", 0) // 60 * 112
        stats["total_freezes"] += r.get("freeze_count", 0)
        stats["total_deception"] += r.get("deception_count", 0)
        stats["total_veracity"] += r.get("veracity_count", 0)
        stats["total_clinical"] += r.get("clinical_count", 0)
        stats["total_noteworthy"] += r.get("noteworthy_count", 0)

        for label, count in r.get("emotion_dist", {}).items():
            stats["emotion_dist"][label] = stats["emotion_dist"].get(label, 0) + count

        for sym, info in r.get("jefferson_summary", {}).items():
            stats["jefferson_dist"][sym] = stats["jefferson_dist"].get(sym, 0) + info.get("count", 0)

        for spk in r.get("speakers", []):
            stats["speakers_seen"].add(spk)

        for p in r.get("people", []):
            pname = p.get("name", "")
            if pname:
                stats["people_seen"][pname] = stats["people_seen"].get(pname, 0) + p.get("occurrences", 1)

        for pl in r.get("places", []):
            ploc = pl.get("place", "")
            if ploc:
                stats["places_seen"][ploc] = stats["places_seen"].get(ploc, 0) + pl.get("occurrences", 1)

    STATE.batch_stats = stats

# ─── Micro RAG (cross-file entity index) ─────────────────────────────────────

def update_micro_rag():
    """Build a cross-file entity index showing where people/places/topics appear across files."""
    rag = {"people": {}, "places": {}, "quotes": [], "topics": {}}

    for f in STATE.files:
        if f["status"] != "done":
            continue
        r = f.get("result", {})
        safe = f["safe_name"]

        # People cross-reference
        for p in r.get("people", []):
            pname = p.get("name", "")
            if pname:
                if pname not in rag["people"]:
                    rag["people"][pname] = {"files": [], "total_occurrences": 0}
                rag["people"][pname]["files"].append(safe)
                rag["people"][pname]["total_occurrences"] += p.get("occurrences", 1)

        # Places cross-reference
        for pl in r.get("places", []):
            ploc = pl.get("place", "")
            if ploc:
                if ploc not in rag["places"]:
                    rag["places"][ploc] = {"files": [], "total_occurrences": 0}
                rag["places"][ploc]["files"].append(safe)
                rag["places"][ploc]["total_occurrences"] += pl.get("occurrences", 1)

        # Quotes cross-reference (high-intensity segments)
        for q in r.get("quotes", []):
            rag["quotes"].append({
                "file": safe,
                "time": q.get("time", ""),
                "emoji": q.get("emoji", ""),
                "affect": q.get("affect", ""),
                "intensity": q.get("intensity", 5),
                "text": q.get("text", ""),
            })

        # Topics from hashtags
        for tag in r.get("hashtags", []):
            tag = tag.lstrip("#")
            if tag:
                if tag not in rag["topics"]:
                    rag["topics"][tag] = []
                rag["topics"][tag].append(safe)

    STATE.micro_rag = rag


def render_dashboard():
    """Render the complete fixed dashboard."""
    STATE.term_rows, STATE.term_cols = get_terminal_size()
    rows = STATE.term_rows
    cols = STATE.term_cols

    # Layout zones:
    # Top:    rows 1-7   (title + config + progress)
    # Middle: rows 8-?   (left: queue, right: cards)
    # Bottom: rows -3 to end (menu bar)
    bottom_start = rows - 4
    middle_start = 8
    middle_end = bottom_start - 1
    middle_height = middle_end - middle_start + 1
    left_width = min(50, cols // 2)
    right_start_col = left_width + 2

    lines = []
    lines.append(HOME + CLEAR)

    # ── TOP: Title bar ──
    lines.append(move_cursor(1, 1))
    title = f"  🎧 EMOTION AUDIO ANALYSER v3.1 — BATCH DASHBOARD"
    lines.append(f"{P}{BD}{title}{NC}")
    lines.append(move_cursor(2, 1))
    lines.append(f"{P}{'─' * (cols - 1)}{NC}")

    # ── TOP: Config line ──
    config_parts = []
    config_parts.append(f"🧠Deception: {'✅' if STATE.deception else '❌'}")
    config_parts.append(f"✅Veracity: {'✅' if STATE.veracity else '❌'}")
    config_parts.append(f"📝Jefferson: {'✅' if STATE.jefferson else '❌'}")
    config_parts.append(f"🏥Clinical: {'✅' if STATE.clinical else '❌'}")
    config_parts.append(f"🎤Voice: {'✅' if STATE.voice_dynamics else '❌'}")
    config_parts.append(f"😊Emotional: {'✅' if STATE.emotional else '❌'}")
    config_parts.append(f"📋Omni: {'✅' if STATE.omni else '❌'}")
    config_parts.append(f"🔒Names: {STATE.name_privacy_label()}")
    config_parts.append(f"🔒Nums: {STATE.num_privacy_label()}")
    config_parts.append(f"📊Cards: {STATE.card_mode_label()}")

    # Split config across two lines if too long
    config_line = "  ".join(config_parts)
    if len(config_line) > cols - 4:
        line1 = "  ".join(config_parts[:5])
        line2 = "  ".join(config_parts[5:])
        lines.append(move_cursor(3, 1))
        lines.append(f"  {D}{line1}{NC}")
        lines.append(move_cursor(4, 1))
        lines.append(f"  {D}{line2}{NC}")
        prog_row = 5
    else:
        lines.append(move_cursor(3, 1))
        lines.append(f"  {D}{config_line}{NC}")
        prog_row = 4

    # ── TOP: Progress bar ──
    total = len(STATE.files)
    done_total = STATE.completed + STATE.failed
    pct = (done_total * 100 // total) if total > 0 else 0
    elapsed = int(time.time() - STATE.start_time)
    el_m, el_s = divmod(elapsed, 60)

    bar_width = min(40, cols - 60)
    filled = bar_width * pct // 100 if pct > 0 else 0
    bar = "█" * filled + "░" * (bar_width - filled)

    lines.append(move_cursor(prog_row, 1))
    lines.append(f"  {BD}Progress:{NC} {G}{bar}{NC} {pct}%  │  ✅{STATE.completed} ❌{STATE.failed} ⏳{STATE.running} / {total}  │  ⏱ {el_m}m{el_s:02d}s  │  🔢 ~{STATE.total_tokens} tok")

    lines.append(move_cursor(prog_row + 1, 1))
    lines.append(f"{D}{'─' * (cols - 1)}{NC}")

    # ── MIDDLE-LEFT: Queue with progress bars ──
    lines.append(move_cursor(middle_start, 1))
    if not STATE.started:
        lines.append(f"  {BD}📋 QUEUE{NC}  {Y}⏸ Press [Enter] to start{NC}")
    else:
        lines.append(f"  {BD}📋 QUEUE{NC}")

    queue_row = middle_start + 1
    visible_queue = min(middle_height - 2, len(STATE.files))

    for i, f in enumerate(STATE.files[:visible_queue]):
        row = queue_row + i
        if row >= middle_end:
            break

        status_icon = {"pending": "⬚", "running": "▶", "done": "✅", "failed": "❌"}.get(f["status"], "?")
        dur_min = f["duration"] // 60
        safe = f["safe_name"]
        is_selected = (i == STATE.selected_file_idx)

        if f["status"] == "running":
            est_time = max(1, f["duration"] * 0.3)
            elapsed_f = time.time() - f["start_time"]
            file_pct = min(99, int(elapsed_f / est_time * 100))
            bar_w = 15
            filled_f = bar_w * file_pct // 100
            fbar = "█" * filled_f + "░" * (bar_w - filled_f)
            color = Y
            prefix = "▶" if is_selected else " "
            lines.append(move_cursor(row, 1))
            lines.append(f" {prefix} {color}{status_icon}{NC} {safe:<16} {dur_min:>4}min {color}{fbar}{NC} {file_pct:>2}%")
        elif f["status"] == "done":
            color = G
            prefix = "▶" if is_selected else " "
            lines.append(move_cursor(row, 1))
            lines.append(f" {prefix} {color}{status_icon}{NC} {safe:<16} {dur_min:>4}min {color}{'✓' * 15}{NC} 100%")
        elif f["status"] == "failed":
            color = R
            prefix = "▶" if is_selected else " "
            lines.append(move_cursor(row, 1))
            lines.append(f" {prefix} {color}{status_icon}{NC} {safe:<16} {dur_min:>4}min {color}{'✗' * 15}{NC} ERR")
        else:
            color = D
            prefix = "▶" if is_selected else " "
            lines.append(move_cursor(row, 1))
            lines.append(f" {prefix} {color}{status_icon}{NC} {safe:<16} {dur_min:>4}min {color}{'·' * 15}{NC} ---")

    # ── MIDDLE-RIGHT: Detail cards ──
    lines.append(move_cursor(middle_start, right_start_col))
    lines.append(f"{BD}📊 FILE DETAIL{NC} {'[' + STATE.card_mode_label() + ']':>12}")

    card_row = middle_start + 1

    # Determine which file to show
    display_file = None
    if STATE.current_display_idx >= 0 and STATE.current_display_idx < len(STATE.files):
        display_file = STATE.files[STATE.current_display_idx]
    else:
        # Show the most recently started/finished
        for f in reversed(STATE.files):
            if f["status"] in ("done", "failed", "running"):
                display_file = f
                break

    if display_file and display_file.get("result"):
        r = display_file["result"]
        card_width = cols - right_start_col - 1

        if STATE.card_mode == 0:
            # ── Emotional mode ──
            row = card_row

            # Choice quotes
            lines.append(move_cursor(row, right_start_col))
            lines.append(f"{C}💬 Choice Quotes{NC}")
            row += 1
            quotes = r.get("quotes", [])
            if quotes:
                for q in quotes[:3]:
                    if row >= middle_end: break
                    text = filter_text(q["text"][:card_width - 12])
                    lines.append(move_cursor(row, right_start_col))
                    lines.append(f"  {q['emoji']} {q['time']} {D}{text}{NC}")
                    row += 1
            else:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {D}(none){NC}")
                row += 1

            row += 1

            # Emotional markers
            lines.append(move_cursor(row, right_start_col))
            lines.append(f"{C}😊 Emotional Markers{NC}")
            row += 1
            emo_dist = r.get("emotion_dist", {})
            if emo_dist:
                for label, count in sorted(emo_dist.items(), key=lambda x: -x[1])[:5]:
                    if row >= middle_end: break
                    pct_str = f"{count}"
                    lines.append(move_cursor(row, right_start_col))
                    lines.append(f"  {label:<14} {pct_str:>3}")
                    row += 1
            else:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {D}(none){NC}")
                row += 1

            row += 1

            # Names/people
            if row < middle_end:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"{C}👥 People Found{NC}")
                row += 1
                people = r.get("people", [])
                if people:
                    for p in people[:4]:
                        if row >= middle_end: break
                        pname = filter_name(p.get("name", ""))
                        cert = p.get("certainty", 0)
                        lines.append(move_cursor(row, right_start_col))
                        lines.append(f"  {pname:<12} [C:{cert:.2f}]")
                        row += 1
                else:
                    lines.append(move_cursor(row, right_start_col))
                    lines.append(f"  {D}(none){NC}")
                    row += 1

            row += 1

            # Noteworthy
            if row < middle_end:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"{C}🔍 Noteworthy ({r.get('noteworthy_count', 0)}){NC}")
                row += 1
                nw = r.get("noteworthy", [])
                if nw:
                    for n in nw[:3]:
                        if row >= middle_end: break
                        note = filter_text(n.get("note", "")[:card_width - 4])
                        lines.append(move_cursor(row, right_start_col))
                        lines.append(f"  {D}{note}{NC}")
                        row += 1
                else:
                    lines.append(move_cursor(row, right_start_col))
                    lines.append(f"  {D}(none){NC}")
                    row += 1

        elif STATE.card_mode == 1:
            # ── Technical mode ──
            row = card_row

            lines.append(move_cursor(row, right_start_col))
            lines.append(f"{C}⚙️ Technical Stats{NC}")
            row += 1

            tech_items = [
                ("Model", r.get("model", "?")),
                ("Duration", f"{r.get('duration', 0) // 60}min"),
                ("Segments", str(r.get("segment_count", "?"))),
                ("Words", str(r.get("word_count", "?"))),
                ("Tokens", f"~{r.get('duration', 0) // 60 * 112}"),
                ("Freeze events", str(r.get("freeze_count", 0))),
                ("Noteworthy", str(r.get("noteworthy_count", 0))),
            ]
            for label, val in tech_items:
                if row >= middle_end: break
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {label:<16} {W}{val}{NC}")
                row += 1

            row += 1

            # Indicator counts
            if row < middle_end:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"{C}🧠 Indicators{NC}")
                row += 1

            indicators = [
                ("Deception", r.get("deception_count", 0), R),
                ("Veracity", r.get("veracity_count", 0), G),
                ("Clinical", r.get("clinical_count", 0), Y),
                ("Voice dyn.", r.get("voice_dynamics_count", 0), C),
            ]
            for label, count, color in indicators:
                if row >= middle_end: break
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {label:<16} {color}{count}{NC}")
                row += 1

            row += 1

            # Jefferson markers
            if row < middle_end:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"{C}📝 Jefferson Markers{NC}")
                row += 1
                jf = r.get("jefferson_summary", {})
                if jf:
                    # Sort by count descending
                    for sym, info in sorted(jf.items(), key=lambda x: -x[1].get("count", 0))[:5]:
                        if row >= middle_end: break
                        count = info.get("count", 0)
                        phenomenon = info.get("phenomenon", "")[:card_width - 20]
                        lines.append(move_cursor(row, right_start_col))
                        lines.append(f"  {sym:<10} {count:>3}x {D}{phenomenon}{NC}")
                        row += 1
                else:
                    lines.append(move_cursor(row, right_start_col))
                    lines.append(f"  {D}(none){NC}")
                    row += 1

        elif STATE.card_mode == 2:
            # ── Quotes mode ── key quotes/facts/key points
            row = card_row
            lines.append(move_cursor(row, right_start_col))
            lines.append(f"{C}📌 Key Quotes & Facts{NC}")
            row += 1

            # Pull from noteworthy items — filter for interesting types
            nw = r.get("noteworthy", [])
            quotes_shown = 0
            for item in nw:
                if row >= middle_end: break
                if quotes_shown >= 8: break
                itype = item.get("type", "")
                note = item.get("note", "")
                # Skip generic uncertain entities
                if "uncertain_entity" in itype:
                    continue
                text = filter_text(note[:card_width - 6])
                icon = "🚨" if "freeze" in itype else "⚠️" if "deception" in itype else "✓" if "veracity" in itype else "🏥" if "clinical" in itype else "🔍"
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {icon} {D}{text}{NC}")
                row += 1
                quotes_shown += 1

            if quotes_shown == 0:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {D}(no key quotes yet){NC}")
                row += 1

            # Also show high-intensity quotes
            row += 1
            if row < middle_end:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"{C}💬 High-Intensity Moments{NC}")
                row += 1
                for q in r.get("quotes", [])[:4]:
                    if row >= middle_end: break
                    text = filter_text(q["text"][:card_width - 12])
                    lines.append(move_cursor(row, right_start_col))
                    lines.append(f"  {q['emoji']} [{q['intensity']}/10] {D}{text}{NC}")
                    row += 1

        elif STATE.card_mode == 3:
            # ── Batch Stats mode ── aggregate across all completed files
            row = card_row
            lines.append(move_cursor(row, right_start_col))
            lines.append(f"{C}📊 Batch Statistics ({STATE.batch_stats.get('files_done', 0)} files){NC}")
            row += 1

            bs = STATE.batch_stats
            batch_items = [
                ("Files completed", str(bs.get("files_done", 0))),
                ("Files failed", str(bs.get("files_failed", 0))),
                ("Total segments", str(bs.get("total_segments", 0))),
                ("Total words", str(bs.get("total_words", 0))),
                ("Total tokens", f"~{bs.get('total_tokens', 0)}"),
                ("Freeze events", str(bs.get("total_freezes", 0))),
                ("Deception markers", str(bs.get("total_deception", 0))),
                ("Veracity markers", str(bs.get("total_veracity", 0))),
                ("Clinical markers", str(bs.get("total_clinical", 0))),
                ("Noteworthy items", str(bs.get("total_noteworthy", 0))),
            ]
            for label, val in batch_items:
                if row >= middle_end: break
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {label:<18} {W}{val}{NC}")
                row += 1

            row += 1
            # Top emotions across batch
            if row < middle_end:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"{C}🎭 Top Emotions (batch){NC}")
                row += 1
                emo = bs.get("emotion_dist", {})
                for label, count in sorted(emo.items(), key=lambda x: -x[1])[:4]:
                    if row >= middle_end: break
                    lines.append(move_cursor(row, right_start_col))
                    lines.append(f"  {label:<14} {count:>4}")
                    row += 1

            row += 1
            # Top people across batch
            if row < middle_end:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"{C}👥 People (batch){NC}")
                row += 1
                people = bs.get("people_seen", {})
                for pname, count in sorted(people.items(), key=lambda x: -x[1])[:4]:
                    if row >= middle_end: break
                    filtered = filter_name(pname)
                    lines.append(move_cursor(row, right_start_col))
                    lines.append(f"  {filtered:<12} {count:>3}x")
                    row += 1

        elif STATE.card_mode == 4:
            # ── Micro RAG mode ── cross-file entity index
            row = card_row
            lines.append(move_cursor(row, right_start_col))
            lines.append(f"{C}🔎 Micro RAG — Cross-File Index{NC}")
            row += 1

            rag = STATE.micro_rag

            # People appearing in multiple files
            if row < middle_end:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"{C}👥 People Across Files{NC}")
                row += 1
            cross_people = [(name, info) for name, info in rag.get("people", {}).items() if len(info["files"]) > 1]
            cross_people.sort(key=lambda x: -x[1]["total_occurrences"])
            for pname, info in cross_people[:4]:
                if row >= middle_end: break
                filtered = filter_name(pname)
                file_count = len(info["files"])
                occ = info["total_occurrences"]
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {filtered:<10} {file_count} files  {occ}x")
                row += 1
            if not cross_people:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {D}(no cross-file matches yet){NC}")
                row += 1

            row += 1
            # Places appearing in multiple files
            if row < middle_end:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"{C}📍 Places Across Files{NC}")
                row += 1
            cross_places = [(name, info) for name, info in rag.get("places", {}).items() if len(info["files"]) > 1]
            cross_places.sort(key=lambda x: -x[1]["total_occurrences"])
            for ploc, info in cross_places[:4]:
                if row >= middle_end: break
                file_count = len(info["files"])
                occ = info["total_occurrences"]
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {ploc:<14} {file_count} files  {occ}x")
                row += 1
            if not cross_places:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {D}(no cross-file places yet){NC}")
                row += 1

            row += 1
            # Topics across files
            if row < middle_end:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"{C}🏷 Topics Across Files{NC}")
                row += 1
            cross_topics = [(tag, files) for tag, files in rag.get("topics", {}).items() if len(files) > 1]
            cross_topics.sort(key=lambda x: -len(x[1]))
            for tag, files in cross_topics[:4]:
                if row >= middle_end: break
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  #{tag:<14} {len(files)} files")
                row += 1
            if not cross_topics:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {D}(no cross-file topics yet){NC}")
                row += 1

        elif STATE.card_mode == 5:
            # ── Event Log mode ── chronological system log
            row = card_row
            lines.append(move_cursor(row, right_start_col))
            lines.append(f"{C}📋 Event Log{NC}")
            row += 1

            events = STATE.event_log[-(middle_end - card_row - 1):]
            if events:
                for ev in events:
                    if row >= middle_end: break
                    icon = {"start": "▶", "done": "✅", "fail": "❌", "info": "ℹ️", "warn": "⚠️"}.get(ev["type"], "•")
                    msg = filter_text(ev["message"][:card_width - 14])
                    lines.append(move_cursor(row, right_start_col))
                    lines.append(f"  {D}{ev['time']}{NC} {icon} {msg}")
                    row += 1
            else:
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {D}(no events yet){NC}")
                row += 1

        elif STATE.card_mode == 6:
            # ── Tech Specs mode ── system info
            row = card_row
            lines.append(move_cursor(row, right_start_col))
            lines.append(f"{C}⚙️ System Tech Specs{NC}")
            row += 1

            # Gather system info
            py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            whisper_models = []
            try:
                import whisper
                for m in ["tiny", "base", "small", "medium", "large"]:
                    try:
                        p = SCRIPT_DIR / f"~/.cache/whisper/{m}.pt"
                        whisper_models.append(f"{m}✓" if p.exists() else m)
                    except Exception:
                        whisper_models.append(m)
            except ImportError:
                whisper_models = ["(not installed)"]

            librosa_ok = "✅" if _has_librosa else "❌"

            # Disk space
            try:
                stat = os.statvfs(str(SCRIPT_DIR))
                disk_gb = (stat.f_bavail * stat.f_frsize) / 1073741824
                disk_str = f"{disk_gb:.1f} GB free"
            except Exception:
                disk_str = "?"

            specs = [
                ("Python", py_ver),
                ("Whisper models", ", ".join(whisper_models[:4])),
                ("librosa", librosa_ok),
                ("ffmpeg", "✅" if _has_ffmpeg else "❌"),
                ("Disk space", disk_str),
                ("Script dir", str(SCRIPT_DIR)[:card_width - 20]),
                ("Batch files", str(len(STATE.files))),
                ("Parallel max", str(STATE.max_parallel)),
                ("Provider", "Local (on-device)"),
                ("LLM engine", "OpenAI Whisper (local)"),
                ("Cost", "$0.00"),
            ]
            for label, val in specs:
                if row >= middle_end: break
                lines.append(move_cursor(row, right_start_col))
                lines.append(f"  {label:<16} {W}{val}{NC}")
                row += 1

    elif display_file and display_file["status"] == "running":
        lines.append(move_cursor(card_row, right_start_col))
        lines.append(f"  {Y}⏳ Processing...{NC}")
        lines.append(move_cursor(card_row + 1, right_start_col))
        lines.append(f"  {D}{display_file['safe_name']}{NC}")
        lines.append(move_cursor(card_row + 2, right_start_col))
        lines.append(f"  {D}model: {display_file['model']}  dur: {display_file['duration']//60}min{NC}")
    else:
        lines.append(move_cursor(card_row, right_start_col))
        lines.append(f"  {D}Waiting for first file...{NC}")

    # ── BOTTOM: Menu bar ──
    lines.append(move_cursor(bottom_start, 1))
    lines.append(f"{D}{'─' * (cols - 1)}{NC}")

    # Menu bar — three rows
    menu1 = (
        f"  {BD}[N]{NC} Names:{STATE.name_privacy_label()}  "
        f"{BD}[P]{NC} Nums:{STATE.num_privacy_label()}  "
        f"{BD}[F]{NC} Card:{STATE.card_mode_label()}  "
        f"{BD}[D]{NC} Dec:{'✅' if STATE.deception else '❌'}  "
        f"{BD}[V]{NC} Ver:{'✅' if STATE.veracity else '❌'}  "
        f"{BD}[J]{NC} Jef:{'✅' if STATE.jefferson else '❌'}  "
        f"{BD}[C]{NC} Clin:{'✅' if STATE.clinical else '❌'}  "
        f"{BD}[G]{NC} Voice:{'✅' if STATE.voice_dynamics else '❌'}  "
        f"{BD}[A]{NC} Emo:{'✅' if STATE.emotional else '❌'}"
    )
    export_label = STATE.export_formats[STATE.export_format - 1] if STATE.export_format > 0 else "OFF"
    watch_label = "ON" if STATE.watch_mode else "OFF"
    model_label = STATE.model_override if STATE.model_override else "auto"
    menu2 = (
        f"  {BD}[O]{NC} Options  "
        f"{BD}[H]{NC} Help  "
        f"{BD}[M]{NC} Model:{model_label}  "
        f"{BD}[+/-]{NC} Par:{STATE.max_parallel}  "
        f"{BD}[I]{NC} Omni:{'✅' if STATE.omni else '❌'}  "
        f"{BD}[B]{NC} Viewer:{'✅' if STATE.viewer else '❌'}  "
        f"{BD}[↑↓]{NC} Nav  "
        f"{BD}[1-7]{NC} Card  "
        f"{BD}[⏎]{NC} Start  "
        f"{BD}[E]{NC} Exp:{export_label}  "
        f"{BD}[X]{NC} ExNow  "
        f"{BD}[R]{NC} Requeue  "
        f"{BD}[W]{NC} Watch:{watch_label}  "
        f"{BD}[Q]{NC} Quit"
    )

    lines.append(move_cursor(bottom_start + 1, 1))
    lines.append(CLEAR_LINE + menu1)
    lines.append(move_cursor(bottom_start + 2, 1))
    lines.append(CLEAR_LINE + menu2)

    # Flush main dashboard
    sys.stdout.write("".join(lines))
    sys.stdout.flush()

    # Render overlay on top if active
    if STATE.overlay == "options":
        render_overlay_options()
    elif STATE.overlay == "help":
        render_overlay_help()

# ─── Overlay Renderers ───────────────────────────────────────────────────────

def render_overlay_options():
    """Render a full-screen options overlay replacing the middle section."""
    rows = STATE.term_rows
    cols = STATE.term_cols
    bottom_start = rows - 4
    middle_start = 8
    middle_end = bottom_start - 1

    out = []

    # Clear middle section
    for r in range(middle_start, middle_end + 1):
        out.append(move_cursor(r, 1))
        out.append(CLEAR_LINE)

    # Header
    out.append(move_cursor(middle_start, 1))
    out.append(f"  {BD}{P}⚙️  OPTIONS & PARAMETERS{NC}  {D}[O] close · changes apply immediately{NC}")
    out.append(move_cursor(middle_start + 1, 1))
    out.append(f"{P}{'─' * (cols - 1)}{NC}")

    half = max(cols // 2, 42)

    def sect(row, col, label):
        out.append(move_cursor(row, col))
        out.append(f"  {BD}{C}{label}{NC}")

    def opt(row, col, key, label, value, color=W):
        out.append(move_cursor(row, col))
        out.append(f"  {BD}[{key}]{NC} {label:<24} {color}{value}{NC}")

    r = middle_start + 2

    # LEFT COLUMN
    sect(r, 1, "🧠 Analysis Features")
    r += 1
    opt(r, 1, "D", "Deception detection", "✅ ON" if STATE.deception else "❌ OFF", G if STATE.deception else R)
    r += 1
    opt(r, 1, "V", "Veracity detection",  "✅ ON" if STATE.veracity else "❌ OFF", G if STATE.veracity else R)
    r += 1
    opt(r, 1, "J", "Jefferson notation",  "✅ ON" if STATE.jefferson else "❌ OFF", G if STATE.jefferson else R)
    r += 1
    opt(r, 1, "C", "Clinical markers",    "✅ ON" if STATE.clinical else "❌ OFF", G if STATE.clinical else R)
    r += 1
    opt(r, 1, "G", "Voice dynamics",      "✅ ON" if STATE.voice_dynamics else "❌ OFF", G if STATE.voice_dynamics else R)
    r += 1
    opt(r, 1, "A", "Emotional analysis",  "✅ ON" if STATE.emotional else "❌ OFF", G if STATE.emotional else R)
    r += 2
    sect(r, 1, "📤 Export / Output")
    r += 1
    opt(r, 1, "I", "Omni output (.md)",   "✅ ON" if STATE.omni else "❌ OFF", G if STATE.omni else R)
    r += 1
    opt(r, 1, "B", "HTML Viewer output",  "✅ ON" if STATE.viewer else "❌ OFF", G if STATE.viewer else R)
    r += 1
    opt(r, 1, "K", "Diarise local",       "✅ ON" if STATE.diarise_local else "❌ OFF", G if STATE.diarise_local else R)
    r += 1
    export_label = STATE.export_formats[STATE.export_format - 1] if STATE.export_format > 0 else "OFF"
    opt(r, 1, "E", "Second Brain format", export_label, Y)
    r += 1
    opt(r, 1, "X", "Export now",          f"({export_label})", D)

    # RIGHT COLUMN
    r2 = middle_start + 2
    sect(r2, half, "⚙️ Processing Parameters")
    r2 += 1
    model_display = STATE.model_override if STATE.model_override else "auto (per duration)"
    opt(r2, half, "M", "Whisper model (cycle)", model_display, Y)
    r2 += 1
    opt(r2, half, "+", "Increase parallel",  f"{STATE.max_parallel} → {min(8, STATE.max_parallel + 1)}", Y)
    r2 += 1
    opt(r2, half, "-", "Decrease parallel",  f"{STATE.max_parallel} → {max(1, STATE.max_parallel - 1)}", Y)
    r2 += 2
    sect(r2, half, "🔒 Privacy Levels")
    r2 += 1
    opt(r2, half, "N", "Names (cycle)",   STATE.name_privacy_label(), Y)
    r2 += 1
    opt(r2, half, "P", "Numbers (cycle)", STATE.num_privacy_label(), Y)
    r2 += 2
    sect(r2, half, "📂 Queue & Navigation")
    r2 += 1
    opt(r2, half, "↑↓", "Select file",      f"{STATE.selected_file_idx + 1}/{max(1,len(STATE.files))}", Y)
    r2 += 1
    opt(r2, half, "1–7", "Jump to card mode", STATE.card_mode_label(), Y)
    r2 += 1
    opt(r2, half, "R",   "Requeue failed",   f"{STATE.failed} failed file(s)", Y if STATE.failed else D)
    r2 += 1
    opt(r2, half, "W",   "Watch mode",       "ON" if STATE.watch_mode else "OFF", G if STATE.watch_mode else D)
    r2 += 2
    sect(r2, half, "ℹ️ Indicator Explanations")
    r2 += 1
    out.append(move_cursor(r2, half))
    out.append(f"  {D}<dec>  false-start/correction/stall/evade/mem{NC}")
    r2 += 1
    out.append(move_cursor(r2, half))
    out.append(f"  {D}<ver>  sensory-recall/temporal/context/complex{NC}")
    r2 += 1
    out.append(move_cursor(r2, half))
    out.append(f"  {D}<clin> PTSD-frag/somatic/ADHD-maze/ASD-pause{NC}")
    r2 += 1
    out.append(move_cursor(r2, half))
    out.append(f"  {D}Certainty 0.00–1.00 · <0.70 = manual verify{NC}")

    sys.stdout.write("".join(out))
    sys.stdout.flush()


def render_overlay_help():
    """Render a help screen overlay listing all keyboard shortcuts."""
    rows = STATE.term_rows
    cols = STATE.term_cols
    bottom_start = rows - 4
    middle_start = 8
    middle_end = bottom_start - 1

    out = []
    for r in range(middle_start, middle_end + 1):
        out.append(move_cursor(r, 1))
        out.append(CLEAR_LINE)

    out.append(move_cursor(middle_start, 1))
    out.append(f"  {BD}{Y}⌨️  KEYBOARD SHORTCUTS{NC}  {D}[H] close{NC}")
    out.append(move_cursor(middle_start + 1, 1))
    out.append(f"{Y}{'─' * (cols - 1)}{NC}")

    half = max(cols // 2, 42)

    shortcuts_left = [
        ("SECTION", "Analysis Toggles"),
        ("D", "Deception detection ON/OFF"),
        ("V", "Veracity detection ON/OFF"),
        ("J", "Jefferson notation ON/OFF"),
        ("C", "Clinical markers ON/OFF"),
        ("G", "Voice dynamics ON/OFF"),
        ("A", "Emotional analysis ON/OFF"),
        ("I", "Omni output (.md) ON/OFF"),
        ("B", "HTML Viewer output ON/OFF"),
        ("K", "Diarise-local ON/OFF"),
        ("", ""),
        ("SECTION", "Privacy & Display"),
        ("N", "Names: REDACTED → EMOJI → FULL"),
        ("P", "Numbers: REDACTED → EMOJI → FULL"),
        ("F", "Cycle card mode (7 modes)"),
        ("1–7", "Jump directly to card mode 1–7"),
        ("", ""),
        ("SECTION", "Navigation"),
        ("↑ / ↓", "Select file in queue"),
        ("← / →", "Navigate files (same as ↑↓)"),
        ("⏎ Enter", "Start batch processing"),
    ]

    shortcuts_right = [
        ("SECTION", "Card Modes (1–7)"),
        ("1", "Emotional: quotes, emotions, people"),
        ("2", "Technical: model, segments, tokens"),
        ("3", "Quotes: key facts & high-intensity"),
        ("4", "Batch Stats: aggregate all files"),
        ("5", "Micro RAG: cross-file entity index"),
        ("6", "Event Log: chronological events"),
        ("7", "Tech Specs: system information"),
        ("", ""),
        ("SECTION", "Processing & Export"),
        ("M", "Cycle Whisper model (tiny→large)"),
        ("+", "Increase max parallel processes"),
        ("-", "Decrease max parallel processes"),
        ("R", "Requeue all failed files"),
        ("W", "Toggle folder watch mode"),
        ("E", "Cycle Second Brain export format"),
        ("X", "Export now (current format)"),
        ("O", "Open/close Options screen"),
        ("H", "Open/close this Help screen"),
        ("Q", "Quit gracefully (finish current)"),
    ]

    r = middle_start + 2
    for left, right in zip(shortcuts_left, shortcuts_right):
        if r >= middle_end:
            break
        lkey, lval = left
        rkey, rval = right

        if lkey == "SECTION":
            out.append(move_cursor(r, 1))
            out.append(f"  {BD}{C}{lval}{NC}")
        elif lkey:
            out.append(move_cursor(r, 1))
            out.append(f"  {BD}{W}[{lkey}]{NC} {D}{lval}{NC}")
        # else blank row

        if rkey == "SECTION":
            out.append(move_cursor(r, half))
            out.append(f"  {BD}{C}{rval}{NC}")
        elif rkey:
            out.append(move_cursor(r, half))
            out.append(f"  {BD}{W}[{rkey}]{NC} {D}{rval}{NC}")

        r += 1

    sys.stdout.write("".join(out))
    sys.stdout.flush()


# ─── Keyboard Handler ─────────────────────────────────────────────────────────

def handle_keypress(key):
    """Handle a single keypress for live toggling."""
    key_lower = key.lower()

    # ── Overlay toggles (work regardless of overlay state) ──
    if key_lower == 'o':
        STATE.overlay = None if STATE.overlay == "options" else "options"
        return
    elif key_lower == 'h':
        STATE.overlay = None if STATE.overlay == "help" else "help"
        return
    # Escape closes any overlay
    elif key == '\x1b' and STATE.overlay:
        STATE.overlay = None
        return

    # ── All other keys work normally; overlays stay open to show live feedback ──
    if key_lower == 'n':
        STATE.name_privacy = (STATE.name_privacy + 1) % 3
    elif key_lower == 'p':
        STATE.num_privacy = (STATE.num_privacy + 1) % 3
    elif key_lower == 'f':
        STATE.card_mode = (STATE.card_mode + 1) % 7
    elif key_lower == 'd':
        STATE.deception = not STATE.deception
    elif key_lower == 'v':
        STATE.veracity = not STATE.veracity
    elif key_lower == 'j':
        STATE.jefferson = not STATE.jefferson
    elif key_lower == 'c':
        STATE.clinical = not STATE.clinical
    elif key_lower == 'g':
        STATE.voice_dynamics = not STATE.voice_dynamics
    elif key_lower == 'a':
        STATE.emotional = not STATE.emotional
    elif key_lower == 'i':
        STATE.omni = not STATE.omni
    elif key_lower == 'b':
        STATE.viewer = not STATE.viewer
    elif key_lower == 'k':
        STATE.diarise_local = not STATE.diarise_local
    elif key_lower == 'm':
        # Cycle model override
        idx = MODELS.index(STATE.model_override) if STATE.model_override in MODELS else -1
        STATE.model_override = MODELS[(idx + 1) % len(MODELS)] if idx < len(MODELS) - 1 else ""
        # Apply to all still-pending files
        for f in STATE.files:
            if f["status"] == "pending" and STATE.model_override:
                f["model"] = STATE.model_override
        log_event("info", f"Model override: {STATE.model_override or 'auto'}")
    elif key == '+' or key == '=':
        STATE.max_parallel = min(8, STATE.max_parallel + 1)
        log_event("info", f"Parallel: {STATE.max_parallel}")
    elif key == '-':
        STATE.max_parallel = max(1, STATE.max_parallel - 1)
        log_event("info", f"Parallel: {STATE.max_parallel}")
    elif key_lower == 'r':
        # Requeue all failed files
        requeued = 0
        for f in STATE.files:
            if f["status"] == "failed":
                f["status"] = "pending"
                f["pid"] = None
                f["proc"] = None
                f.pop("result", None)
                STATE.failed = max(0, STATE.failed - 1)
                requeued += 1
        if requeued:
            log_event("info", f"Requeued {requeued} failed file(s)")
    elif key_lower == 'q':
        STATE.quit_requested = True
    elif key in '1234567':
        STATE.card_mode = int(key) - 1
    elif key == '\r' or key == '\n':
        # Enter — start processing, also close overlay
        STATE.started = True
        STATE.overlay = None
        log_event("info", "Processing started by user")
    elif key == 'e':
        STATE.export_format = (STATE.export_format + 1) % (len(STATE.export_formats) + 1)
    elif key == 'x':
        if STATE.export_format > 0:
            fmt = STATE.export_formats[STATE.export_format - 1]
            export_second_brain(fmt)
    elif key == 'w':
        STATE.watch_mode = not STATE.watch_mode
        if STATE.watch_mode:
            log_event("info", f"Watch mode ON — monitoring {STATE.watch_dir or 'default dir'}")
    # Arrow keys: \x1b[A=up, \x1b[B=down, \x1b[C=right, \x1b[D=left
    elif key == '\x1b[A':
        if STATE.selected_file_idx > 0:
            STATE.selected_file_idx -= 1
        STATE.current_display_idx = STATE.selected_file_idx
    elif key == '\x1b[B':
        if STATE.selected_file_idx < len(STATE.files) - 1:
            STATE.selected_file_idx += 1
        STATE.current_display_idx = STATE.selected_file_idx
    elif key == '\x1b[C':
        if STATE.selected_file_idx < len(STATE.files) - 1:
            STATE.selected_file_idx += 1
        STATE.current_display_idx = STATE.selected_file_idx
    elif key == '\x1b[D':
        if STATE.selected_file_idx > 0:
            STATE.selected_file_idx -= 1
        STATE.current_display_idx = STATE.selected_file_idx

# ─── Second Brain Export System ───────────────────────────────────────────────

EXPORT_FORMAT_EXPLAINERS = {
    "Wiki MD":      "Markdown with [[wiki-links]] — bidirectional connections, Karpathy-style second brain",
    "Obsidian":     "Full Obsidian vault: frontmatter + wiki-links + graph-ready folder structure",
    "CSV":          "Tabular CSV — one row per entity/quote, importable into Excel/Sheets/databases",
    "JSON":         "Structured JSON — nested blocks, relationships, machine-readable",
    "HTML":         "Web-ready HTML with inline CSS — viewable in any browser",
    "SQL":          "SQL INSERT statements — creates tables for people, places, quotes, indicators",
    "OPML":         "Outline Processor Markup — hierarchical tree, importable to Workflowy/Dynalist",
    "Excel":        "CSV formatted for Excel import — multiple sheets (entities, quotes, indicators)",
    "WordPress":    "WordPress-ready HTML post with formatting, categories, and tags",
    "Substack":     "Substack-ready Markdown newsletter post with sections",
    "CapCut":       "CapCut script: timestamped quote cards for video editing",
    "Notion":       "Notion-import-ready Markdown with database tables and relations",
}

def export_second_brain(fmt):
    """Export all completed file data in the specified Second Brain format."""
    output_dir = SCRIPT_DIR / "second_brain_export"
    output_dir.mkdir(exist_ok=True)

    completed = [f for f in STATE.files if f["status"] == "done" and f.get("result")]
    if not completed:
        log_event("warn", "No completed files to export")
        return

    log_event("info", f"Exporting {len(completed)} files as {fmt}...")

    if fmt == "Wiki MD":
        _export_wiki_md(completed, output_dir)
    elif fmt == "Obsidian":
        _export_obsidian(completed, output_dir)
    elif fmt == "CSV":
        _export_csv(completed, output_dir)
    elif fmt == "JSON":
        _export_json(completed, output_dir)
    elif fmt == "HTML":
        _export_html(completed, output_dir)
    elif fmt == "SQL":
        _export_sql(completed, output_dir)
    elif fmt == "OPML":
        _export_opml(completed, output_dir)
    elif fmt == "Excel":
        _export_excel(completed, output_dir)
    elif fmt == "WordPress":
        _export_wordpress(completed, output_dir)
    elif fmt == "Substack":
        _export_substack(completed, output_dir)
    elif fmt == "CapCut":
        _export_capcut(completed, output_dir)
    elif fmt == "Notion":
        _export_notion(completed, output_dir)

    log_event("info", f"Export complete: {output_dir}/{fmt.lower().replace(' ', '_')}/")


def _export_wiki_md(completed, output_dir):
    """Karpathy-style second brain: markdown files with [[wiki-links]]."""
    export_dir = output_dir / "wiki_md"
    export_dir.mkdir(exist_ok=True)

    # Build entity index for wiki links
    all_people = set()
    all_places = set()
    for f in completed:
        r = f.get("result", {})
        for p in r.get("people", []):
            all_people.add(p.get("name", ""))
        for pl in r.get("places", []):
            all_places.add(pl.get("place", ""))

    # Index page
    index_lines = ["# Second Brain Index\n", "## Files\n"]
    for f in completed:
        safe = f["safe_name"]
        index_lines.append(f"- [[{safe}]] — {f['duration']//60}min, {f.get('result',{}).get('segment_count',0)} segments")

    index_lines.append("\n## People\n")
    for p in sorted(all_people):
        if p:
            index_lines.append(f"- [[{p}]]")

    index_lines.append("\n## Places\n")
    for pl in sorted(all_places):
        if pl:
            index_lines.append(f"- [[{pl}]]")

    (export_dir / "index.md").write_text("\n".join(index_lines), encoding="utf-8")

    # One file per recording
    for f in completed:
        r = f.get("result", {})
        safe = f["safe_name"]
        lines = [
            f"# {safe}\n",
            f"**Duration:** {f['duration']//60}min\n",
            f"**Model:** {r.get('model', '?')}\n",
            f"**Segments:** {r.get('segment_count', 0)}\n",
            f"**Tokens:** ~{f['duration']//60*112}\n",
            f"**Date processed:** {datetime.now().strftime('%Y-%m-%d')}\n",
            "\n## People Mentioned\n",
        ]
        for p in r.get("people", []):
            pname = p.get("name", "")
            if pname:
                lines.append(f"- [[{pname}]] (certainty: {p.get('certainty', 0):.2f}, occurrences: {p.get('occurrences', 1)})")

        lines.append("\n## Places Mentioned\n")
        for pl in r.get("places", []):
            ploc = pl.get("place", "")
            if ploc:
                lines.append(f"- [[{ploc}]] ({pl.get('occurrences', 1)}x)")

        lines.append("\n## Key Quotes\n")
        for q in r.get("quotes", []):
            lines.append(f"> {q.get('emoji','')} [{q.get('intensity',5)}/10] {q.get('text','')}")
            lines.append(f"  — {safe} at {q.get('time','')}\n")

        lines.append("\n## Indicators\n")
        lines.append(f"- Deception markers: {r.get('deception_count', 0)}")
        lines.append(f"- Veracity markers: {r.get('veracity_count', 0)}")
        lines.append(f"- Clinical markers: {r.get('clinical_count', 0)}")
        lines.append(f"- Freeze events: {r.get('freeze_count', 0)}")

        lines.append("\n## Noteworthy\n")
        for nw in r.get("noteworthy", [])[:10]:
            lines.append(f"- {nw.get('note', '')}")

        lines.append("\n## How Conclusions Were Reached\n")
        lines.append("Each indicator above was detected via:")
        lines.append("- **Deception**: text pattern matching for false starts, corrections, stalling repetitions, memory disclaimers, defensive language, evasion")
        lines.append("- **Veracity**: text pattern matching for qualified certainty, sensory detail, temporal sequencing, contextual embedding, cognitive complexity")
        lines.append("- **Clinical**: text pattern matching for PTSD fragmentation, somatic recall, ADHD maze blocks, ASD awkward pauses")
        lines.append("- **Freeze events**: silence >10s between Whisper segments")
        lines.append("- **Jefferson markers**: text pattern matching for shouting, whispering, prolonged sounds, pitch spikes, pauses")
        lines.append(f"\n certainty scores range from 0.00 to 1.00 — below 0.70 should be manually verified")

        (export_dir / f"{safe}.md").write_text("\n".join(lines), encoding="utf-8")


def _export_obsidian(completed, output_dir):
    """Obsidian vault: frontmatter + wiki-links + folder structure."""
    vault = output_dir / "obsidian_vault"
    vault.mkdir(exist_ok=True)
    (vault / "attachments").mkdir(exist_ok=True)
    (vault / "people").mkdir(exist_ok=True)
    (vault / "places").mkdir(exist_ok=True)

    for f in completed:
        r = f.get("result", {})
        safe = f["safe_name"]
        lines = [
            "---",
            f"file: {safe}",
            f"duration: {f['duration']}",
            f"model: {r.get('model', '?')}",
            f"segments: {r.get('segment_count', 0)}",
            f"deception: {r.get('deception_count', 0)}",
            f"veracity: {r.get('veracity_count', 0)}",
            f"clinical: {r.get('clinical_count', 0)}",
            f"freeze_events: {r.get('freeze_count', 0)}",
            f"date: {datetime.now().strftime('%Y-%m-%d')}",
            "tags: [second-brain, audio-analysis]",
            "---",
            "",
            f"# {safe}",
            "",
        ]
        for q in r.get("quotes", []):
            lines.append(f"> {q.get('emoji','')} **[{q.get('intensity',5)}/10]** {q.get('text','')}")
            lines.append("")

        for p in r.get("people", []):
            pname = p.get("name", "")
            if pname:
                lines.append(f"Person: [[people/{pname}|{pname}]] (cert: {p.get('certainty',0):.2f})")

        (vault / f"{safe}.md").write_text("\n".join(lines), encoding="utf-8")


def _export_csv(completed, output_dir):
    """CSV export — entities, quotes, indicators as separate CSVs."""
    import csv as csv_mod
    export_dir = output_dir / "csv"
    export_dir.mkdir(exist_ok=True)

    # Entities CSV
    with open(export_dir / "entities.csv", "w", newline="", encoding="utf-8") as ef:
        w = csv_mod.writer(ef)
        w.writerow(["file", "entity", "type", "certainty", "occurrences"])
        for f in completed:
            r = f.get("result", {})
            for p in r.get("people", []):
                w.writerow([f["safe_name"], p.get("name",""), "person", p.get("certainty",0), p.get("occurrences",1)])
            for pl in r.get("places", []):
                w.writerow([f["safe_name"], pl.get("place",""), "place", pl.get("certainty",0), pl.get("occurrences",1)])

    # Quotes CSV
    with open(export_dir / "quotes.csv", "w", newline="", encoding="utf-8") as qf:
        w = csv_mod.writer(qf)
        w.writerow(["file", "time", "emoji", "affect", "intensity", "text"])
        for f in completed:
            r = f.get("result", {})
            for q in r.get("quotes", []):
                w.writerow([f["safe_name"], q.get("time",""), q.get("emoji",""), q.get("affect",""), q.get("intensity",5), q.get("text","")])

    # Indicators CSV
    with open(export_dir / "indicators.csv", "w", newline="", encoding="utf-8") as inf:
        w = csv_mod.writer(inf)
        w.writerow(["file", "deception", "veracity", "clinical", "freezes", "noteworthy", "segments", "tokens"])
        for f in completed:
            r = f.get("result", {})
            w.writerow([f["safe_name"], r.get("deception_count",0), r.get("veracity_count",0), r.get("clinical_count",0), r.get("freeze_count",0), r.get("noteworthy_count",0), r.get("segment_count",0), f["duration"]//60*112])


def _export_json(completed, output_dir):
    """Structured JSON export."""
    export_dir = output_dir / "json"
    export_dir.mkdir(exist_ok=True)
    data = {"export_date": datetime.now().isoformat(), "files": []}
    for f in completed:
        data["files"].append({
            "name": f["safe_name"],
            "duration": f["duration"],
            "result": f.get("result", {}),
        })
    (export_dir / "second_brain.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _export_html(completed, output_dir):
    """Generate a rich, interactive batch viewer HTML file."""
    export_dir = output_dir / "html"
    export_dir.mkdir(exist_ok=True)

    # Build embedded data payload — load full omni.md for each file if available
    files_data = []
    for f in completed:
        r = f.get("result", {})
        entry = {
            "name": f["safe_name"],
            "original_name": f.get("name", f["safe_name"]),
            "duration": f["duration"],
            "status": f["status"],
            "output_dir": f.get("output_dir", ""),
            "result": r,
        }
        # Embed omni.md content if present
        omni_path = Path(f.get("output_dir", "")) / "omni.md"
        if omni_path.exists():
            try:
                entry["omni_md"] = omni_path.read_text(encoding="utf-8")
            except Exception:
                entry["omni_md"] = ""
        # Embed transcript.md
        transcript_path = Path(f.get("output_dir", "")) / "transcript.md"
        if transcript_path.exists():
            try:
                entry["transcript_md"] = transcript_path.read_text(encoding="utf-8")
            except Exception:
                entry["transcript_md"] = ""
        files_data.append(entry)

    batch_payload = json.dumps({
        "generated": datetime.now().isoformat(),
        "files": files_data,
    }, ensure_ascii=False, indent=None)

    html = _build_batch_viewer_html(batch_payload)
    out_path = export_dir / "batch_viewer.html"
    out_path.write_text(html, encoding="utf-8")
    log_event("info", f"Batch viewer: {out_path}")


def _build_batch_viewer_html(batch_payload_json: str) -> str:
    """Build the complete batch viewer HTML string."""
    # Escape </script> inside JSON payload
    safe_payload = batch_payload_json.replace("</script>", "<\\/script>")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>🎧 Emotion Audio Batch Viewer</title>
<style>
:root{{
  --bg:#0d1117;--bg-card:#161b22;--bg-hover:#21262d;--bg-active:#1f3044;
  --border:#30363d;--text:#e6edf3;--muted:#8b949e;--accent:#388bfd;
  --green:#3fb950;--yellow:#d29922;--red:#f85149;--purple:#bc8cff;--orange:#f0883e;
  --sidebar-w:260px;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,-apple-system,'Segoe UI',Roboto,Arial;background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column;overflow:hidden}}
/* TOP BAR */
#topbar{{background:#010409;border-bottom:1px solid var(--border);padding:0 16px;height:52px;display:flex;align-items:center;gap:16px;flex-shrink:0}}
#topbar h1{{font-size:15px;font-weight:600;white-space:nowrap}}
#batch-pills{{display:flex;gap:8px;flex-wrap:wrap}}
.pill{{background:var(--bg-card);border:1px solid var(--border);border-radius:20px;padding:2px 10px;font-size:12px;white-space:nowrap}}
.pill.dec{{border-color:var(--red);color:var(--red)}}
.pill.ver{{border-color:var(--green);color:var(--green)}}
.pill.clin{{border-color:var(--yellow);color:var(--yellow)}}
.pill.freeze{{border-color:var(--purple);color:var(--purple)}}
#mode-badge{{margin-left:auto;font-size:11px;color:var(--muted);border:1px solid var(--border);border-radius:4px;padding:2px 8px}}
/* MAIN LAYOUT */
#layout{{display:flex;flex:1;overflow:hidden}}
/* SIDEBAR */
#sidebar{{width:var(--sidebar-w);flex-shrink:0;background:var(--bg-card);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}}
#sidebar-header{{padding:10px 12px;font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid var(--border)}}
#file-list{{overflow-y:auto;flex:1}}
.file-item{{padding:10px 12px;border-bottom:1px solid var(--border);cursor:pointer;transition:background .1s}}
.file-item:hover{{background:var(--bg-hover)}}
.file-item.active{{background:var(--bg-active);border-left:3px solid var(--accent)}}
.fi-name{{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.fi-meta{{font-size:11px;color:var(--muted);margin-top:3px}}
.fi-badges{{display:flex;gap:4px;margin-top:5px;flex-wrap:wrap}}
.fi-badge{{font-size:10px;padding:1px 5px;border-radius:3px;font-weight:600}}
.fi-badge.d{{background:#3d1a1a;color:var(--red)}}
.fi-badge.v{{background:#1a3d1a;color:var(--green)}}
.fi-badge.c{{background:#3d2e1a;color:var(--yellow)}}
.fi-badge.f{{background:#2a1a3d;color:var(--purple)}}
/* MAIN CONTENT */
#main{{flex:1;display:flex;flex-direction:column;overflow:hidden}}
/* TABS */
#tabs{{display:flex;border-bottom:1px solid var(--border);background:var(--bg-card);flex-shrink:0;padding:0 12px;gap:0;overflow-x:auto}}
.tab{{padding:10px 14px;font-size:13px;cursor:pointer;border-bottom:2px solid transparent;color:var(--muted);white-space:nowrap;transition:color .15s,border-color .15s}}
.tab:hover{{color:var(--text)}}
.tab.active{{color:var(--text);border-bottom-color:var(--accent)}}
/* TAB PANELS */
#tab-content{{flex:1;overflow-y:auto;padding:20px}}
.panel{{display:none}}
.panel.active{{display:block}}
/* STAT CARDS */
.stats-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px;margin-bottom:20px}}
.stat-card{{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center}}
.stat-card .num{{font-size:28px;font-weight:700;line-height:1}}
.stat-card .label{{font-size:11px;color:var(--muted);margin-top:4px;text-transform:uppercase;letter-spacing:.04em}}
.stat-card.dec .num{{color:var(--red)}}
.stat-card.ver .num{{color:var(--green)}}
.stat-card.clin .num{{color:var(--yellow)}}
.stat-card.freeze .num{{color:var(--purple)}}
.stat-card.words .num{{color:var(--accent)}}
/* SECTION HEADINGS */
.section-head{{font-size:13px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin:20px 0 10px;border-bottom:1px solid var(--border);padding-bottom:6px}}
/* EMOTION BAR CHART */
.emo-chart{{display:flex;flex-direction:column;gap:6px}}
.emo-row{{display:flex;align-items:center;gap:8px;font-size:13px}}
.emo-label{{width:130px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--muted)}}
.emo-bar-wrap{{flex:1;height:16px;background:var(--bg-card);border-radius:4px;overflow:hidden}}
.emo-bar{{height:100%;background:var(--accent);border-radius:4px;transition:width .3s}}
.emo-count{{width:30px;text-align:right;font-size:12px;color:var(--muted)}}
/* TRANSCRIPT */
#transcript-text{{font-family:'JetBrains Mono','Fira Code','Consolas',monospace;font-size:13px;line-height:1.7;white-space:pre-wrap;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:16px;max-height:calc(100vh - 280px);overflow-y:auto}}
.ts-timestamp{{color:var(--accent);cursor:pointer}}
.ts-timestamp:hover{{text-decoration:underline}}
.ts-dec{{background:#3d1a1a;color:var(--red);border-radius:2px;padding:0 2px}}
.ts-ver{{background:#1a3d1a;color:var(--green);border-radius:2px;padding:0 2px}}
.ts-jef{{color:var(--orange);font-weight:600}}
.ts-freeze{{background:#2a1a3d;color:var(--purple);border-radius:2px;padding:0 2px}}
/* INDICATOR TABLE */
.ind-table{{width:100%;border-collapse:collapse;font-size:13px}}
.ind-table th{{padding:8px 10px;text-align:left;color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em;border-bottom:2px solid var(--border)}}
.ind-table td{{padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:top}}
.ind-table tr:hover td{{background:var(--bg-hover)}}
.cert-bar{{height:6px;border-radius:3px;background:var(--border)}}
.cert-fill{{height:100%;border-radius:3px}}
.sym-dec{{color:var(--red);font-weight:700;font-family:monospace}}
.sym-ver{{color:var(--green);font-weight:700;font-family:monospace}}
/* NOTEWORTHY */
.nw-list{{display:flex;flex-direction:column;gap:8px}}
.nw-item{{background:var(--bg-card);border:1px solid var(--border);border-radius:6px;padding:10px 14px;display:flex;gap:10px;align-items:flex-start}}
.nw-icon{{font-size:16px;flex-shrink:0}}
.nw-note{{font-size:13px;line-height:1.5}}
.nw-time{{font-size:11px;color:var(--muted);margin-top:2px}}
/* ENTITIES */
.entity-table{{width:100%;border-collapse:collapse;font-size:13px}}
.entity-table th{{padding:7px 10px;text-align:left;color:var(--muted);font-size:11px;text-transform:uppercase;border-bottom:2px solid var(--border)}}
.entity-table td{{padding:7px 10px;border-bottom:1px solid var(--border)}}
.entity-table tr:hover td{{background:var(--bg-hover)}}
/* OMNI VIEW */
#omni-content{{font-size:13px;line-height:1.8;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:20px;max-height:calc(100vh - 280px);overflow-y:auto}}
#omni-content h1,#omni-content h2{{color:var(--text);border-bottom:1px solid var(--border);padding-bottom:6px;margin:20px 0 10px}}
#omni-content h3{{color:var(--muted);margin:14px 0 8px}}
#omni-content table{{border-collapse:collapse;width:100%;margin:10px 0;font-size:12px}}
#omni-content th{{background:var(--bg-hover);padding:6px 10px;text-align:left;border:1px solid var(--border)}}
#omni-content td{{padding:6px 10px;border:1px solid var(--border)}}
#omni-content code{{background:var(--bg-hover);padding:1px 5px;border-radius:3px;font-family:monospace}}
#omni-content blockquote{{border-left:3px solid var(--border);padding-left:12px;color:var(--muted);margin:8px 0}}
/* AUDIO PLAYER */
#player{{background:#010409;border-top:1px solid var(--border);padding:8px 16px;display:flex;align-items:center;gap:12px;flex-shrink:0;height:54px}}
#player-title{{font-size:12px;color:var(--muted);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
#player audio{{height:32px;flex:1;accent-color:var(--accent);min-width:0}}
/* SCROLLBARS */
::-webkit-scrollbar{{width:6px;height:6px}}
::-webkit-scrollbar-track{{background:transparent}}
::-webkit-scrollbar-thumb{{background:var(--border);border-radius:3px}}
::-webkit-scrollbar-thumb:hover{{background:var(--muted)}}
/* EMPTY STATE */
.empty{{color:var(--muted);font-size:13px;font-style:italic;padding:20px 0}}
/* QUOTES */
.quote-item{{background:var(--bg-card);border-left:3px solid var(--accent);padding:10px 14px;margin-bottom:8px;border-radius:0 6px 6px 0}}
.quote-header{{display:flex;align-items:center;gap:8px;margin-bottom:4px}}
.quote-text{{font-size:13px;line-height:1.5;color:var(--text)}}
.intensity{{font-size:11px;color:var(--muted)}}
</style>
</head>
<body>
<div id="topbar">
  <h1>🎧 Emotion Audio Analyser — Batch Viewer</h1>
  <div id="batch-pills"></div>
  <div id="mode-badge">Embedded Data</div>
</div>
<div id="layout">
  <aside id="sidebar">
    <div id="sidebar-header">Batch Files (<span id="file-count">0</span>)</div>
    <div id="file-list"></div>
  </aside>
  <div id="main">
    <div id="tabs">
      <div class="tab active" data-tab="overview">Overview</div>
      <div class="tab" data-tab="transcript">Transcript</div>
      <div class="tab" data-tab="emotions">Emotions</div>
      <div class="tab" data-tab="indicators">Indicators</div>
      <div class="tab" data-tab="entities">Entities</div>
      <div class="tab" data-tab="noteworthy">Noteworthy</div>
      <div class="tab" data-tab="omni">Omni View</div>
    </div>
    <div id="tab-content">
      <div class="panel active" id="panel-overview"></div>
      <div class="panel" id="panel-transcript"></div>
      <div class="panel" id="panel-emotions"></div>
      <div class="panel" id="panel-indicators"></div>
      <div class="panel" id="panel-entities"></div>
      <div class="panel" id="panel-noteworthy"></div>
      <div class="panel" id="panel-omni"></div>
    </div>
  </div>
</div>
<div id="player">
  <span id="player-title">No file selected</span>
  <audio id="audio-el" controls></audio>
</div>
<script>
const BATCH_DATA = {safe_payload};

let selectedIdx = 0;
const audioEl = document.getElementById('audio-el');

function esc(s){{ const d=document.createElement('div');d.textContent=String(s||'');return d.innerHTML; }}

function fmt_dur(s){{
  const m=Math.floor(s/60), sec=Math.floor(s%60);
  return `${{m}}:${{sec.toString().padStart(2,'0')}}`;
}}

function cert_color(c){{
  if(c>=0.7) return 'var(--green)';
  if(c>=0.5) return 'var(--yellow)';
  return 'var(--red)';
}}

// Build batch summary pills
function renderBatchSummary(){{
  const files = BATCH_DATA.files||[];
  let totDec=0,totVer=0,totClin=0,totFreeze=0,totWords=0,totDur=0;
  files.forEach(f=>{{
    const r=f.result||{{}};
    totDec+=r.deception_count||0;
    totVer+=r.veracity_count||0;
    totClin+=r.clinical_count||0;
    totFreeze+=r.freeze_count||0;
    totWords+=r.word_count||0;
    totDur+=f.duration||0;
  }});
  const pills = document.getElementById('batch-pills');
  pills.innerHTML = `
    <span class="pill">📁 ${{files.length}} files</span>
    <span class="pill">⏱ ${{fmt_dur(totDur)}}</span>
    <span class="pill dec">🧠 ${{totDec}} deception</span>
    <span class="pill ver">✅ ${{totVer}} veracity</span>
    <span class="pill clin">🏥 ${{totClin}} clinical</span>
    <span class="pill freeze">❄️ ${{totFreeze}} freezes</span>
    <span class="pill">📝 ${{totWords.toLocaleString()}} words</span>
  `;
}}

// Build sidebar file list
function renderSidebar(){{
  const files = BATCH_DATA.files||[];
  document.getElementById('file-count').textContent = files.length;
  const list = document.getElementById('file-list');
  list.innerHTML = '';
  files.forEach((f,i)=>{{
    const r=f.result||{{}};
    const item = document.createElement('div');
    item.className = 'file-item' + (i===selectedIdx?' active':'');
    item.innerHTML = `
      <div class="fi-name" title="${{esc(f.original_name||f.name)}}">${{esc(f.name)}}</div>
      <div class="fi-meta">${{fmt_dur(f.duration||0)}} · ${{r.segment_count||0}} segs · ${{r.word_count||0}} words</div>
      <div class="fi-badges">
        ${{(r.deception_count||0)>0?`<span class="fi-badge d">⚠ ${{r.deception_count}} dec</span>`:''}}
        ${{(r.veracity_count||0)>0?`<span class="fi-badge v">✓ ${{r.veracity_count}} ver</span>`:''}}
        ${{(r.clinical_count||0)>0?`<span class="fi-badge c">🏥 ${{r.clinical_count}} clin</span>`:''}}
        ${{(r.freeze_count||0)>0?`<span class="fi-badge f">❄ ${{r.freeze_count}} freeze</span>`:''}}
      </div>
    `;
    item.onclick = ()=>selectFile(i);
    list.appendChild(item);
  }});
}}

function selectFile(i){{
  selectedIdx = i;
  renderSidebar();
  renderAllPanels();
  // Try to load audio
  const f = (BATCH_DATA.files||[])[i];
  if(f && f.output_dir){{
    const audioName = (f.original_name||f.name||'').replace(/\\/g,'/');
    // Try audio file in output_dir parent
    const base = f.output_dir.replace(/_subfile$/,'');
    audioEl.src = base;
    document.getElementById('player-title').textContent = f.name||'';
  }}
}}

function renderAllPanels(){{
  const f = (BATCH_DATA.files||[])[selectedIdx];
  if(!f) return;
  renderOverview(f);
  renderTranscript(f);
  renderEmotions(f);
  renderIndicators(f);
  renderEntities(f);
  renderNoteworthy(f);
  renderOmni(f);
}}

function renderOverview(f){{
  const r = f.result||{{}};
  const p = document.getElementById('panel-overview');
  const emo = r.emotion_dist||{{}};
  const topEmo = Object.entries(emo).sort((a,b)=>b[1]-a[1]).slice(0,1)[0];
  const topEmoStr = topEmo?`${{topEmo[0]}} (${{topEmo[1]}})`:'—';

  let quotesHtml = '';
  (r.quotes||[]).slice(0,5).forEach(q=>{{
    const intColor = q.intensity>=8?'var(--red)':q.intensity>=6?'var(--yellow)':'var(--green)';
    quotesHtml += `<div class="quote-item">
      <div class="quote-header">
        <span style="font-size:18px">${{esc(q.emoji||'')}}</span>
        <span style="font-size:12px;color:var(--muted)">${{esc(q.time||'')}}</span>
        <span class="intensity" style="color:${{intColor}};font-weight:600">${{q.intensity||5}}/10</span>
        <span class="intensity">${{esc(q.affect||'')}}</span>
      </div>
      <div class="quote-text">${{esc(q.text||'')}}</div>
    </div>`;
  }});
  if(!quotesHtml) quotesHtml = '<div class="empty">No high-intensity quotes detected</div>';

  p.innerHTML = `
    <div class="stats-grid">
      <div class="stat-card dec"><div class="num">${{r.deception_count||0}}</div><div class="label">Deception</div></div>
      <div class="stat-card ver"><div class="num">${{r.veracity_count||0}}</div><div class="label">Veracity</div></div>
      <div class="stat-card clin"><div class="num">${{r.clinical_count||0}}</div><div class="label">Clinical</div></div>
      <div class="stat-card freeze"><div class="num">${{r.freeze_count||0}}</div><div class="label">Freezes</div></div>
      <div class="stat-card words"><div class="num">${{r.word_count||0}}</div><div class="label">Words</div></div>
      <div class="stat-card"><div class="num">${{r.segment_count||0}}</div><div class="label">Segments</div></div>
      <div class="stat-card"><div class="num" style="font-size:16px;padding-top:4px">${{esc(r.model||'?')}}</div><div class="label">Model</div></div>
      <div class="stat-card"><div class="num" style="font-size:16px;padding-top:4px">${{fmt_dur(f.duration||0)}}</div><div class="label">Duration</div></div>
    </div>
    <div class="section-head">💬 High-Intensity Quotes</div>
    ${{quotesHtml}}
  `;
}}

function renderTranscript(f){{
  const p = document.getElementById('panel-transcript');
  const raw = f.transcript_md||'';
  if(!raw){{ p.innerHTML='<div class="empty">No transcript available</div>'; return; }}
  // Highlight timestamps, deception markers, veracity markers, Jefferson markers
  let html = esc(raw)
    .replace(/\\[(\\d{{2}}:\\d{{2}}(?:\\.\\d+)?)\\]/g, '<span class="ts-timestamp" onclick="seekAudio($1)">[$1]</span>')
    .replace(/&lt;(fs|corrsp|rep|lack-mem|over-elab|defensive|contradict|cog-load|evade)[^&gt;]*&gt;(.*?)&lt;\\/\\1&gt;/g,
             '<span class="ts-dec">&lt;$1&gt;$2&lt;/$1&gt;</span>')
    .replace(/&lt;(veracious|sensory-recall|temporal|context|emo-consist|cog-complex|spontaneous|recall-pause)[^&gt;]*&gt;(.*?)&lt;\\/\\1&gt;/g,
             '<span class="ts-ver">&lt;$1&gt;$2&lt;/$1&gt;</span>')
    .replace(/\\((\\d+\\.\\d+)\\)|\\((\\d+:\\d+\\.\\d+)\\)/g, '<span class="ts-freeze">($1$2)</span>');
  p.innerHTML = `<div id="transcript-text">${{html}}</div>`;
}}

function seekAudio(ts){{
  // ts is MM:SS — convert to seconds and seek
  const parts = String(ts).split(':');
  if(parts.length===2){{
    const secs = parseInt(parts[0])*60+parseInt(parts[1]);
    audioEl.currentTime=secs; audioEl.play();
  }}
}}

function renderEmotions(f){{
  const r = f.result||{{}};
  const p = document.getElementById('panel-emotions');
  const emo = r.emotion_dist||{{}};
  const total = Object.values(emo).reduce((a,b)=>a+b,0)||1;
  const sorted = Object.entries(emo).sort((a,b)=>b[1]-a[1]);

  let chart = '<div class="emo-chart">';
  sorted.forEach(([label,count])=>{{
    const pct = Math.round(count/total*100);
    chart += `<div class="emo-row">
      <div class="emo-label">${{esc(label)}}</div>
      <div class="emo-bar-wrap"><div class="emo-bar" style="width:${{pct}}%"></div></div>
      <div class="emo-count">${{count}}</div>
    </div>`;
  }});
  chart += '</div>';

  // Freeze events
  let freezeHtml = '';
  (r.freeze_events||[]).forEach(fe=>{{
    freezeHtml += `<div class="nw-item">
      <div class="nw-icon">❄️</div>
      <div><div class="nw-note">Freeze/silence event</div>
      <div class="nw-time">${{esc(JSON.stringify(fe))}}</div></div>
    </div>`;
  }});
  if(!freezeHtml) freezeHtml = '<div class="empty">No freeze events detected</div>';

  if(!sorted.length){{ p.innerHTML='<div class="empty">No emotion data available</div>'; return; }}
  p.innerHTML = `
    <div class="section-head">🎭 Emotion Distribution</div>
    ${{chart}}
    <div class="section-head">❄️ Freeze / Silence Events (${{(r.freeze_events||[]).length}})</div>
    <div class="nw-list">${{freezeHtml}}</div>
  `;
}}

function renderIndicators(f){{
  const r = f.result||{{}};
  const p = document.getElementById('panel-indicators');

  function indTable(items, symClass, label){{
    if(!items||!items.length) return `<div class="empty">No ${{label}} detected</div>`;
    let html = `<table class="ind-table"><thead><tr>
      <th>Time</th><th>Symbol</th><th>Type</th><th>Note</th><th>Certainty</th>
    </tr></thead><tbody>`;
    items.forEach(it=>{{
      const cert = it.certainty||it.confidence||0;
      const w = Math.round(cert*100);
      const col = cert_color(cert);
      html += `<tr>
        <td style="color:var(--accent);font-family:monospace">${{esc(it.timestamp||'')}}</td>
        <td><span class="${{symClass}}">${{esc(it.symbol||it.type||'')}}</span></td>
        <td style="color:var(--muted)">${{esc(it.type||'')}}</td>
        <td>${{esc(it.note||it.description||'')}}</td>
        <td><div class="cert-bar"><div class="cert-fill" style="width:${{w}}%;background:${{col}}"></div></div>
          <span style="font-size:11px;color:var(--muted)">${{cert.toFixed(2)}}</span></td>
      </tr>`;
    }});
    html += '</tbody></table>';
    return html;
  }}

  // Extract from noteworthy items as fallback
  const noteworthy = r.noteworthy||[];
  const decItems = noteworthy.filter(n=>n.type&&n.type.includes('deception'));
  const verItems = noteworthy.filter(n=>n.type&&n.type.includes('veracity'));

  p.innerHTML = `
    <div class="section-head">🧠 Deception Indicators (${{r.deception_count||decItems.length}})</div>
    ${{indTable(decItems, 'sym-dec', 'deception indicators')}}
    <div class="section-head" style="margin-top:24px">✅ Veracity Indicators (${{r.veracity_count||verItems.length}})</div>
    ${{indTable(verItems, 'sym-ver', 'veracity indicators')}}
    <div style="margin-top:16px;padding:10px;background:var(--bg-card);border:1px solid var(--border);border-radius:6px;font-size:12px;color:var(--muted)">
      <strong style="color:var(--text)">How these are detected:</strong><br>
      Deception: false-starts &lt;fs&gt;, corrections &lt;corrsp&gt;, stalling &lt;rep&gt;, memory disclaimers &lt;lack-mem&gt;, over-elaboration, defensive language, contradiction, cognitive load, evasion<br>
      Veracity: qualified certainty, sensory detail &lt;sensory-recall&gt;, temporal sequencing &lt;temporal&gt;, contextual embedding, cognitive complexity, spontaneous recall<br>
      Certainty scores &lt;0.70 should be manually verified.
    </div>
  `;
}}

function renderEntities(f){{
  const r = f.result||{{}};
  const p = document.getElementById('panel-entities');
  const people = r.people||[];
  const places = r.places||[];
  const hashtags = r.hashtags||[];

  let pplHtml = '';
  if(people.length){{
    pplHtml = '<table class="entity-table"><thead><tr><th>Name</th><th>Certainty</th><th>Occurrences</th></tr></thead><tbody>';
    people.forEach(pe=>{{
      const cert = pe.certainty||0;
      pplHtml += `<tr>
        <td>${{esc(pe.name||'')}}</td>
        <td><div class="cert-bar" style="width:60px"><div class="cert-fill" style="width:${{Math.round(cert*100)}}%;background:${{cert_color(cert)}}"></div></div></td>
        <td style="color:var(--muted)">${{pe.occurrences||1}}</td>
      </tr>`;
    }});
    pplHtml += '</tbody></table>';
  }} else pplHtml = '<div class="empty">No people detected</div>';

  let plHtml = '';
  if(places.length){{
    plHtml = '<table class="entity-table"><thead><tr><th>Place</th><th>Certainty</th><th>Occurrences</th></tr></thead><tbody>';
    places.forEach(pl=>{{
      const cert = pl.certainty||0;
      plHtml += `<tr>
        <td>${{esc(pl.place||pl.name||'')}}</td>
        <td><div class="cert-bar" style="width:60px"><div class="cert-fill" style="width:${{Math.round(cert*100)}}%;background:${{cert_color(cert)}}"></div></div></td>
        <td style="color:var(--muted)">${{pl.occurrences||1}}</td>
      </tr>`;
    }});
    plHtml += '</tbody></table>';
  }} else plHtml = '<div class="empty">No places detected</div>';

  let tagsHtml = hashtags.length
    ? hashtags.map(t=>`<span class="pill" style="margin:2px">${{esc(t)}}</span>`).join('')
    : '<div class="empty">No hashtags</div>';

  p.innerHTML = `
    <div class="section-head">👥 People Mentioned</div>
    ${{pplHtml}}
    <div class="section-head">📍 Places Mentioned</div>
    ${{plHtml}}
    <div class="section-head">🏷 Hashtags</div>
    <div style="display:flex;flex-wrap:wrap;gap:4px;padding:4px 0">${{tagsHtml}}</div>
  `;
}}

function renderNoteworthy(f){{
  const r = f.result||{{}};
  const p = document.getElementById('panel-noteworthy');
  const items = r.noteworthy||[];
  if(!items.length){{ p.innerHTML='<div class="empty">No noteworthy items</div>'; return; }}

  const iconMap = {{
    freeze:'❄️', deception:'🚨', veracity:'✅', clinical:'🏥', entity:'🔍',
    jefferson:'📝', voice:'🎤', unknown:'•'
  }};

  let html = '<div class="nw-list">';
  items.forEach(it=>{{
    const t = it.type||'unknown';
    const icon = Object.keys(iconMap).find(k=>t.includes(k))||'unknown';
    html += `<div class="nw-item">
      <div class="nw-icon">${{iconMap[icon]}}</div>
      <div>
        <div class="nw-note">${{esc(it.note||it.description||'')}}</div>
        <div class="nw-time">${{esc(it.timestamp||it.time||'')}}&nbsp;·&nbsp;<span style="color:var(--muted)">${{esc(t)}}</span></div>
      </div>
    </div>`;
  }});
  html += '</div>';
  p.innerHTML = html;
}}

function renderOmni(f){{
  const p = document.getElementById('panel-omni');
  const raw = f.omni_md||'';
  if(!raw){{ p.innerHTML='<div class="empty">No omni.md available for this file</div>'; return; }}
  // Simple markdown → HTML conversion
  let html = esc(raw)
    // Tables
    .replace(/^(\\|.+\\|)$/gm, m=>m)
    // Code blocks
    .replace(/```[\\s\\S]*?```/g, m=>`<pre><code>${{m.replace(/```/g,'')}}</code></pre>`)
    .replace(/^### (.+)$/gm,'<h3>$1</h3>')
    .replace(/^## (.+)$/gm,'<h2>$1</h2>')
    .replace(/^# (.+)$/gm,'<h1>$1</h1>')
    .replace(/\\*\\*(.+?)\\*\\*/g,'<strong>$1</strong>')
    .replace(/\\*(.+?)\\*/g,'<em>$1</em>')
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/^---$/gm,'<hr style="border-color:var(--border)">')
    .replace(/\\n/g,'<br>');
  p.innerHTML = `<div id="omni-content">${{html}}</div>`;
}}

// Tab switching
document.querySelectorAll('.tab').forEach(tab=>{{
  tab.onclick = ()=>{{
    document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(t=>t.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('panel-'+tab.dataset.tab).classList.add('active');
  }};
}});

// Init
renderBatchSummary();
renderSidebar();
if((BATCH_DATA.files||[]).length>0) selectFile(0);
</script>
</body>
</html>"""


def _export_sql(completed, output_dir):
    """SQL INSERT statements."""
    export_dir = output_dir / "sql"
    export_dir.mkdir(exist_ok=True)
    lines = [
        "-- Second Brain SQL Export",
        "-- Auto-generated by Emotion Audio Analyser",
        "",
        "CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, name TEXT, duration_s INTEGER, segments INTEGER, tokens INTEGER);",
        "CREATE TABLE IF NOT EXISTS people (id INTEGER PRIMARY KEY, file_id INTEGER, name TEXT, certainty REAL, occurrences INTEGER);",
        "CREATE TABLE IF NOT EXISTS quotes (id INTEGER PRIMARY KEY, file_id INTEGER, time TEXT, affect TEXT, intensity INTEGER, text TEXT);",
        "CREATE TABLE IF NOT EXISTS indicators (file_id INTEGER PRIMARY KEY, deception INTEGER, veracity INTEGER, clinical INTEGER, freezes INTEGER);",
        "",
    ]
    for i, f in enumerate(completed, 1):
        r = f.get("result", {})
        safe = f["safe_name"].replace("'", "''")
        lines.append(f"INSERT INTO files VALUES ({i}, '{safe}', {f['duration']}, {r.get('segment_count',0)}, {f['duration']//60*112});")
        for p in r.get("people", []):
            pname = p.get("name","").replace("'", "''")
            lines.append(f"INSERT INTO people VALUES (NULL, {i}, '{pname}', {p.get('certainty',0)}, {p.get('occurrences',1)});")
        for q in r.get("quotes", []):
            qtext = q.get("text","").replace("'", "''")
            lines.append(f"INSERT INTO quotes VALUES (NULL, {i}, '{q.get('time','')}', '{q.get('affect','')}', {q.get('intensity',5)}, '{qtext}');")
        lines.append(f"INSERT INTO indicators VALUES ({i}, {r.get('deception_count',0)}, {r.get('veracity_count',0)}, {r.get('clinical_count',0)}, {r.get('freeze_count',0)});")
    (export_dir / "second_brain.sql").write_text("\n".join(lines), encoding="utf-8")


def _export_opml(completed, output_dir):
    """OPML outline export."""
    export_dir = output_dir / "opml"
    export_dir.mkdir(exist_ok=True)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<opml version="2.0"><head><title>Second Brain</title></head><body>']
    for f in completed:
        r = f.get("result", {})
        lines.append(f'  <outline text="{f["safe_name"]}">')
        for q in r.get("quotes", []):
            lines.append(f'    <outline text="{q.get("text","")[:80]}" />')
        lines.append('  </outline>')
    lines.append('</body></opml>')
    (export_dir / "second_brain.opml").write_text("\n".join(lines), encoding="utf-8")


def _export_excel(completed, output_dir):
    """Excel-compatible CSV with multiple sheets (files)."""
    import csv as csv_mod
    export_dir = output_dir / "excel"
    export_dir.mkdir(exist_ok=True)
    # Single combined CSV that Excel can open
    with open(export_dir / "second_brain.xlsx.csv", "w", newline="", encoding="utf-8") as ef:
        w = csv_mod.writer(ef)
        w.writerow(["File", "Duration", "Segments", "Tokens", "Deception", "Veracity", "Clinical", "Freezes", "Top Emotion", "People Count"])
        for f in completed:
            r = f.get("result", {})
            emo = r.get("emotion_dist", {})
            top_emo = max(emo, key=emo.get) if emo else "N/A"
            w.writerow([f["safe_name"], f"{f['duration']//60}min", r.get("segment_count",0), f["duration"]//60*112, r.get("deception_count",0), r.get("veracity_count",0), r.get("clinical_count",0), r.get("freeze_count",0), top_emo, len(r.get("people",[]))])


def _export_wordpress(completed, output_dir):
    """WordPress-ready HTML post."""
    export_dir = output_dir / "wordpress"
    export_dir.mkdir(exist_ok=True)
    lines = ["<!-- WordPress Post Export -->",
             "<h2>🎧 Audio Analysis Batch Report</h2>",
             f"<p>Processed {len(completed)} files on {datetime.now().strftime('%Y-%m-%d')}</p>"]
    for f in completed:
        r = f.get("result", {})
        lines.append(f"<h3>{f['safe_name']}</h3>")
        lines.append(f"<p>Duration: {f['duration']//60}min | Deception: {r.get('deception_count',0)} | Veracity: {r.get('veracity_count',0)}</p>")
        lines.append("<blockquote>")
        for q in r.get("quotes", [])[:3]:
            lines.append(f"<p>{q.get('emoji','')} {q.get('text','')}</p>")
        lines.append("</blockquote>")
    lines.append("\n<!-- Categories: audio-analysis, second-brain -->")
    lines.append("<!-- Tags: emotion, deception, veracity, transcription -->")
    (export_dir / "wordpress_post.html").write_text("\n".join(lines), encoding="utf-8")


def _export_substack(completed, output_dir):
    """Substack-ready Markdown newsletter."""
    export_dir = output_dir / "substack"
    export_dir.mkdir(exist_ok=True)
    lines = [f"# Audio Analysis Batch — {datetime.now().strftime('%B %d, %Y')}\n"]
    lines.append(f"*{len(completed)} files processed*\n")
    for f in completed:
        r = f.get("result", {})
        lines.append(f"## {f['safe_name']}\n")
        lines.append(f"*{f['duration']//60} minutes | {r.get('segment_count',0)} segments*\n")
        for q in r.get("quotes", [])[:2]:
            lines.append(f"> {q.get('emoji','')} **[{q.get('intensity',5)}/10]** {q.get('text','')}\n")
        lines.append(f"\n*Deception: {r.get('deception_count',0)} | Veracity: {r.get('veracity_count',0)} | Clinical: {r.get('clinical_count',0)}*\n")
    (export_dir / "substack_post.md").write_text("\n".join(lines), encoding="utf-8")


def _export_capcut(completed, output_dir):
    """CapCut script: timestamped quote cards for video editing."""
    export_dir = output_dir / "capcut"
    export_dir.mkdir(exist_ok=True)
    lines = ["# CapCut Script — Timestamped Quote Cards\n"]
    for f in completed:
        r = f.get("result", {})
        lines.append(f"## {f['safe_name']}\n")
        for q in r.get("quotes", []):
            time_str = q.get("time", "00:00")
            text = q.get("text", "")[:60]
            lines.append(f"[{time_str}] {q.get('emoji','')} {text}")
            lines.append(f"  → Card: {q.get('affect','')} (intensity {q.get('intensity',5)}/10)")
            lines.append("")
    (export_dir / "capcut_script.txt").write_text("\n".join(lines), encoding="utf-8")


def _export_notion(completed, output_dir):
    """Notion-import-ready Markdown with database tables."""
    export_dir = output_dir / "notion"
    export_dir.mkdir(exist_ok=True)
    lines = ["# Audio Analysis Database\n"]
    lines.append("| File | Duration | Segments | Deception | Veracity | Clinical | Freezes |")
    lines.append("|------|----------|----------|-----------|----------|----------|---------|")
    for f in completed:
        r = f.get("result", {})
        lines.append(f"| {f['safe_name']} | {f['duration']//60}min | {r.get('segment_count',0)} | {r.get('deception_count',0)} | {r.get('veracity_count',0)} | {r.get('clinical_count',0)} | {r.get('freeze_count',0)} |")
    lines.append("\n## Detailed Notes\n")
    for f in completed:
        r = f.get("result", {})
        lines.append(f"### {f['safe_name']}\n")
        for q in r.get("quotes", [])[:3]:
            lines.append(f"- {q.get('emoji','')} [{q.get('intensity',5)}/10] {q.get('text','')}")
        lines.append("")
    (export_dir / "notion_import.md").write_text("\n".join(lines), encoding="utf-8")


# ─── Folder Watcher ───────────────────────────────────────────────────────────

def check_watch_dir():
    """Check watch directory for new .m4a files and add them to the queue."""
    if not STATE.watch_mode or not STATE.watch_dir:
        return
    audio_dir = Path(STATE.watch_dir)
    existing_paths = {f["path"] for f in STATE.files}
    for new_file in sorted(audio_dir.glob("*.m4a")):
        if str(new_file) not in existing_paths:
            dur = get_duration(new_file)
            safe = sanitize_filename(new_file.name)
            STATE.files.append({
                "path": str(new_file),
                "name": new_file.name,
                "stem": new_file.stem,
                "duration": dur,
                "size_mb": new_file.stat().st_size / 1048576,
                "model": "tiny" if dur < 300 else "base",
                "safe_name": safe,
                "tokens": dur // 60 * 112,
                "status": "pending",
                "pid": None,
                "start_time": None,
                "end_time": None,
                "output_dir": str(audio_dir / (new_file.stem + "_subfile")),
            })
            log_event("info", f"Watch: new file detected — {safe} ({dur//60}min)")


# ─── Main Loop ────────────────────────────────────────────────────────────────

def main():
    global STATE

    parser = argparse.ArgumentParser(
        description="Batch dashboard runner for Emotion Audio Analyser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dir", default=str(SCRIPT_DIR.parent / "test_audios" / "emotional_range_tests"),
                        help="Directory containing .m4a files")
    parser.add_argument("--parallel", type=int, default=3,
                        help="Max simultaneous processes (default 3)")
    parser.add_argument("--model", default="",
                        choices=["", "tiny", "base", "small", "medium", "large"],
                        help="Force a specific Whisper model")
    parser.add_argument("--fast", action="store_true", help="Quick draft profile")
    parser.add_argument("--full", action="store_true", help="Everything ON, small model")
    parser.add_argument("--stealth", action="store_true", help="Minimal output")
    parser.add_argument("--forensic", action="store_true", help="Deception + veracity + clinical")
    parser.add_argument("--no-facts", action="store_true", help="Disable facts (unused in dashboard)")
    parser.add_argument("--watch", action="store_true", help="Watch directory for new files")
    parser.add_argument("--auto-start", action="store_true", help="Start processing immediately (default: wait for Enter)")
    parser.add_argument("--export", default="", help="Auto-export on completion: wiki_md, obsidian, csv, json, html, sql, opml, excel, wordpress, substack, capcut, notion")
    args = parser.parse_args()

    # Apply profiles
    if args.fast:
        STATE.deception = False; STATE.veracity = False; STATE.clinical = False
        STATE.voice_dynamics = False; STATE.omni = False
    if args.full:
        args.model = "small"; STATE.viewer = True
    if args.stealth:
        STATE.omni = True
    if args.forensic:
        STATE.omni = False; STATE.voice_dynamics = False
        STATE.deception = True; STATE.veracity = True; STATE.clinical = True

    # Scan files
    print("Scanning files...")
    STATE.files = scan_files(args.dir)
    if not STATE.files:
        print(f"No .m4a files found in {args.dir}")
        sys.exit(1)

    # Apply forced model
    if args.model:
        for f in STATE.files:
            f["model"] = args.model

    # Apply fast profile model override
    if args.fast:
        for f in STATE.files:
            f["model"] = "tiny"

    STATE.total_duration = sum(f["duration"] for f in STATE.files)
    STATE.total_tokens = sum(f["tokens"] for f in STATE.files)

    STATE.max_parallel = args.parallel
    max_parallel = args.parallel
    STATE.watch_mode = args.watch
    STATE.watch_dir = args.dir
    STATE.auto_start = args.auto_start
    STATE.started = args.auto_start

    # Init terminal
    old_term = init_raw_terminal()
    sys.stdout.write(HIDE_CURSOR)

    def cleanup():
        sys.stdout.write(SHOW_CURSOR + CLEAR)
        sys.stdout.flush()
        restore_terminal(old_term)

    def signal_handler(sig, frame):
        cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        while True:
            # Check for completed processes
            check_running()

            # Check watch directory for new files
            if STATE.watch_mode:
                check_watch_dir()

            # Start new files only if started and under parallel limit and not quitting
            if STATE.started and not STATE.quit_requested:
                pending = [f for f in STATE.files if f["status"] == "pending"]
                while STATE.running < max_parallel and pending:
                    f = pending.pop(0)
                    start_file(f)
                    STATE.running += 1

            # Check for keypresses
            key = nonblocking_getchar()
            if key:
                handle_keypress(key)

            # Render dashboard
            render_dashboard()

            # Check if all done (only if we've started)
            if STATE.started:
                all_done = all(f["status"] in ("done", "failed") for f in STATE.files)
                if all_done or (STATE.quit_requested and STATE.running == 0):
                    # Auto-export if requested
                    if args.export:
                        export_second_brain(args.export.replace("_", " ").title())
                    # Auto-generate batch viewer if viewer toggle is ON
                    if STATE.viewer:
                        completed_files = [f for f in STATE.files if f["status"] == "done" and f.get("result")]
                        if completed_files:
                            export_second_brain("HTML")
                            log_event("info", "Batch viewer generated (viewer ON)")
                    # Final render
                    render_dashboard()
                    time.sleep(2)
                    break

            time.sleep(0.3)

    finally:
        cleanup()

    # Print final summary after dashboard cleanup
    elapsed = int(time.time() - STATE.start_time)
    el_m, el_s = divmod(elapsed, 60)

    print()
    print(f"  🏁 BATCH COMPLETE")
    print(f"  ────────────────────────────────")
    print(f"  ✅ Succeeded:  {STATE.completed} / {len(STATE.files)}")
    print(f"  ❌ Failed:     {STATE.failed}")
    print(f"  ⏱  Wall time:  {el_m}m {el_s}s")
    print(f"  🔢 Tokens:     ~{STATE.total_tokens}")
    print(f"  💰 Cost:       $0.00")
    print()
    print(f"  📂 Output: each file's _subfile/ folder contains omni.md, analysis.json, transcript.md")
    print()


if __name__ == "__main__":
    main()
