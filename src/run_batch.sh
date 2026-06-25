#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
#  EMOTION AUDIO ANALYSER — BATCH RUNNER v3.0
#  Baked into the project. Toggle options like Hermes modes.
#
#  Usage:
#    ./run_batch.sh                          # Interactive (default profile)
#    ./run_batch.sh --fast                   # Quick draft (tiny model, no extras)
#    ./run_batch.sh --full                   # Everything ON, best model
#    ./run_batch.sh --stealth                # Minimal output, no facts, no viewer
#    ./run_batch.sh --forensic               # Deception + veracity + clinical, no omni
#    ./run_batch.sh --diarise-local          # Add local speaker clustering
#    ./run_batch.sh --help                   # Show all options
#
#  Toggle flags (combine freely):
#    --facts / --no-facts                    Fun facts during processing
#    --deception / --no-deception            Deception indicators
#    --veracity / --no-veracity              Truthfulness indicators
#    --jefferson / --no-jefferson            Jefferson paralinguistic markers
#    --clinical / --no-clinical              Clinical markers (PTSD/ASD/ADHD)
#    --voice-dynamics / --no-voice-dynamics  Voice dynamics (librosa)
#    --emotional / --no-emotional            Emotional analysis
#    --omni / --no-omni                      Omni single-file output
#    --viewer / --no-viewer                  HTML viewer
#    --parallel N                            Max simultaneous processes (default 3)
#    --model tiny|base|small|medium|large    Force a specific model
#    --auto-model                            Auto-select model by duration
#    --estimate-cost                         Print cost estimate
#    --dir PATH                              Custom audio directory
#
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TRANSCRIPT_SCRIPT="$SCRIPT_DIR/run_transcription.py"
DEFAULT_DIR="$SCRIPT_DIR/../test_audios/emotional_range_tests"

# ── Defaults (all ON, like Hermes auto-mode) ──────────────────────────────────
FACTS=1
DECEPTION=1
VERACITY=1
JEFFERSON=1
CLINICAL=1
VOICE_DYNAMICS=1
EMOTIONAL=1
OMNI=1
VIEWER=0
PARALLEL=3
MODEL=""
AUTO_MODEL=0
ESTIMATE_COST=0
DIR="$DEFAULT_DIR"
DIARISE_LOCAL=0
COPY_AUDIO=0

# ── Color codes ───────────────────────────────────────────────────────────────
R='\033[0;31m'    G='\033[0;32m'   Y='\033[1;33m'   B='\033[0;34m'
P='\033[0;35m'    C='\033[0;36m'   W='\033[1;37m'   D='\033[2m'
BD='\033[1m'      NC='\033[0m'

# ── Profile presets ───────────────────────────────────────────────────────────
apply_profile() {
    local profile="$1"
    case "$profile" in
        --fast)
            MODEL="tiny"; FACTS=0; OMNI=0; VIEWER=0
            DECEPTION=0; VERACITY=0; CLINICAL=0; VOICE_DYNAMICS=0
            ;;
        --full)
            MODEL="small"; FACTS=1; OMNI=1; VIEWER=1
            DECEPTION=1; VERACITY=1; CLINICAL=1; VOICE_DYNAMICS=1; EMOTIONAL=1
            ;;
        --stealth)
            FACTS=0; OMNI=1; VIEWER=0; MODEL="tiny"
            ;;
        --forensic)
            DECEPTION=1; VERACITY=1; CLINICAL=1; EMOTIONAL=1
            OMNI=0; VOICE_DYNAMICS=0; VIEWER=0; MODEL="base"
            ;;
    esac
}

