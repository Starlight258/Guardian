#!/usr/bin/env bash
# ─── Angel expressions ───────────────────────────────────────────────────────
# Edit this file to change angel moods.
# Color variables (PINK LAVENDER GOLD GRAY SKIN WHITE NC) come from angel-status.sh.
# NOW is already set by the time this is sourced.
#
# Template (normal art, 7 lines):
#
#         ʚɞ ⋆｡˚ ☁︎ ˚｡⋆
#       ˚₊‧꒰ა {HALO} ໒꒱ ‧₊˚
#            /)  /)
#         ૮({FACE})ა
#          ꒰ঌ {ITEM} ໒꒱
#             {FEET}
#          ☁︎ {DECO} ☁︎
#
# Blink art (every 8 s, 6 lines):
#
#           ʚɞ
#       ˚₊‧꒰ა 𓂋 ໒꒱ ‧₊˚
#         ૮(•ᴗ•)ა
#         ꒰ঌ ♡ ໒꒱
#             ╹╹
#            ☁︎
#
# Spacing notes:
#   Normal: lead spaces per line = 8 / 6 / 11 / 8* / 9 / 12* / 9
#   *face lead varies per mood; *feet lead varies per mood (happy +1)
#
# Note: each line starts with ${NC} (ANSI reset, zero visual width) so that
# Claude Code's statusLine renderer does not strip the leading spaces.
# ─────────────────────────────────────────────────────────────────────────────

BLINK=$(( NOW % 8 ))

if [ "$BLINK" -eq 0 ]; then
    # ── Blink (compact, eyes closed) ─────────────────────────────────────────
    ART=(
        "${NC}          ${PINK}ʚɞ${NC}"
        "${NC}      ${LAVENDER}˚₊‧꒰ა${NC} ${GOLD}𓂋${NC} ${LAVENDER}໒꒱ ‧₊˚${NC}"
        "${NC}        ${SKIN}૮(•ᴗ•)ა${NC}"
        "${NC}        ${LAVENDER}꒰ঌ${NC} ${PINK}♡${NC} ${LAVENDER}໒꒱${NC}"
        "${NC}            ${WHITE}╹╹${NC}"
        "${NC}           ${LAVENDER}☁︎${NC}"
    )
else
    # ── Mood-based art ────────────────────────────────────────────────────────
    case "$MOOD" in
        happy|excited)
            #  ʚɞ ⋆｡˚ ☁︎ ˚｡⋆
            #  ˚₊‧꒰ა ✧ ໒꒱ ‧₊˚
            #       /)  /)
            #   ૮(˶ᵔᗜᵔ˶)ﾉﾞა     ← 5-space lead (wide arm)
            #    ꒰ঌ ♡⃝ ໒꒱
            #             ╲╱    ← 13-space lead
            #    ☁︎ 𓍯 ☁︎
            HALO="${GOLD}✧${NC}"
            FACE_LINE="${NC}     ${SKIN}૮(${GOLD}˶ᵔᗜᵔ˶)ﾉﾞ${SKIN}ა${NC}"
            ITEM="${PINK}♡⃝${NC}"
            FEET="${NC}             ${WHITE}╲╱${NC}"
            DECO="${GOLD}𓍯${NC}"
            ;;
        tired)
            #  ʚɞ ⋆｡˚ ☁︎ ˚｡⋆
            #  ˚₊‧꒰ა ☾ ໒꒱ ‧₊˚
            #       /)  /)
            #   ૮( • ᴗ - )ა    ← 8-space lead, sleepy face
            #    ꒰ঌ ✧ ໒꒱
            #           ╲╱
            #    ☁︎ ♡ ☁︎
            HALO="${GRAY}☾${NC}"
            FACE_LINE="${NC}        ${SKIN}૮(${GRAY} • ᴗ - ${SKIN})ა${NC}"
            ITEM="${PINK}✧${NC}"
            FEET="${NC}            ${WHITE}╲╱${NC}"
            DECO="${GRAY}♡${NC}"
            ;;
        *)
            # focused / default
            #  ʚɞ ⋆｡˚ ☁︎ ˚｡⋆
            #  ˚₊‧꒰ა 𓂋 ໒꒱ ‧₊˚
            #       /)  /)
            #   ૮(˶• ֊ •˶)ა   ← 8-space lead
            #    ꒰ঌ ♡ ໒꒱
            #           ╲╱
            #    ☁︎ ⋆ ☁︎
            HALO="${GOLD}𓂋${NC}"
            FACE_LINE="${NC}        ${SKIN}૮(˶• ֊ •˶)ა${NC}"
            ITEM="${PINK}♡${NC}"
            FEET="${NC}            ${WHITE}╲╱${NC}"
            DECO="${LAVENDER}⋆${NC}"
            ;;
    esac

    ART=(
        "${NC}      ${LAVENDER}˚₊‧꒰ა${NC} ${HALO} ${LAVENDER}໒꒱ ‧₊˚${NC}"
        "${NC}           ${SKIN}/)  /)${NC}"
        "${FACE_LINE}"
        "${NC}         ${LAVENDER}꒰ঌ${NC} ${ITEM} ${LAVENDER}໒꒱${NC}"
        "${FEET}"
        "${NC}         ${LAVENDER}☁︎${NC} ${DECO} ${LAVENDER}☁︎${NC}"
    )
fi
