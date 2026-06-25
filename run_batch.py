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

        # Card mode: 0=Emotional, 1=Technical
        self.card_mode = 0

        # Current file being displayed in middle-right
        self.current_display_idx = -1

        # Last completed file data
        self.last_result: dict = {}

        # Terminal dimensions
        self.term_rows = 40
        self.term_cols = 120

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
        return ["Emotional", "Technical"][self.card_mode]


STATE = BatchState()

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
    """Read a single key press without blocking. Returns None if no input."""
    try:
        import select
        if select.select([sys.stdin], [], [], 0.0)[0]:
            ch = sys.stdin.read(1)
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
    idx = STATE.files.index(file_entry)
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
                else:
                    f["status"] = "failed"
                    STATE.failed += 1
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

        if f["status"] == "running":
            # Estimate progress based on elapsed time vs estimated time
            est_time = max(1, f["duration"] * 0.3)  # rough: 30% of audio duration
            elapsed_f = time.time() - f["start_time"]
            file_pct = min(99, int(elapsed_f / est_time * 100))
            bar_w = 15
            filled_f = bar_w * file_pct // 100
            fbar = "█" * filled_f + "░" * (bar_w - filled_f)
            color = Y
            lines.append(move_cursor(row, 1))
            lines.append(f"  {color}{status_icon}{NC} {safe:<16} {dur_min:>4}min {color}{fbar}{NC} {file_pct:>2}%")
        elif f["status"] == "done":
            color = G
            lines.append(move_cursor(row, 1))
            lines.append(f"  {color}{status_icon}{NC} {safe:<16} {dur_min:>4}min {G}{'✓' * 15}{NC} 100%")
        elif f["status"] == "failed":
            color = R
            lines.append(move_cursor(row, 1))
            lines.append(f"  {color}{status_icon}{NC} {safe:<16} {dur_min:>4}min {R}{'✗' * 15}{NC} ERR")
        else:
            color = D
            lines.append(move_cursor(row, 1))
            lines.append(f"  {color}{status_icon}{NC} {safe:<16} {dur_min:>4}min {D}{'·' * 15}{NC} ---")

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

        else:
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

    # Menu items — two rows
    menu1 = (
        f"  {BD}[N]{NC} Names:{STATE.name_privacy_label()}  "
        f"{BD}[P]{NC} Nums:{STATE.num_privacy_label()}  "
        f"{BD}[F]{NC} Cards:{STATE.card_mode_label()}  "
        f"{BD}[D]{NC} Deception:{'✅' if STATE.deception else '❌'}  "
        f"{BD}[V]{NC} Veracity:{'✅' if STATE.veracity else '❌'}  "
        f"{BD}[J]{NC} Jefferson:{'✅' if STATE.jefferson else '❌'}"
    )
    menu2 = (
        f"  {BD}[C]{NC} Clinical:{'✅' if STATE.clinical else '❌'}  "
        f"{BD}[Q]{NC} Quit  "
        f"{D}│  Toggles affect next queued file{NC}"
    )

    lines.append(move_cursor(bottom_start + 1, 1))
    lines.append(CLEAR_LINE + menu1)
    lines.append(move_cursor(bottom_start + 2, 1))
    lines.append(CLEAR_LINE + menu2)

    # Flush all at once
    sys.stdout.write("".join(lines))
    sys.stdout.flush()

# ─── Keyboard Handler ─────────────────────────────────────────────────────────

def handle_keypress(key):
    """Handle a single keypress for live toggling."""
    key = key.lower()

    if key == 'n':
        STATE.name_privacy = (STATE.name_privacy + 1) % 3
    elif key == 'p':
        STATE.num_privacy = (STATE.num_privacy + 1) % 3
    elif key == 'f':
        STATE.card_mode = (STATE.card_mode + 1) % 2
    elif key == 'd':
        STATE.deception = not STATE.deception
    elif key == 'v':
        STATE.veracity = not STATE.veracity
    elif key == 'j':
        STATE.jefferson = not STATE.jefferson
    elif key == 'c':
        STATE.clinical = not STATE.clinical
    elif key == 'q':
        STATE.quit_requested = True

# ─── Main Loop ────────────────────────────────────────────────────────────────

def main():
    global STATE

    parser = argparse.ArgumentParser(
        description="Batch dashboard runner for Emotion Audio Analyser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dir", default=str(SCRIPT_DIR / "test audios" / "emotional_range_tests"),
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

    max_parallel = args.parallel

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

            # Start new files if under parallel limit and not quitting
            if not STATE.quit_requested:
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

            # Check if all done
            all_done = all(f["status"] in ("done", "failed") for f in STATE.files)
            if all_done or (STATE.quit_requested and STATE.running == 0):
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