# ── Parse arguments ───────────────────────────────────────────────────────────
SHOW_HELP=0
for arg in "$@"; do
    case "$arg" in
        --help|-h)              SHOW_HELP=1 ;;
        --fast|--full|--stealth|--forensic) apply_profile "$arg" ;;
        --facts)                FACTS=1 ;;
        --no-facts)             FACTS=0 ;;
        --deception)            DECEPTION=1 ;;
        --no-deception)         DECEPTION=0 ;;
        --veracity)             VERACITY=1 ;;
        --no-veracity)          VERACITY=0 ;;
        --jefferson)            JEFFERSON=1 ;;
        --no-jefferson)         JEFFERSON=0 ;;
        --clinical)             CLINICAL=1 ;;
        --no-clinical)          CLINICAL=0 ;;
        --voice-dynamics)       VOICE_DYNAMICS=1 ;;
        --no-voice-dynamics)    VOICE_DYNAMICS=0 ;;
        --emotional)            EMOTIONAL=1 ;;
        --no-emotional)         EMOTIONAL=0 ;;
        --omni)                 OMNI=1 ;;
        --no-omni)              OMNI=0 ;;
        --viewer)               VIEWER=1 ;;
        --no-viewer)            VIEWER=0 ;;
        --diarise-local)        DIARISE_LOCAL=1 ;;
        --copy-audio)           COPY_AUDIO=1 ;;
        --auto-model)           AUTO_MODEL=1 ;;
        --estimate-cost)        ESTIMATE_COST=1 ;;
        --parallel)             shift_next=1 ;;
        --model)                shift_next=2 ;;
        --dir)                  shift_next=3 ;;
        *)
            if [ "${shift_next:-0}" = "1" ]; then PARALLEL="$arg"; shift_next=0
            elif [ "${shift_next:-0}" = "2" ]; then MODEL="$arg"; shift_next=0
            elif [ "${shift_next:-0}" = "3" ]; then DIR="$arg"; shift_next=0
            fi
            ;;
    esac
done

if [ $SHOW_HELP -eq 1 ]; then
    echo ""
    echo -e "${BD}EMOTION AUDIO ANALYSER — BATCH RUNNER${NC}"
    echo ""
    echo -e "${BD}Usage:${NC} ./run_batch.sh [OPTIONS]"
    echo ""
    echo -e "${BD}Profiles (preset combinations):${NC}"
    echo -e "  ${C}--fast${NC}      Quick draft — tiny model, minimal extras"
    echo -e "  ${C}--full${NC}      Everything ON, small model, viewer included"
    echo -e "  ${C}--stealth${NC}   Minimal output, no facts, no viewer"
    echo -e "  ${C}--forensic${NC}  Deception + veracity + clinical, no omni"
    echo ""
    echo -e "${BD}Toggle flags (combine freely):${NC}"
    echo -e "  ${C}--facts${NC} / ${C}--no-facts${NC}                    Fun facts during processing (default: ON)"
    echo -e "  ${C}--deception${NC} / ${C}--no-deception${NC}            Deception indicators (default: ON)"
    echo -e "  ${C}--veracity${NC} / ${C}--no-veracity${NC}              Truthfulness indicators (default: ON)"
    echo -e "  ${C}--jefferson${NC} / ${C}--no-jefferson${NC}            Jefferson markers (default: ON)"
    echo -e "  ${C}--clinical${NC} / ${C}--no-clinical${NC}              Clinical markers (default: ON)"
    echo -e "  ${C}--voice-dynamics${NC} / ${C}--no-voice-dynamics${NC}  Voice dynamics (default: ON)"
    echo -e "  ${C}--emotional${NC} / ${C}--no-emotional${NC}            Emotional analysis (default: ON)"
    echo -e "  ${C}--omni${NC} / ${C}--no-omni${NC}                      Omni single-file output (default: ON)"
    echo -e "  ${C}--viewer${NC} / ${C}--no-viewer${NC}                  HTML viewer (default: OFF)"
    echo -e "  ${C}--diarise-local${NC}                                 Add local speaker clustering"
    echo -e "  ${C}--copy-audio${NC}                                   Copy audio into output folder"
    echo ""
    echo -e "${BD}Model control:${NC}"
    echo -e "  ${C}--model${NC} tiny|base|small|medium|large    Force a specific model"
    echo -e "  ${C}--auto-model${NC}                            Auto-select by duration"
    echo -e "  ${C}--estimate-cost${NC}                        Print cost estimate"
    echo -e "  ${C}--parallel${NC} N                           Max simultaneous (default 3)"
    echo -e "  ${C}--dir${NC} PATH                             Custom audio directory"
    echo ""
    echo -e "${BD}Examples:${NC}"
    echo -e "  ./run_batch.sh --fast                        # Quick draft of everything"
    echo -e "  ./run_batch.sh --full --parallel 2           # Full analysis, 2 at a time"
    echo -e "  ./run_batch.sh --forensic --no-clinical      # Deception + veracity only"
    echo -e "  ./run_batch.sh --no-deception --no-veracity  # Emotion + Jefferson only"
    echo -e "  ./run_batch.sh --stealth --parallel 4        # Fast, quiet, 4 parallel"
    echo ""
    exit 0
