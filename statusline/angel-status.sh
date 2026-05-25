#!/usr/bin/env bash
# Guardian Angel — Claude Code status line
#
# Layout:
#   [memory card] --   ʚɞ  ⋆｡˚ ☁︎ ˚｡⋆
#                    ˚₊‧꒰ა {HALO} ໒꒱ ‧₊˚
#                         /)  /)
#                      ૮({FACE})ა
#                      ꒰ঌ {ITEM} ໒꒱
#                          {FEET}
#                       ☁︎ {DECO} ☁︎
#   [3-column status bar]
#
# State: ~/.guardian/angel-state.json

STATE="$HOME/.guardian/angel-state.json"
[ -f "$STATE" ] || exit 0

MUTED=$(jq -r '.muted // false' "$STATE" 2>/dev/null)
[ "$MUTED" = "true" ] && exit 0

MOOD=$(jq -r '.mood // "focused"' "$STATE" 2>/dev/null)
MESSAGE=$(jq -r '.message // ""' "$STATE" 2>/dev/null)
MSG_TS=$(jq -r '.message_ts // 0' "$STATE" 2>/dev/null)
MSG_TTL=$(jq -r '.message_ttl // 60' "$STATE" 2>/dev/null)
SOURCE_TITLE=$(jq -r '.source_title // ""' "$STATE" 2>/dev/null)
SOURCE_FILE=$(jq -r '.source_file // ""' "$STATE" 2>/dev/null)
RECALL_COUNT=$(jq -r '.recall_count // 0' "$STATE" 2>/dev/null)
LAST_RECALL_TS=$(jq -r '.last_recall_ts // 0' "$STATE" 2>/dev/null)
GUARDIAN_ACTIVE=$(jq -r '.guardian_active // true' "$STATE" 2>/dev/null)

NOW=$(date +%s)

# ─── Message freshness ───────────────────────────────────────────────────────
SHOW_CARD=0
if [ -n "$MESSAGE" ] && [ "$MESSAGE" != "null" ] && [ "$MESSAGE" != "" ]; then
    AGE=$(( NOW - MSG_TS ))
    [ "$AGE" -lt "$MSG_TTL" ] && SHOW_CARD=1
fi

# ─── "X min ago" ─────────────────────────────────────────────────────────────
LAST_RECALL_STR=""
if [ "$LAST_RECALL_TS" -gt 0 ] 2>/dev/null; then
    MINS=$(( (NOW - LAST_RECALL_TS) / 60 ))
    if [ "$MINS" -lt 1 ]; then
        LAST_RECALL_STR="just now"
    elif [ "$MINS" -lt 60 ]; then
        LAST_RECALL_STR="${MINS}m ago"
    else
        LAST_RECALL_STR="$(( MINS / 60 ))h ago"
    fi
fi

# ─── Colors ──────────────────────────────────────────────────────────────────
NC=$'\033[0m'
PURPLE=$'\033[38;2;180;140;255m'
GOLD=$'\033[38;2;255;210;80m'
PINK=$'\033[38;2;255;150;180m'
DIM=$'\033[2;3m'
GREEN=$'\033[38;2;100;220;120m'
GRAY=$'\033[38;2;130;130;150m'
CB=$'\033[38;2;120;100;200m'
SKIN=$'\033[38;2;255;220;185m'
WHITE=$'\033[38;2;235;235;245m'
LAVENDER=$'\033[38;2;200;170;255m'

# ─── Angel ASCII art ─────────────────────────────────────────────────────────
ART_W=26
# shellcheck source=angel-moods.sh
. "$(dirname "$0")/angel-moods.sh"

# ─── Memory card lines ────────────────────────────────────────────────────────
CARD_LINES=()
CARD_TYPES=()   # "border" | "header" | "text" | "meta"
CARD_W=46

