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

# ─── Mood constants ───────────────────────────────────────────────────────────
MOOD_FOCUSED="focused"
MOOD_HAPPY="happy"
MOOD_EXCITED="excited"
MOOD_TIRED="tired"
MOOD_THINKING="thinking"
MOOD_DEFAULT="$MOOD_FOCUSED"
MOOD_DECAY_SECS=30

MUTED=$(jq -r '.muted // false' "$STATE" 2>/dev/null)
[ "$MUTED" = "true" ] && exit 0

MOOD=$(jq -r '.mood // "focused"' "$STATE" 2>/dev/null)
MOOD_TS=$(jq -r '.mood_ts // 0' "$STATE" 2>/dev/null)
MESSAGE=$(jq -r '.message // ""' "$STATE" 2>/dev/null)
MSG_TS=$(jq -r '.message_ts // 0' "$STATE" 2>/dev/null)
MSG_TTL=$(jq -r '.message_ttl // 60' "$STATE" 2>/dev/null)
SOURCE_FILE=$(jq -r '.source_file // ""' "$STATE" 2>/dev/null)
RECALL_COUNT=$(jq -r '.recall_count // 0' "$STATE" 2>/dev/null)
LAST_RECALL_TS=$(jq -r '.last_recall_ts // 0' "$STATE" 2>/dev/null)
GUARDIAN_ACTIVE=$(jq -r '.guardian_active // true' "$STATE" 2>/dev/null)

NOW=$(date +%s)

# ─── Mood decay: any transient mood → default after MOOD_DECAY_SECS ──────────
if [ "$MOOD" != "$MOOD_DEFAULT" ] && [ "$MOOD_TS" -gt 0 ] 2>/dev/null; then
    MOOD_AGE=$(( NOW - MOOD_TS ))
    [ "$MOOD_AGE" -gt "$MOOD_DECAY_SECS" ] && MOOD="$MOOD_DEFAULT"
fi

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

# Pad each art line to ART_W visible columns so the bubble box aligns correctly
# when art is on the left. Uses unicodedata.east_asian_width for accurate width.
PADDED_ART=()
while IFS= read -r _line; do
    PADDED_ART+=("$_line")
done < <(printf '%s\x01' "${ART[@]}" | python3 -c "
import sys, re, unicodedata
art_w = $ART_W
for L in sys.stdin.read().split('\x01'):
    if not L:
        continue
    clean = re.sub(r'\033\[[^m]*m', '', L)
    v = sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in clean)
    print(L + ' ' * max(0, art_w - v))
")

# ─── Message text lines ──────────────────────────────────────────────────────
TEXT_W=32

if [ "$MOOD" = "$MOOD_HAPPY" ] || [ "$MOOD" = "$MOOD_EXCITED" ]; then
    EMOTE="*happy to help! ♥*"
elif [ "$MOOD" = "$MOOD_TIRED" ]; then
    EMOTE="*a bit tired... zzz*"
else
    EMOTE="*focused and listening...*"
fi

TEXT_LINES=("$EMOTE")
TEXT_TYPES=("emote")

if [ "$SHOW_MSG" -eq 1 ]; then
    TEXT_LINES+=(""); TEXT_TYPES+=("blank")

    META=""
    if [ -n "$LAST_RECALL_STR" ]; then
        META="$LAST_RECALL_STR"
        [ -n "$SOURCE_FILE" ] && [ "$SOURCE_FILE" != "null" ] && META="${META} · ${SOURCE_FILE}"
    fi

    _PY_OUT=$(printf '%s\x01%s' "${MESSAGE}" "$META" | python3 -c "
import sys, unicodedata

def vcw(c):
    return 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1

def vwrap(s, w):
    lines = []
    while s:
        chunk, v = '', 0
        for c in s:
            cw = vcw(c)
            if v + cw > w: break
            chunk += c; v += cw
        if not chunk: break
        lines.append(chunk)
        s = s[len(chunk):]
    return lines

def vtrunc(s, w):
    chunk, v = '', 0
    for c in s:
        cw = vcw(c)
        if v + cw > w: break
        chunk += c; v += cw
    return chunk

W = $TEXT_W
parts = sys.stdin.read().split('\x01')
msg  = parts[0] if len(parts) > 0 else ''
meta = parts[1] if len(parts) > 1 else ''
for line in vwrap(msg, W):
    print('msg\t' + line)
if meta.strip():
    print('meta\t' + vtrunc(meta, W))
")
    while IFS=$'\t' read -r _type _tline; do
        TEXT_LINES+=("$_tline"); TEXT_TYPES+=("$_type")
    done <<< "$_PY_OUT"
fi

TEXT_COUNT=${#TEXT_LINES[@]}
ART_COUNT=${#ART[@]}

# ─── Terminal width & right-align ────────────────────────────────────────────
COLS=$(tput cols 2>/dev/null || echo "${COLUMNS:-120}")
GAP_W=3
MARGIN=2
CLAUDE_OFFSET=3   # Claude Code prepends 3 spaces of its own padding per line

TOTAL_W=$(( ART_W + GAP_W + TEXT_W ))
PAD=$(( COLS - TOTAL_W - MARGIN - CLAUDE_OFFSET ))
[ "$PAD" -lt 0 ] && PAD=0
SP=$(printf '%*s' "$PAD" '')

MAX_LINES=$(( TEXT_COUNT > ART_COUNT ? TEXT_COUNT : ART_COUNT ))

# ─── Render art + text ───────────────────────────────────────────────────────
for (( i=0; i<MAX_LINES; i++ )); do
    if [ $i -lt $ART_COUNT ]; then
        ART_COL="${PADDED_ART[$i]}"
    else
        ART_COL="$(printf '%*s' $ART_W '')"
    fi

    if [ $i -lt $TEXT_COUNT ]; then
        tline="${TEXT_LINES[$i]}"
        ttype="${TEXT_TYPES[$i]}"
        [ $i -eq 0 ] && GAP_STR=" ${CB}─${NC} " || GAP_STR="   "
        case "$ttype" in
            emote) printf '%s%s%s%s\n' "$SP" "$ART_COL" "$GAP_STR" "${PINK}${DIM}${tline}${NC}" ;;
            blank) printf '%s%s\n'     "$SP" "$ART_COL" ;;
            msg)   printf '%s%s%s%s\n' "$SP" "$ART_COL" "$GAP_STR" "${DIM}${tline}${NC}" ;;
            meta)  printf '%s%s%s%s\n' "$SP" "$ART_COL" "$GAP_STR" "${GRAY}${tline}${NC}" ;;
        esac
    else
        printf '%s%s\n' "$SP" "$ART_COL"
    fi
done

printf '\n'
exit 0