fi

# ── Build CLI flags for run_transcription.py ─────────────────────────────────
CLI_FLAGS=""
[ $DECEPTION -eq 0 ]     && CLI_FLAGS="$CLI_FLAGS --no-deception"
[ $VERACITY -eq 0 ]      && CLI_FLAGS="$CLI_FLAGS --no-veracity"
[ $JEFFERSON -eq 0 ]     && CLI_FLAGS="$CLI_FLAGS --no-jefferson"
[ $CLINICAL -eq 0 ]      && CLI_FLAGS="$CLI_FLAGS --no-clinical"
[ $VOICE_DYNAMICS -eq 0 ] && CLI_FLAGS="$CLI_FLAGS --no-voice-dynamics"
[ $EMOTIONAL -eq 0 ]     && CLI_FLAGS="$CLI_FLAGS --no-emotional"
[ $OMNI -eq 1 ]          && CLI_FLAGS="$CLI_FLAGS --omni"
[ $OMNI -eq 0 ]          && CLI_FLAGS="$CLI_FLAGS --no-omni"
[ $VIEWER -eq 1 ]        && CLI_FLAGS="$CLI_FLAGS" || CLI_FLAGS="$CLI_FLAGS --no-viewer"
[ $DIARISE_LOCAL -eq 1 ] && CLI_FLAGS="$CLI_FLAGS --diarise-local"
[ $COPY_AUDIO -eq 1 ]    && CLI_FLAGS="$CLI_FLAGS" || CLI_FLAGS="$CLI_FLAGS --no-copy-audio"
[ $AUTO_MODEL -eq 1 ]    && CLI_FLAGS="$CLI_FLAGS --auto-model"
[ $ESTIMATE_COST -eq 1 ] && CLI_FLAGS="$CLI_FLAGS --estimate-cost"

# ── Fun facts pool (no names, no NSFW, no specific personal numbers) ─────────
FACTS_POOL=(
"🎧 the human voice carries over 340 distinct emotional tones"
"🐋 whales sing in keys humans can't fully hear yet"
"🔍 liars statistically use more words than truth-tellers"
"⚡ Whisper on CPU runs roughly 5x real-time with the tiny model"
"📝 Jefferson transcription dates back to 1984 conversation analysis"
"🫀 a 10s+ silence between turns is clinically called a freeze response"
"🌊 RMS energy 1.8x above baseline = classified as raised voice"
"🦜 Echo was a nymph who could only repeat others — the original transcript"
"🎵 pitch variability under 20Hz std flags possible flat affect"
"🧠 genuine memories contain more sensory detail than fabricated ones"
"⏳ vocal fry became widespread in English after 2005"
"💬 the word 'um' appears in about 1 in 10 conversational turns"
"🔄 ADHD maze = tangential blocks where the speaker loops through topics"
"🏝 PTSD fragments show as repeated phrases and abandoned sentences"
" Whisper whispers register at roughly 10% of normal speaking volume"
"💡 CHAT pause notation (min:sec.ms) comes from CHILDES child-language research"
"👂 the ear distinguishes roughly 400,000 distinct sound textures"
"⚡ a freeze over 30s gets flagged as a possible dissociation event"
"📚 TEI is the international standard for encoding spoken text"
"🫀 cognitive load theory: complex sentences under pressure indicate strain"
"🎭 stage actors project at ~85dB, normal conversation is ~60dB"
"🔬 prosody analysis can detect emotional states with ~69% accuracy"
"🏗 the smallest Whisper model is 39MB, the largest is 2.9GB"
"🌈 every language has its own emotional prosody fingerprint"
)
FIDX=0