if [ $SHOW_CARD -eq 1 ]; then
    if [ -n "$SOURCE_TITLE" ] && [ "$SOURCE_TITLE" != "null" ]; then
        TITLE="$SOURCE_TITLE"
    else
        TITLE="${MESSAGE:0:42}"
        [ ${#MESSAGE} -gt 42 ] && TITLE="${TITLE}..."
    fi

    FILL=$(printf '%*s' $(( CARD_W - 2 )) '' | tr ' ' '─')
    CARD_LINES+=("╭${FILL}╮");           CARD_TYPES+=("border")
    CARD_LINES+=("│ 🧠 related memory detected       │"); CARD_TYPES+=("header")
    CARD_LINES+=("├${FILL}┤");           CARD_TYPES+=("border")

    INNER=$(( CARD_W - 4 ))
    T="${TITLE:0:$INNER}"
    TPAD=$(( INNER - ${#T} ))
    [ "$TPAD" -lt 0 ] && TPAD=0
    CARD_LINES+=("│  ${T}$(printf '%*s' $TPAD '')  │"); CARD_TYPES+=("text")

    if [ -n "$SOURCE_FILE" ] && [ "$SOURCE_FILE" != "null" ] && [ -n "$LAST_RECALL_STR" ]; then
        META="${LAST_RECALL_STR} · ${SOURCE_FILE}"
    elif [ -n "$LAST_RECALL_STR" ]; then
        META="$LAST_RECALL_STR"
    else
        META=""
    fi
    if [ -n "$META" ]; then
        M="${META:0:$INNER}"
        MPAD=$(( INNER - ${#M} ))
        [ "$MPAD" -lt 0 ] && MPAD=0
        CARD_LINES+=("│  ${M}$(printf '%*s' $MPAD '')  │"); CARD_TYPES+=("meta")
    fi

    CARD_LINES+=("╰${FILL}╯");           CARD_TYPES+=("border")
fi

CARD_COUNT=${#CARD_LINES[@]}
ART_COUNT=${#ART[@]}

# ─── Terminal width (status bar only — art uses internal spacing) ────────────
COLS=$(tput cols 2>/dev/null || echo "${COLUMNS:-120}")
GAP=2
SP=""

CARD_START=0
[ $CARD_COUNT -gt 0 ] && [ $CARD_COUNT -lt $ART_COUNT ] && \
    CARD_START=$(( (ART_COUNT - CARD_COUNT) / 2 ))

CONNECTOR_CI=-1
[ $CARD_COUNT -gt 2 ] && CONNECTOR_CI=$(( (1 + CARD_COUNT - 2) / 2 ))

MAX_LINES=$(( ART_COUNT > (CARD_START + CARD_COUNT) ? ART_COUNT : (CARD_START + CARD_COUNT) ))

# ─── Render art + card ───────────────────────────────────────────────────────
for (( i=0; i<MAX_LINES; i++ )); do
    if [ $i -lt $ART_COUNT ]; then
        ART_COL="${ART[$i]}${NC}"
    else
        ART_COL=$(printf '%*s' "$ART_W" '')
    fi

    if [ $CARD_COUNT -gt 0 ]; then
        ci=$(( i - CARD_START ))
        if [ $ci -ge 0 ] && [ $ci -lt $CARD_COUNT ]; then
            cline="${CARD_LINES[$ci]}"
            ctype="${CARD_TYPES[$ci]}"
            [ $ci -eq $CONNECTOR_CI ] && GAP_STR="${CB}--${NC} " || GAP_STR="   "
            case "$ctype" in
                border)
                    echo "${SP}${CB}${cline}${NC}${GAP_STR}${ART_COL}" ;;
                header)
                    echo "${SP}${CB}│${NC}${GOLD} 🧠 ${NC}${PURPLE}related memory detected${NC}       ${CB}│${NC}${GAP_STR}${ART_COL}" ;;
                text)
                    inner="${cline:1:$(( ${#cline} - 2 ))}"
                    echo "${SP}${CB}│${NC}${DIM}${inner}${NC}${CB}│${NC}${GAP_STR}${ART_COL}" ;;
                meta)
                    inner="${cline:1:$(( ${#cline} - 2 ))}"
                    echo "${SP}${CB}│${NC}${GRAY}${inner}${NC}${CB}│${NC}${GAP_STR}${ART_COL}" ;;
            esac
        else
            echo "${SP}$(printf '%*s' "$CARD_W" '')   ${ART_COL}"
        fi
    else
        echo "${SP}${ART_COL}"
    fi
done

echo ""

# ─── 3-column status bar ─────────────────────────────────────────────────────
_vis_len() { printf '%s' "$1" | sed 's/\x1b\[[0-9;:]*[mK]//g' | wc -m | tr -d ' '; }

# Col 1
[ "$GUARDIAN_ACTIVE" = "true" ] && \
    COL1_L1="${GREEN}□${NC} ${PURPLE}Guardian is listening...${NC} ${GOLD}✨${NC}" || \
    COL1_L1="${GRAY}□ Guardian offline${NC}"
COL1_L2="  ${DIM}Capture → Connect → Recall${NC}"

# Col 2
if [ "$RECALL_COUNT" -gt 0 ] 2>/dev/null; then
    [ "$RECALL_COUNT" -eq 1 ] && MEM_WORD="memory" || MEM_WORD="memories"
    COL2_L1="${GRAY}◈${NC} ${PURPLE}${RECALL_COUNT} related ${MEM_WORD} found${NC}"
    COL2_L2="${DIM}  last recall: ${LAST_RECALL_STR}${NC}"
else
    COL2_L1="${GRAY}◈ no recalls yet${NC}"
    COL2_L2=""
fi

# Col 3
case "$MOOD" in
    happy)   EXTRA="${GOLD}✨${NC}" ;;
    excited) EXTRA="${GOLD}✨${NC} ${PINK}🩷${NC}" ;;
    tired)   EXTRA="${GRAY}·${NC}" ;;
    *)       EXTRA="${PINK}🩷${NC}" ;;
esac
COL3_L1="${GREEN}●${NC} ${PURPLE}Angel: ON${NC}  👼 ${EXTRA}"

COL_W=$(( COLS / 3 ))

C1P=$(( COL_W - $(_vis_len "$COL1_L1") )); [ "$C1P" -lt 3 ] && C1P=3
C2P=$(( COL_W - $(_vis_len "$COL2_L1") )); [ "$C2P" -lt 3 ] && C2P=3
printf '%s%*s%s%*s%s\n' "$COL1_L1" "$C1P" '' "$COL2_L1" "$C2P" '' "$COL3_L1"

C1L2P=$(( COL_W - $(_vis_len "$COL1_L2") )); [ "$C1L2P" -lt 3 ] && C1L2P=3
C2L2P=$(( COL_W - $(_vis_len "$COL2_L2") )); [ "$C2L2P" -lt 3 ] && C2L2P=3
printf '%s%*s%s\n' "$COL1_L2" "$C1L2P" '' "$COL2_L2"

exit 0
