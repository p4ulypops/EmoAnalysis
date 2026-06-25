#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Emotion Audio MCP — install script
# Run once from the plugin directory: bash install.sh
# ──────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "═══════════════════════════════════════════════"
echo "  Emotion Audio MCP — installer"
echo "═══════════════════════════════════════════════"

# ── 1. Python check ──
if ! command -v python3 &>/dev/null; then
  echo "❌  Python 3 is required. Install from https://python.org"
  exit 1
fi
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✅  Python $PY_VERSION found"

# ── 2. ffmpeg check (required by librosa + whisper) ──
if ! command -v ffmpeg &>/dev/null; then
  echo ""
  echo "⚠️  ffmpeg not found — needed for audio processing."
  echo "   Install with:  brew install ffmpeg"
  echo "   (continuing install; ffmpeg needed before first use)"
  echo ""
fi

# ── 3. Virtual environment ──
if [ ! -d "$VENV_DIR" ]; then
  echo "📦  Creating virtual environment at $VENV_DIR ..."
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# ── 4. Core deps (fast path — skip heavy optional packages) ──
echo "📦  Installing core packages ..."
pip install --quiet --upgrade pip
pip install --quiet "mcp>=1.0.0" "openai>=1.30.0" "python-dotenv>=1.0.0" \
                    "librosa>=0.10.0" "soundfile>=0.12.0" "numpy>=1.24.0" \
                    "sounddevice>=0.4.6"

# ── 5. Optional: ElevenLabs ──
read -r -p "Install ElevenLabs STT support? (y/N): " ELABS
if [[ "$ELABS" =~ ^[Yy]$ ]]; then
  pip install --quiet "elevenlabs>=1.0.0"
  echo "✅  ElevenLabs installed"
fi

# ── 6. Optional: local Whisper (large download) ──
read -r -p "Install local Whisper (offline, ~1–5 GB models)? (y/N): " LWSP
if [[ "$LWSP" =~ ^[Yy]$ ]]; then
  pip install --quiet "openai-whisper>=20231117"
  echo "✅  Local Whisper installed"
fi

# ── 7. .env file ──
ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<'EOF'
# Emotion Audio MCP — API keys
# Fill in whichever engines you intend to use.

OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=...
EOF
  echo ""
  echo "📝  Created $ENV_FILE — add your API keys there."
fi

# ── 8. Claude Code MCP config snippet ──
SERVER_PATH="$SCRIPT_DIR/server.py"
PYTHON_PATH="$VENV_DIR/bin/python"

echo ""
echo "═══════════════════════════════════════════════"
echo "  Installation complete ✅"
echo "═══════════════════════════════════════════════"
echo ""
echo "Add this to your Claude Code / Cowork MCP config (~/.claude/mcp.json):"
echo ""
cat <<EOF
{
  "mcpServers": {
    "emotion-audio": {
      "command": "$PYTHON_PATH",
      "args": ["$SERVER_PATH"],
      "env": {
        "OPENAI_API_KEY": "\${OPENAI_API_KEY}",
        "ELEVENLABS_API_KEY": "\${ELEVENLABS_API_KEY}"
      }
    }
  }
}
EOF
echo ""
echo "Or run the server directly:  $PYTHON_PATH $SERVER_PATH"
echo ""
echo "Next: open Claude / Cowork, install the emotion-audio-analyser skill,"
echo "and say: 'Analyse this recording for emotional response'"
