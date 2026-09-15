"use client";

import { Pause, Play, Plus, RotateCcw } from "lucide-react";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import { formatTime } from "@/lib/utils";

type AudioPlayerProps = {
  title: string;
  src: string;
  duration?: number | null;
  onAnnotate?: (time: number) => void;
};

export type AudioPlayerHandle = {
  playFrom: (time: number) => void;
  playPause: () => void;
  seekBy: (seconds: number) => void;
  getTime: () => number;
};

export const AudioPlayer = forwardRef<AudioPlayerHandle, AudioPlayerProps>(function AudioPlayer(
  { title, src, duration, onAnnotate },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const wavesurferRef = useRef<WaveSurfer | null>(null);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [total, setTotal] = useState(duration ?? 0);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }
    setReady(false);
    setPlaying(false);
    const wave = WaveSurfer.create({
      container: containerRef.current,
      url: src,
      height: 62,
      barWidth: 2,
      barGap: 2,
      barRadius: 1,
      cursorColor: "#ffc875",
      progressColor: "#a36bff",
      waveColor: "#2a3144",
      normalize: true,
    });
    wavesurferRef.current = wave;
    wave.on("ready", () => {
      setReady(true);
      setTotal(wave.getDuration());
    });
    wave.on("play", () => setPlaying(true));
    wave.on("pause", () => setPlaying(false));
    wave.on("timeupdate", (current) => setTime(current));
    wave.on("interaction", (current) => setTime(current));
    return () => {
      wave.destroy();
      wavesurferRef.current = null;
    };
  }, [src]);

  useImperativeHandle(ref, () => ({
    playFrom: (targetTime: number) => {
      const wave = wavesurferRef.current;
      if (!wave) {
        return;
      }
      const waveDuration = wave.getDuration();
      if (waveDuration > 0) {
        wave.seekTo(Math.max(0, Math.min(targetTime / waveDuration, 0.999)));
      }
      wave.play().catch(() => undefined);
    },
    playPause: () => {
      wavesurferRef.current?.playPause();
    },
    seekBy: (seconds: number) => {
      const wave = wavesurferRef.current;
      if (!wave) {
        return;
      }
      const next = Math.max(0, Math.min(wave.getCurrentTime() + seconds, wave.getDuration() || 0));
      if (wave.getDuration() > 0) {
        wave.seekTo(next / wave.getDuration());
      }
      setTime(next);
    },
    getTime: () => wavesurferRef.current?.getCurrentTime() ?? time,
  }));

  return (
    <div className="border-y border-[var(--studio-border)] bg-[var(--studio-surface)] px-4 py-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-[var(--studio-text)]">{title}</div>
          <div className="text-xs text-[var(--studio-muted)]">
            {formatTime(time)} / {formatTime(total)}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            className="grid h-9 w-9 place-items-center rounded-md border border-[var(--studio-border)] bg-white/[0.04] text-[var(--studio-text)] transition hover:bg-white/[0.08] disabled:opacity-40"
            disabled={!ready}
            onClick={() => wavesurferRef.current?.playPause()}
            title={playing ? "Pause" : "Play"}
          >
            {playing ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <button
            type="button"
            className="grid h-9 w-9 place-items-center rounded-md border border-[var(--studio-border)] bg-white/[0.04] text-[var(--studio-text)] transition hover:bg-white/[0.08] disabled:opacity-40"
            disabled={!ready}
            onClick={() => {
              wavesurferRef.current?.seekTo(0);
              setTime(0);
            }}
            title="Restart"
          >
            <RotateCcw size={15} />
          </button>
          <button
            type="button"
            className="grid h-9 w-9 place-items-center rounded-md border border-[rgba(163,107,255,0.38)] bg-[rgba(163,107,255,0.10)] text-[var(--studio-purple)] transition hover:bg-[rgba(163,107,255,0.16)] disabled:opacity-40"
            disabled={!ready || !onAnnotate}
            onClick={() => onAnnotate?.(time)}
            title="Add annotation"
          >
            <Plus size={16} />
          </button>
        </div>
      </div>
      <div ref={containerRef} className="min-h-[62px]" />
    </div>
  );
});
