#!/usr/bin/env bash
# Mix a podcast episode: voice + intro music sting + outro music swell.
#
# v3 change: intro music CONTINUES under voice for a few seconds and fades to
# silence. Voice is clean through the body. Outro music swells back at end.
# That "mic-down" pattern matches normal podcast convention.
#
# Usage:
#   build_episode_mix.sh VOICE.wav MUSIC.wav OUT.wav
#
# Set MUSIC_OFF=1 to skip music entirely and just master the voice
# (useful when the host wants to mix music in post).

set -euo pipefail

VOICE="${1:?usage: $0 voice.wav music.wav out.wav}"
MUSIC="${2:?need music path (any length; we trim/loop as needed)}"
OUT="${3:?need output path}"

# Music-off mode: just master the voice.
if [[ "${MUSIC_OFF:-0}" == "1" ]]; then
    ffmpeg -y -i "$VOICE" \
        -filter_complex "[0:a]aresample=48000,aformat=channel_layouts=stereo,volume=1.2,loudnorm=I=-16:TP=-1.5:LRA=11[out]" \
        -map "[out]" -ac 2 -ar 48000 -c:a pcm_s16le "$OUT"
    echo "[build-episode-mix] MUSIC_OFF — voice-only master written: $OUT"
    exit 0
fi

INTRO_HOT_S="${INTRO_HOT_S:-3.5}"      # music plays alone before voice (full level)
INTRO_FADE_S="${INTRO_FADE_S:-4.0}"    # while voice runs, music continues then fades over this duration
OUTRO_S="${OUTRO_S:-7.0}"              # outro music swell duration
OUTRO_FADE_IN="${OUTRO_FADE_IN:-1.0}"
OUTRO_FADE_OUT="${OUTRO_FADE_OUT:-3.5}"
INTRO_HOT_GAIN="${INTRO_HOT_GAIN:-0.85}"
INTRO_DUCKED_GAIN="${INTRO_DUCKED_GAIN:-0.25}"  # quieter under-voice level
OUTRO_GAIN="${OUTRO_GAIN:-0.85}"
VOICE_GAIN="${VOICE_GAIN:-1.4}"        # +3 dB on voice

VOICE_DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$VOICE")
VOICE_END=$(awk -v v="$VOICE_DUR" -v i="$INTRO_HOT_S" 'BEGIN{printf "%.2f", v+i}')
TOTAL_DUR=$(awk -v ve="$VOICE_END" -v o="$OUTRO_S" 'BEGIN{printf "%.2f", ve+o}')

# Intro music: plays at full level for INTRO_HOT_S, voice begins, music continues
# at full for ~0.5s then ramps to ducked level over INTRO_FADE_S, then fades to silence.
INTRO_RAMP_END=$(awk -v i="$INTRO_HOT_S" -v f="$INTRO_FADE_S" 'BEGIN{printf "%.2f", i+f}')
INTRO_TOTAL_S=$(awk -v i="$INTRO_HOT_S" -v f="$INTRO_FADE_S" 'BEGIN{printf "%.2f", i+f+1.0}')

ffmpeg -y \
    -stream_loop -1 -i "$MUSIC" \
    -i "$VOICE" \
    -filter_complex "\
        [0:a]atrim=0:${INTRO_TOTAL_S},asetpts=PTS-STARTPTS,\
             aresample=48000,aformat=channel_layouts=stereo,\
             afade=t=in:st=0:d=0.4,\
             volume='if(lt(t,${INTRO_HOT_S}),${INTRO_HOT_GAIN},if(lt(t,${INTRO_RAMP_END}),${INTRO_HOT_GAIN}+(${INTRO_DUCKED_GAIN}-${INTRO_HOT_GAIN})*(t-${INTRO_HOT_S})/${INTRO_FADE_S},${INTRO_DUCKED_GAIN}))':eval=frame,\
             afade=t=out:st=${INTRO_RAMP_END}:d=1.0[intro_music];\
        [1:a]aresample=48000,aformat=channel_layouts=stereo,\
             volume=${VOICE_GAIN},\
             adelay=$(awk -v i="$INTRO_HOT_S" 'BEGIN{printf "%d", i*1000}')|$(awk -v i="$INTRO_HOT_S" 'BEGIN{printf "%d", i*1000}')[vo];\
        [0:a]atrim=${INTRO_TOTAL_S}:$(awk -v t="$INTRO_TOTAL_S" -v o="$OUTRO_S" 'BEGIN{printf "%.2f", t+o}'),\
             asetpts=PTS-STARTPTS,\
             aresample=48000,aformat=channel_layouts=stereo,\
             afade=t=in:st=0:d=${OUTRO_FADE_IN},\
             afade=t=out:st=$(awk -v o="$OUTRO_S" -v f="$OUTRO_FADE_OUT" 'BEGIN{printf "%.2f", o-f}'):d=${OUTRO_FADE_OUT},\
             volume=${OUTRO_GAIN},\
             adelay=$(awk -v ve="$VOICE_END" 'BEGIN{printf "%d", ve*1000}')|$(awk -v ve="$VOICE_END" 'BEGIN{printf "%d", ve*1000}')[outro_music];\
        [intro_music][vo][outro_music]amix=inputs=3:duration=longest:dropout_transition=0:normalize=0[mix];\
        [mix]loudnorm=I=-16:TP=-1.5:LRA=11[out]" \
    -map "[out]" \
    -ac 2 -ar 48000 -c:a pcm_s16le \
    "$OUT"

echo "[build-episode-mix] voice=${VOICE_DUR}s, intro_hot=${INTRO_HOT_S}s, intro_fade=${INTRO_FADE_S}s, outro=${OUTRO_S}s"
echo "[build-episode-mix] pattern: music hot -> voice in -> music fades under voice -> clean voice -> outro music swell"
echo "[build-episode-mix] wrote: $OUT"