print_fact() {
    [ $FACTS -eq 1 ] || return
    echo "  💡 ${FACTS_POOL[$FIDX]}"
    FIDX=$(( (FIDX + 1) % ${#FACTS_POOL[@]} ))
}

# ── Sanitize filename for terminal display ────────────────────────────────────
sanitize() {
    echo "$1" | sed -E \
        -e 's/.*Voice Memo - [0-9-]+ [0-9 ]+ - //' \
        -e 's/—.*//' \
        -e 's/-.*//' \
        -e 's/[^A-Za-z0-9]/_/g' \
        -e 's/_+/_/g' \
    | head -c 22
}

# ── Filter output lines for privacy ──────────────────────────────────────────
filter_line() {
    sed -E \
        -e 's/Speaker_[0-9]+/Speaker_XX/g' \
        -e 's/[A-Z][a-z]+ ->/[REDACTED] ->/g' \
        -e 's/renamed to.*/renamed to [REDACTED]/g' \
        -e 's/→.*$/→ [REDACTED]/g' \
        -e 's/voice match:.*$/voice match: [REDACTED]/g'
}

# ── Status badge ──────────────────────────────────────────────────────────────
badge() {
    [ "$1" = "1" ] && echo -e "${G}ON${NC}" || echo -e "${D}OFF${NC}"
}

# ── Header ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${P}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${P}║  ${W}🎧 EMOTION AUDIO ANALYSER v3.0 — BATCH RUNNER${NC}            ${P}║${NC}"
echo -e "${P}║  ${W}📋 Omni  🔍 Jefferson  🧠 Deception  ✅ Veracity${NC}        ${P}║${NC}"
echo -e "${P}║  ${W}🎤 Voice Dynamics  🏥 Clinical  🪙 Token Min-Maxing${NC}   ${P}║${NC}"
echo -e "${P}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Print active configuration ────────────────────────────────────────────────
echo -e "${BD}⚙️  Active Configuration${NC}"
echo -e "  ─────────────────────────────────────────"
echo -e "  🧠 Deception:      $(badge $DECEPTION)    ✅ Veracity:       $(badge $VERACITY)"
echo -e "  📝 Jefferson:      $(badge $JEFFERSON)    🏥 Clinical:        $(badge $CLINICAL)"
echo -e "  🎤 Voice Dynamics: $(badge $VOICE_DYNAMICS)    😊 Emotional:      $(badge $EMOTIONAL)"
echo -e "  📋 Omni output:    $(badge $OMNI)    🌐 HTML Viewer:     $(badge $VIEWER)"
echo -e "  💡 Facts:           $(badge $FACTS)    🗣  Diarise Local:   $(badge $DIARISE_LOCAL)"
echo -e "  📦 Copy audio:      $(badge $COPY_AUDIO)    💰 Est. cost:       $(badge $ESTIMATE_COST)"
if [ -n "$MODEL" ]; then
    echo -e "  🤖 Model:           ${C}$MODEL (forced)${NC}"
elif [ $AUTO_MODEL -eq 1 ]; then
    echo -e "  🤖 Model:           ${C}auto (by duration)${NC}"
else
    echo -e "  🤖 Model:           ${C}auto (tiny<5min, base>5min)${NC}"
fi
echo -e "  ⚡ Max parallel:     ${W}$PARALLEL${NC}"
echo -e "  📁 Directory:       ${D}$DIR${NC}"
echo ""

# ── Scan files ────────────────────────────────────────────────────────────────
echo -e "${BD}🔍 Scanning files...${NC}"
echo ""

TOTAL_DUR=0
TOTAL_TOK=0
FILE_LIST=()

for f in "$DIR"/*.m4a; do
    [ -f "$f" ] || continue
    dur=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$f" 2>/dev/null | cut -d. -f1)
    [ -z "$dur" ] && dur=0
    tok=$(( dur / 60 * 112 ))
    mb=$(( $(stat -f%z "$f" 2>/dev/null || echo 0) / 1048576 ))
    TOTAL_DUR=$((TOTAL_DUR + dur))
    TOTAL_TOK=$((TOTAL_TOK + tok))

    if [ "$dur" -lt 300 ]; then tier="🟢S"; m="tiny"
    elif [ "$dur" -lt 1800 ]; then tier="🟡M"; m="base"
    else tier="🔴L"; m="base"
    fi

    safe=$(sanitize "$(basename "$f")")
    printf "  %s  %5smin  %6sMB  %-6s  ~%stok  %s\n" "$tier" "$((dur/60))" "$mb" "$m" "$tok" "$safe"
    FILE_LIST+=("$f|$dur|$m")
done

NFILES=${#FILE_LIST[@]}
echo ""
echo -e "${BD}📊 Batch Summary${NC}"
echo -e "  ─────────────────────────────────────────"
echo -e "  📁 Files:            ${W}$NFILES${NC}"
echo -e "  ⏱  Total audio:      ${W}$((TOTAL_DUR/3600))h $((TOTAL_DUR%3600/60))m${NC}"
echo -e "  🔢 Est. tokens:      ${C}~$TOTAL_TOK${NC}"
echo -e "    LLM engine:       ${W}OpenAI Whisper (local, offline)${NC}"
echo -e "   Provider:          ${W}Local (on-device, no API)${NC}"
echo -e "  💰 Cost:             ${G}\$0.00${NC}"
echo -e "  ⚡ Max parallel:      ${W}$PARALLEL${NC}"
echo -e "  🕓 Est. wall time:   ${C}~$((TOTAL_DUR/60*2/PARALLEL))min${NC}"
echo ""
echo -e "  ${D}🟢S=<5min(tiny)  🟡M=5-30min(base)  🔴L=30min+(base)${NC}"
echo -e "  ${D}🔒 All names + personal content filtered from terminal output${NC}"
echo ""

# ── Confirm ───────────────────────────────────────────────────────────────────
read -p "$(echo -e "  ${BD}${G}⏸  Press ENTER to start, or Ctrl+C to cancel...${NC}")" _
echo ""

echo -e "${P}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${P}  ${W}🚀 PROCESSING STARTED${NC}${NC}"
echo -e "${P}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# ── Process ───────────────────────────────────────────────────────────────────
START=$(date +%s)
DONE=0
FAIL=0
RUN=0
LAST_FACT=0

start_file() {
    local f="$1" dur="$2" model="$3"
    local tok=$((dur / 60 * 112))
    local safe=$(sanitize "$(basename "$f")")
    local idx=$((DONE + FAIL + RUN + 1))
    echo "  ▶ [$idx/$NFILES] 🚀 $safe  model:$model  ~${tok}tok  $((dur/60))min"
    (
        cd "$SCRIPT_DIR"
        local flags="$CLI_FLAGS"
        [ -z "$MODEL" ] && flags="$flags --model $model"
        [ -n "$MODEL" ] && flags="$flags --model $MODEL"
        python3 "$TRANSCRIPT_SCRIPT" "$f" $flags --output-dir "$DIR" 2>&1 \
            | filter_line \
            | grep -E '(✓|⚠️|✅|→|ERROR|Building|Writing|Scanning|Analyzing|Done)' \
            | while read -r line; do echo "      $line"; done
    ) &
    RUN=$((RUN + 1))
}

for entry in "${FILE_LIST[@]}"; do
    IFS='|' read -r f dur model <<< "$entry"

    while [ $RUN -ge $PARALLEL ]; do
        sleep 2
        for pid in $(jobs -p); do
            if ! kill -0 "$pid" 2>/dev/null; then
                wait "$pid" 2>/dev/null
                ex=$?
                RUN=$((RUN - 1))
                [ $ex -eq 0 ] && DONE=$((DONE + 1)) || FAIL=$((FAIL + 1))
            fi
        done
        el=$(( $(date +%s) - START ))
        pct=$(( (DONE + FAIL) * 100 / NFILES ))
        printf "\r  ✅%s  ❌%s  ⏳%s  📊%s%%  ⏱%dm%02ds   " \
            "$DONE" "$FAIL" "$RUN" "$pct" $((el/60)) $((el%60))
        if [ $FACTS -eq 1 ] && [ $((el - LAST_FACT)) -ge 20 ] && [ $RUN -gt 0 ]; then
            echo ""
            print_fact
            LAST_FACT=$el
        fi
    done

    start_file "$f" "$dur" "$model"
    sleep 1
done

echo ""
echo -e "  ${BD}⏳ Waiting for remaining $RUN processes...${NC}"

while [ $RUN -gt 0 ]; do
    sleep 2
    for pid in $(jobs -p); do
        if ! kill -0 "$pid" 2>/dev/null; then
            wait "$pid" 2>/dev/null
            ex=$?
            RUN=$((RUN - 1))
            [ $ex -eq 0 ] && DONE=$((DONE + 1)) || FAIL=$((FAIL + 1))
        fi
    done
    el=$(( $(date +%s) - START ))
    printf "\r  ✅%s  ❌%s  ⏳%s  ⏱%dm%02ds   " \
        "$DONE" "$FAIL" "$RUN" $((el/60)) $((el%60))
done

el=$(( $(date +%s) - START ))
echo ""
echo ""
echo -e "${P}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${P}  ${W}🏁 BATCH COMPLETE${NC}${NC}"
echo -e "${P}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BD}📊 Results${NC}"
echo -e "  ─────────────────────────────────────────"
echo -e "  ✅ Succeeded:       ${G}$DONE${NC} / $NFILES"
echo -e "  ❌ Failed:          ${R}$FAIL${NC}"
echo -e "  ⏱  Total wall time:  ${W}$((el/60))m $((el%60))s${NC}"
echo -e "  🕓 Total audio:      ${W}$((TOTAL_DUR/3600))h $((TOTAL_DUR%3600/60))m${NC}"
echo -e "  🔢 Total tokens:     ${C}~$TOTAL_TOK${NC}"
echo -e "    LLM engine:       ${W}OpenAI Whisper (local, offline)${NC}"
echo -e "   Provider:          ${W}Local (on-device)${NC}"
echo -e "  💰 Cost:             ${G}\$0.00${NC}"
echo -e "  ⚡ Max parallel:      ${W}$PARALLEL${NC}"
echo ""
echo -e "${BD}📁 Per-file breakdown${NC}"
echo -e "  ─────────────────────────────────────────"
for entry in "${FILE_LIST[@]}"; do
    IFS='|' read -r f dur model <<< "$entry"
    safe=$(sanitize "$(basename "$f")")
    stem=$(basename "$f" .m4a)
    out="$DIR/${stem}_subfile"
    if [ -f "$out/omni.md" ]; then st="${G}✅${NC}"
    elif [ -f "$out/transcript.md" ]; then st="${Y}⚠️${NC}"
    else st="${R}❌${NC}"; fi
    printf "  %b  %4smin  %s\n" "$st" "$((dur/60))" "$safe"
done
echo ""
echo -e "  ${D}📂 Output: each file's _subfile/ folder contains omni.md, analysis.json, transcript.md${NC}"
echo -e "  ${D}🔒 All names + personal content filtered from this terminal session${NC}"
echo ""
[ $FACTS -eq 1 ] && print_fact && echo ""
echo -e "  ${BD}${G}✅ Done. Check omni.md files for full analysis.${NC}"
echo ""
