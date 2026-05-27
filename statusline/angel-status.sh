#!/usr/bin/env bash
# Guardian Angel — Claude Code status line
#
# Layout:
#   [angel art]   ╭─────────────────────────────────────╮
#                 │ *emote*                              │
#                 │ message line 1                       │
#                 │ message line 2                       │
#                 ╰─────────────────────────────────────╯
#                 Xm ago · source_file.md
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

# ─── Emote text ──────────────────────────────────────────────────────────────
if [ "$MOOD" = "$MOOD_HAPPY" ] || [ "$MOOD" = "$MOOD_EXCITED" ]; then
    EMOTE="*happy to help! ♥*"
elif [ "$MOOD" = "$MOOD_TIRED" ]; then
    EMOTE="*a bit tired... zzz*"
else
    EMOTE="*focused and listening...*"
fi

EMOTE_W=$(printf '%s' "$EMOTE" | python3 -c "
import sys, unicodedata
s = sys.stdin.read()
def vcw(c):
    return 0 if unicodedata.combining(c) or unicodedata.category(c) == 'Cf' else (2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1)
print(sum(vcw(c) for c in s))
")

# ─── Angel ASCII art ─────────────────────────────────────────────────────────
# shellcheck source=angel-moods.sh
. "$(dirname "$0")/angel-moods.sh"

ART_W=$(printf '%s\x01' "${ART[@]}" | python3 -c "
import sys, re, unicodedata
lines = [L for L in sys.stdin.read().split('\x01') if L]
def vis_len(s):
    clean = re.sub(r'\033\[[^m]*m', '', s)
    def vcw(c):
        return 0 if unicodedata.combining(c) or unicodedata.category(c) == 'Cf' else (2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1)
    width = sum(vcw(c) for c in clean)
    if '☁︎' in clean and '⋆' in clean:
        width -= 1
    return max(0, width)
print(max([vis_len(L) for L in lines] or [0]))
")

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
    def vcw(c):
        return 0 if unicodedata.combining(c) or unicodedata.category(c) == 'Cf' else (2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1)
    v = sum(vcw(c) for c in clean)
    if '☁︎' in clean and '⋆' in clean:
        v -= 1
    print(L + ' ' * max(0, art_w - v))
")

ART_COUNT=${#ART[@]}

# ─── Terminal size & bubble inner width ──────────────────────────────────────
COLS=$(tput cols 2>/dev/null || echo "${COLUMNS:-120}")
GAP_W=3
MARGIN=8
CLAUDE_OFFSET=3   # Claude Code prepends 3 spaces of its own padding per line

TEXT_W_MAX=26
TEXT_W_MIN=20
SAFE_MARGIN=12
AVAIL=$(( COLS - ART_W - GAP_W - MARGIN - CLAUDE_OFFSET - SAFE_MARGIN ))  # keep extra slack for Claude's own padding/clipping
[ "$AVAIL" -lt 20 ] && AVAIL=20
TEXT_W=$EMOTE_W
MSG_TEXT=""
if [ "$SHOW_MSG" -eq 1 ]; then
    MSG_TEXT=$(printf '%s' "$MESSAGE" | python3 -c "
import sys, re
s = sys.stdin.read().replace('\r', ' ')
s = re.sub(r'[\r\n\t]+', ' ', s)
s = re.sub(r'\s+', ' ', s).strip()
print(s)
")
fi
[ "$TEXT_W" -lt "$TEXT_W_MIN" ] && TEXT_W=$TEXT_W_MIN
[ "$TEXT_W" -gt "$TEXT_W_MAX" ] && TEXT_W=$TEXT_W_MAX
[ "$TEXT_W" -gt "$AVAIL" ] && TEXT_W=$AVAIL

# ─── Message & meta ──────────────────────────────────────────────────────────
META=""
if [ "$SHOW_MSG" -eq 1 ]; then
    if [ -n "$LAST_RECALL_STR" ]; then
        META="$LAST_RECALL_STR"
        [ -n "$SOURCE_FILE" ] && [ "$SOURCE_FILE" != "null" ] && META="${META} · ${SOURCE_FILE}"
    fi
fi

BUBBLE_LINES=()
BUBBLE_TYPES=()
META_LINE=""

_PY_OUT=$(printf '%s\x01%s\x01%s' "$EMOTE" "$MSG_TEXT" "$META" | python3 -c "
import re
import sys, unicodedata

def vcw(c):
    return 0 if unicodedata.combining(c) or unicodedata.category(c) == 'Cf' else (2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1)
def vis_len(s):
    return sum(vcw(c) for c in s)
def vtrunc(s, w):
    out, v = '', 0
    for c in s:
        cw = vcw(c)
        if v + cw > w: break
        out += c; v += cw
    return out
def vpad(s, w):
    return s + ' ' * max(0, w - vis_len(s))
def vwrap(s, w):
    words = [word for word in re.split(r'\s+', s.strip()) if word]
    lines, cur, cv = [], '', 0
    for word in words:
        wv = vis_len(word)
        if wv > w:
            word = vtrunc(word, w); wv = vis_len(word)
        if cur and cv + 1 + wv > w:
            lines.append(cur); cur, cv = word, wv
        else:
            cur = (cur + ' ' + word).lstrip() if cur else word
            cv = cv + (1 if cur != word else 0) + wv
    if cur: lines.append(cur)
    return lines

W = $TEXT_W
raw = sys.stdin.read().split('\x01')
emote = raw[0] if len(raw) > 0 else ''
msg   = raw[1] if len(raw) > 1 else ''
meta  = raw[2] if len(raw) > 2 else ''

dashes = '─' * (W + 2)
print('top\t'   + dashes)
print('emote\t' + vpad(vtrunc(emote, W), W))
for line in (vwrap(msg, W) if msg.strip() else []):
    print('msg\t' + vpad(line, W))
print('bot\t'   + dashes)
if meta.strip():
    m = meta.strip()
    max_w = W + 2
    if vis_len(m) > max_w:
        m = vtrunc(m, max_w - 1) + '…'
    print('meta\t' + m)
")

while IFS=$'\t' read -r _type _content; do
    case "$_type" in
        top|emote|msg|bot) BUBBLE_LINES+=("$_content"); BUBBLE_TYPES+=("$_type") ;;
        meta) META_LINE="$_content" ;;
    esac
done <<< "$_PY_OUT"

BUBBLE_COUNT=${#BUBBLE_LINES[@]}
MAX_LINES=$(( BUBBLE_COUNT > ART_COUNT ? BUBBLE_COUNT : ART_COUNT ))

# ─── Right-align ─────────────────────────────────────────────────────────────
# Bubble outer width = TEXT_W + 4  (╭ + space + content + space + ╮)
TOTAL_W=$(( ART_W + GAP_W + TEXT_W + 4 ))
PAD=$(( COLS - TOTAL_W - MARGIN - CLAUDE_OFFSET ))
[ "$PAD" -lt 0 ] && PAD=0
SP=$(printf '%*s' "$PAD" '')
GAP=$(printf '%*s' "$GAP_W" '')

# ─── Render art + bubble ─────────────────────────────────────────────────────
for (( i=0; i<MAX_LINES; i++ )); do
    # Art column — pad with spaces when art is shorter than bubble
    if [ $i -lt $ART_COUNT ]; then
        ART_COL="${PADDED_ART[$i]}"
    else
        ART_COL="${NC}$(printf '%*s' $ART_W '')"
    fi

    # Bubble column — omit when bubble is shorter than art
    if [ $i -lt $BUBBLE_COUNT ]; then
        btype="${BUBBLE_TYPES[$i]}"
        bcontent="${BUBBLE_LINES[$i]}"
        case "$btype" in
            top)   BCOL="${LAVENDER}╭${bcontent}╮${NC}" ;;
            bot)   BCOL="${LAVENDER}╰${bcontent}╯${NC}" ;;
            emote) BCOL="${LAVENDER}│${NC} ${PINK}${DIM}${bcontent}${NC} ${LAVENDER}│${NC}" ;;
            msg)   BCOL="${LAVENDER}│${NC} ${DIM}${bcontent}${NC} ${LAVENDER}│${NC}" ;;
        esac
        printf '%s%s%s%s\n' "$SP" "$ART_COL" "$GAP" "$BCOL"
    else
        printf '%s%s\n' "$SP" "$ART_COL"
    fi
done

# Meta line below bubble, aligned with bubble left border
if [ -n "$META_LINE" ]; then
    META_INDENT=$(printf '%*s' $(( ART_W + GAP_W )) '')
    printf '%s%s%s%s%s\n' "$SP" "$META_INDENT" "${GRAY}" "$META_LINE" "${NC}"
fi

printf '\n'
exit 0
