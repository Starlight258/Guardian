#!/usr/bin/env bash
# ─── Angel expressions ───────────────────────────────────────────────────────
# Edit this file to change angel moods.
# Color variables (PINK LAVENDER GOLD GRAY SKIN WHITE NC) come from angel-status.sh.
# NOW is already set by the time this is sourced.
#
# Template (6 lines):
#
#       ˚₊‧꒰ა {HALO} ໒꒱‧₊˚
#            /)  /)
#         ૮({FACE})ა
#          ꒰ঌ {ITEM} ໒꒱
#             {FEET}
#          ☁︎ {DECO} ☁︎
#
# Blink art (every 8 s, 6 lines):
#
#        ʚɞ
#    ˚₊‧꒰ა 𓂋 ໒꒱‧₊˚
#      ૮(•ᴗ•)ა
#      ꒰ঌ ♡ ໒꒱
#         ╹╹
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
        #   ˚₊‧✧‧₊˚           ← 2-space lead
        #    /)  /)            ← 4-space lead
        #  ૮(˶ᵔᗜᵔ˶)ﾉﾞა       ← 2-space lead (wide arm)
        #   ꒰ঌ ♡ ໒꒱           ← 3-space lead
        #     ╲╱              ← 6-space lead
        #   ☁︎ ⋆ ☁︎            ← 3-space lead
        HALO_LINE="${NC}   ${LAVENDER}˚₊‧${GOLD}✧${LAVENDER}‧₊˚${NC}"
        EARS_LINE="${NC}    ${SKIN}/)  /)${NC}"
        FACE_LINE="${NC}  ${SKIN}૮(${GOLD}˶ᵔᗜᵔ˶)ﾉﾞ${SKIN}ა${NC}"
        BLINK_LINE="${NC}  ${SKIN}૮(${GOLD}˶˘ᗜ˘˶)ﾉﾞ${SKIN}ა${NC}"
        ITEM="${PINK}♡${NC}"; ITEM_LEAD="  "
        FEET="${NC}     ${WHITE}╲╱${NC}"
        DECO="${GOLD}⋆${NC}"; DECO_LEAD="    "
        ;;
    tired)
        #  ˚₊‧꒰ა ☾ ໒꒱‧₊˚
        #     /)  /)
        #   ૮( • ﹃ - )ა    ← 5-space lead
        #    ꒰ঌ ✧ ໒꒱
        #      ╲╱
        #    ☁︎ ♡ ☁︎
        HALO_LINE="${NC}    ${LAVENDER}˚₊‧꒰ა${NC} ${GRAY}☾${NC} ${LAVENDER}໒꒱‧₊˚${NC}"
        EARS_LINE="${NC}        ${SKIN}/)  /)${NC} ᶻ 𝗓 𐰁"
        FACE_LINE="${NC}     ${SKIN}૮(${GRAY} • ﹃ - ${SKIN})ა${NC}"
        BLINK_LINE="${NC}     ${SKIN}૮(${GRAY} ˘ ﹃ ˘ ${SKIN})ა${NC}"
        ITEM="${PINK}✧${NC}"; ITEM_LEAD="      "
        FEET="${NC}         ${WHITE}╲╱${NC}"
        DECO="${GRAY}♡${NC}"; DECO_LEAD="       "
        ;;
    *)
        # focused / default
        #  ˚₊‧꒰ა 𓂋 ໒꒱‧₊˚
        #     /)  /)
        #   ૮(˶• ֊ •˶)ა   ← 5-space lead
        #    ꒰ঌ ♡ ໒꒱
        #      ╲╱
        #    ☁︎ ⋆ ☁︎
        HALO_LINE="${NC}   ${LAVENDER}˚₊‧꒰ა${NC} ${GOLD}𓂋${NC} ${LAVENDER}໒꒱‧₊˚${NC}"
        EARS_LINE="${NC}        ${SKIN}/)  /)${NC}"
        FACE_LINE="${NC}     ${SKIN}૮(˶• ֊ •˶)ა${NC}"
        BLINK_LINE="${NC}     ${SKIN}૮(˶˘ ֊ ˘˶)ა${NC}"
        ITEM="${PINK}♡${NC}"; ITEM_LEAD="      "
        FEET="${NC}         ${WHITE}╲╱${NC}"
        DECO="${LAVENDER}⋆${NC}"; DECO_LEAD="      "
        ;;
esac

[ "$BLINK" -lt 2 ] && FACE_LINE="$BLINK_LINE"

ART=(
    "${HALO_LINE}"
    "${EARS_LINE}"
    "${FACE_LINE}"
    "${NC}${ITEM_LEAD}${LAVENDER}꒰ঌ${NC} ${ITEM} ${LAVENDER}໒꒱${NC}"
    "${FEET}"
    "${NC}${DECO_LEAD}${LAVENDER}☁︎${NC} ${DECO} ${LAVENDER}☁︎${NC}"
)
