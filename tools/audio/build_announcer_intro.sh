#!/usr/bin/env bash
# Build a Layer-Above-style theatrical announcer intro.
#
# Mixes:
#   - music bed (full track, fades in/out, sidechain-ducked under voice)
#   - announcer voice (processed, delayed for music fanfare head)
#   - applause SFX (delayed to swell during announcer crescendo)
#
# Usage:
#   build_announcer_intro.sh ANNOUNCER.wav MUSIC.{flac,wav,mp3} APPLAUSE.wav OUT.wav
#
# Defaults are tuned for a ~30s total runtime mirroring the BIP cold-open.

set -euo pipefail

ANN="${1:?usage: $0 announcer.wav music.flac applause.wav out.wav}"
MUSIC="${2:?need music bed path}"
APPLAUSE="${3:?need applause sfx path}"
OUT="${4:?need output path}"

VO_DELAY_MS="${VO_DELAY_MS:-1800}"      # music fanfare head before announcer enters
VO_DELAY_S="${VO_DELAY_S:-1.8}"
VO_END_S="${VO_END_S:-26.5}"            # when the announcer typically wraps
APP_DELAY_MS="${APP_DELAY_MS:-25500}"   # applause swell starts late in the VO
MUSIC_LEN_S="${MUSIC_LEN_S:-32}"        # total mix length
APP_GAIN="${APP_GAIN:-0.45}"            # applause level (~-7dB so it doesn't bury voice)
VO_GAIN="${VO_GAIN:-1.6}"               # +4dB boost on voice so it sits above music
MUSIC_BED_GAIN="${MUSIC_BED_GAIN:-0.12}" # music ducks to ~-18dB during VO
MUSIC_FADE_IN="${MUSIC_FADE_IN:-0.5}"
MUSIC_FADE_OUT_AT="${MUSIC_FADE_OUT_AT:-29.5}"
MUSIC_FADE_OUT_DUR="${MUSIC_FADE_OUT_DUR:-2.0}"

# Explicit volume schedule on the music:
#   t in [0, VO_DELAY_S]                : full volume (1.0)  — fanfare intro
#   t in [VO_DELAY_S, VO_END_S]         : duck to MUSIC_BED_GAIN (~-18dB)
#   t in [VO_END_S, MUSIC_FADE_OUT_AT]  : full volume again (1.0) — applause swell over music
#   then afade-out for the tail.
ffmpeg -y \
    -i "$MUSIC" \
    -i "$ANN" \
    -i "$APPLAUSE" \
    -filter_complex "\
        [0:a]atrim=0:${MUSIC_LEN_S},asetpts=PTS-STARTPTS,\
             aresample=48000,aformat=channel_layouts=stereo,\
             afade=t=in:st=0:d=${MUSIC_FADE_IN},\
             afade=t=out:st=${MUSIC_FADE_OUT_AT}:d=${MUSIC_FADE_OUT_DUR},\
             volume='if(between(t,${VO_DELAY_S},${VO_END_S}),${MUSIC_BED_GAIN},1.0)':eval=frame[music];\
        [1:a]aresample=48000,aformat=channel_layouts=stereo,\
             volume=${VO_GAIN},\
             adelay=${VO_DELAY_MS}|${VO_DELAY_MS}[vo];\
        [2:a]aresample=48000,aformat=channel_layouts=stereo,\
             adelay=${APP_DELAY_MS}|${APP_DELAY_MS},\
             volume=${APP_GAIN}[app];\
        [music][vo][app]amix=inputs=3:duration=first:dropout_transition=0:normalize=0[mix];\
        [mix]loudnorm=I=-14:TP=-1.0:LRA=10[out]" \
    -map "[out]" \
    -ac 2 -ar 48000 -c:a pcm_s16le \
    "$OUT"

echo "[build-announcer-intro] wrote: $OUT"
