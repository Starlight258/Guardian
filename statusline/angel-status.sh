#!/usr/bin/env bash
# Guardian Angel — Claude Code status line
#
# Layout (right-aligned):
#   [speech bubble]  —  [angel art]
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
SOURCE_FILE=$(jq -r '.source_file // ""' "$STATE" 2>/dev/null)
RECALL_COUNT=$(jq -r '.recall_count // 0' "$STATE" 2>/dev/null)
LAST_RECALL_TS=$(jq -r '.last_recall_ts // 0' "$STATE" 2>/dev/null)
GUARDIAN_ACTIVE=$(jq -r '.guardian_active // true' "$STATE" 2>/dev/null)

NOW=$(date +%s)

# ─── Message freshness ───────────────────────────────────────────────────────
SHOW_MSG=0
if [ -n "$MESSAGE" ] && [ "$MESSAGE" != "null" ] && [ "$MESSAGE" != "" ]; then
    AGE=$(( NOW - MSG_TS ))
    [ "$AGE" -lt "$MSG_TTL" ] && SHOW_MSG=1
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
ART_W=20
# shellcheck source=angel-moods.sh
. "$(dirname "$0")/angel-moods.sh"

# ─── Speech bubble (always shown) ────────────────────────────────────────────
BUBBLE_W=32
B_INNER=$(( BUBBLE_W - 4 ))   # usable text width: "│ {B_INNER chars} │"
B_FILL=$(printf '%*s' $(( BUBBLE_W - 2 )) '' | tr ' ' '─')

case "$MOOD" in
    happy|excited) EMOTE="*happy to help! ♥*" ;;
    tired)         EMOTE="*a bit tired... zzz*" ;;
    *)             EMOTE="*focused and listening...*" ;;
esac

BUBBLE_LINES=()
BUBBLE_TYPES=()   # border | emote | blank | msg | meta

BUBBLE_LINES+=("╭${B_FILL}╮"); BUBBLE_TYPES+=("border")

E="${EMOTE:0:$B_INNER}"
EPAD=$(( B_INNER - ${#E} )); [ "$EPAD" -lt 0 ] && EPAD=0
BUBBLE_LINES+=("│ ${E}$(printf '%*s' $EPAD '') │"); BUBBLE_TYPES+=("emote")

if [ "$SHOW_MSG" -eq 1 ]; then
    BUBBLE_LINES+=("│$(printf '%*s' $(( BUBBLE_W - 2 )) '')│"); BUBBLE_TYPES+=("blank")

    msg="${MESSAGE}"
    C1="${msg:0:$B_INNER}"
    C1PAD=$(( B_INNER - ${#C1} )); [ "$C1PAD" -lt 0 ] && C1PAD=0
    BUBBLE_LINES+=("│ ${C1}$(printf '%*s' $C1PAD '') │"); BUBBLE_TYPES+=("msg")

    if [ ${#msg} -gt $B_INNER ]; then
        C2="${msg:$B_INNER:$B_INNER}"
        C2PAD=$(( B_INNER - ${#C2} )); [ "$C2PAD" -lt 0 ] && C2PAD=0
        BUBBLE_LINES+=("│ ${C2}$(printf '%*s' $C2PAD '') │"); BUBBLE_TYPES+=("msg")
    fi

    if [ -n "$LAST_RECALL_STR" ]; then
        META="$LAST_RECALL_STR"
        [ -n "$SOURCE_FILE" ] && [ "$SOURCE_FILE" != "null" ] && META="${META} · ${SOURCE_FILE}"
        M="${META:0:$B_INNER}"
        MPAD=$(( B_INNER - ${#M} )); [ "$MPAD" -lt 0 ] && MPAD=0
        BUBBLE_LINES+=("│ ${M}$(printf '%*s' $MPAD '') │"); BUBBLE_TYPES+=("meta")
    fi
fi

# Pad bubble with blank lines inside the box to match ART height
ART_COUNT=${#ART[@]}
CORE_COUNT=$(( ${#BUBBLE_LINES[@]} + 1 ))   # +1 for closing border
PAD_NEEDED=$(( ART_COUNT - CORE_COUNT ))
if [ "$PAD_NEEDED" -gt 0 ]; then
    BLANK_LINE="│$(printf '%*s' $(( BUBBLE_W - 2 )) '')│"
    for (( _p=0; _p<PAD_NEEDED; _p++ )); do
        BUBBLE_LINES+=("$BLANK_LINE"); BUBBLE_TYPES+=("blank")
    done
fi
BUBBLE_LINES+=("╰${B_FILL}╯"); BUBBLE_TYPES+=("border")

BUBBLE_COUNT=${#BUBBLE_LINES[@]}

# ─── Terminal width & right-align ────────────────────────────────────────────
COLS=$(tput cols 2>/dev/null || echo "${COLUMNS:-120}")
GAP_W=3           # " — " or "   "
MARGIN=2
CLAUDE_OFFSET=3   # Claude Code prepends 3 spaces of its own padding per line

TOTAL_W=$(( BUBBLE_W + GAP_W + ART_W ))
PAD=$(( COLS - TOTAL_W - MARGIN - CLAUDE_OFFSET ))
[ "$PAD" -lt 0 ] && PAD=0
SP=$(printf '%*s' "$PAD" '')

ART_START=0
BUBBLE_START=0
MAX_LINES=$(( BUBBLE_COUNT > ART_COUNT ? BUBBLE_COUNT : ART_COUNT ))

CONNECTOR_BI=$(( BUBBLE_COUNT / 2 ))

# ─── Render bubble + art ─────────────────────────────────────────────────────
for (( i=0; i<MAX_LINES; i++ )); do
    ai=$(( i - ART_START ))
    if [ $ai -ge 0 ] && [ $ai -lt $ART_COUNT ]; then
        ART_COL="${ART[$ai]}${NC}"
    else
        ART_COL=""
    fi

    bi=$(( i - BUBBLE_START ))
    if [ $bi -ge 0 ] && [ $bi -lt $BUBBLE_COUNT ]; then
        bline="${BUBBLE_LINES[$bi]}"
        btype="${BUBBLE_TYPES[$bi]}"
        [ $bi -eq $CONNECTOR_BI ] && GAP_STR=" ${CB}─${NC} " || GAP_STR="   "
        inner="${bline:1:$(( ${#bline} - 2 ))}"
        case "$btype" in
            border) printf '%s%s%s%s\n' "$SP" "${CB}${bline}${NC}"             "$GAP_STR" "$ART_COL" ;;
            emote)  printf '%s%s%s%s%s%s\n' "$SP" "${CB}│${NC}" "${PINK}${DIM}${inner}${NC}" "${CB}│${NC}" "$GAP_STR" "$ART_COL" ;;
            blank)  printf '%s%s%s%s\n' "$SP" "${CB}${bline}${NC}"             "$GAP_STR" "$ART_COL" ;;
            msg)    printf '%s%s%s%s%s%s\n' "$SP" "${CB}│${NC}" "${DIM}${inner}${NC}"       "${CB}│${NC}" "$GAP_STR" "$ART_COL" ;;
            meta)   printf '%s%s%s%s%s%s\n' "$SP" "${CB}│${NC}" "${GRAY}${inner}${NC}"      "${CB}│${NC}" "$GAP_STR" "$ART_COL" ;;
        esac
    else
        printf '%s%s%s%s\n' "$SP" "$(printf '%*s' $BUBBLE_W '')" "   " "$ART_COL"
    fi
done

printf '\n'
exit 0
