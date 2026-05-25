#!/usr/bin/env bash
# ─── Angel expressions ───────────────────────────────────────────────────────
# Edit this file to change angel moods.
# Color variables (PINK LAVENDER GOLD GRAY SKIN WHITE NC) come from angel-status.sh.
# NOW is already set by the time this is sourced.
#
# Template (6 lines):
#
#       ˚₊‧꒰ა {HALO} ໒꒱ ‧₊˚
#            /)  /)
#         ૮({FACE})ა
#          ꒰ঌ {ITEM} ໒꒱
#             {FEET}
#          ☁︎ {DECO} ☁︎
#
# Blink art (every 8 s, 6 lines):
#
#        ʚɞ
#    ˚₊‧꒰ა 𓂋 ໒꒱ ‧₊˚
#      ૮(•ᴗ•)ა
#      ꒰ঌ ♡ ໒꒱
#          ╹╹
#         ☁︎
#
# Spacing notes:
#   Claude Code statusLine adds 3 spaces of its own padding per line.
#   All internal leading space counts are (-3) from the visual template
#   so the final rendered output matches the template exactly.
#
#   Each line starts with ${NC} (ANSI reset, zero visual width) to prevent
#   Claude Code from stripping the leading spaces.
# ─────────────────────────────────────────────────────────────────────────────

BLINK=$(( NOW % 8 ))

# ── Mood-based art ────────────────────────────────────────────────────────
case "$MOOD" in
    happy|excited)
        #  ˚₊‧꒰ა ✧ ໒꒱ ‧₊˚
        #       /)  /)
        #  ૮(˶ᵔᗜᵔ˶)ﾉﾞა     ← 2-space lead (wide arm, -3 offset)
        #   ꒰ঌ ♡⃝ ໒꒱
        #          ╲╱       ← 10-space lead
        #   ☁︎ 𓍯 ☁︎
        HALO="${GOLD}✧${NC}"
        FACE_LINE="${NC}  ${SKIN}૮(${GOLD}˶ᵔᗜᵔ˶)ﾉﾞ${SKIN}ა${NC}"
        BLINK_LINE="${NC}  ${SKIN}૮(${GOLD}˶˘ᗜ˘˶)ﾉﾞ${SKIN}ა${NC}"
        ITEM="${PINK}♡⃝${NC}"
        FEET="${NC}          ${WHITE}╲╱${NC}"
        DECO="${GOLD}𓍯${NC}"
        ;;
    tired)
        #  ˚₊‧꒰ა ☾ ໒꒱ ‧₊˚
        #       /)  /)
        #   ૮( • ᴗ - )ა    ← 5-space lead
        #    ꒰ঌ ✧ ໒꒱
        #           ╲╱
        #    ☁︎ ♡ ☁︎
        HALO="${GRAY}☾${NC}"
        FACE_LINE="${NC}     ${SKIN}૮(${GRAY} • ᴗ - ${SKIN})ა${NC}"
        BLINK_LINE="${NC}     ${SKIN}૮(${GRAY} ˘ ᴗ ˘ ${SKIN})ა${NC}"
        ITEM="${PINK}✧${NC}"
        FEET="${NC}         ${WHITE}╲╱${NC}"
        DECO="${GRAY}♡${NC}"
        ;;
    *)
        # focused / default
        #  ˚₊‧꒰ა 𓂋 ໒꒱ ‧₊˚
        #       /)  /)
        #   ૮(˶• ֊ •˶)ა   ← 5-space lead
        #    ꒰ঌ ♡ ໒꒱
        #           ╲╱
        #    ☁︎ ⋆ ☁︎
        HALO="${GOLD}𓂋${NC}"
        FACE_LINE="${NC}     ${SKIN}૮(˶• ֊ •˶)ა${NC}"
        BLINK_LINE="${NC}     ${SKIN}૮(˶˘ ֊ ˘˶)ა${NC}"
        ITEM="${PINK}♡${NC}"
        FEET="${NC}         ${WHITE}╲╱${NC}"
        DECO="${LAVENDER}⋆${NC}"
        ;;
esac

[ "$BLINK" -lt 2 ] && FACE_LINE="$BLINK_LINE"

ART=(
    "${NC}   ${LAVENDER}˚₊‧꒰ა${NC} ${HALO} ${LAVENDER}໒꒱ ‧₊˚${NC}"
    "${NC}        ${SKIN}/)  /)${NC}"
    "${FACE_LINE}"
    "${NC}      ${LAVENDER}꒰ঌ${NC} ${ITEM} ${LAVENDER}໒꒱${NC}"
    "${FEET}"
    "${NC}      ${LAVENDER}☁︎${NC} ${DECO} ${LAVENDER}☁︎${NC}"
)
