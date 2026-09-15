"use client";

import { Pause, Play } from "lucide-react";
import { useRef, useState } from "react";
import type { AudioFile } from "@/lib/api";
import { audioUrl } from "@/lib/api";
import { formatTime } from "@/lib/utils";

type ComparePlayerProps = {
  left?: AudioFile;
  right?: AudioFile;
};

export function ComparePlayer({ left, right }: ComparePlayerProps) {
  const leftRef = useRef<HTMLAudioElement | null>(null);
  const rightRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const duration = Math.max(left?.duration_s ?? 0, right?.duration_s ?? 0);

  function sync(timeValue: number) {
    setTime(timeValue);
    if (leftRef.current) {
      leftRef.current.currentTime = timeValue;
    }
    if (rightRef.current) {
      rightRef.current.currentTime = timeValue;
    }
  }

  async function toggle() {
    const players = [leftRef.current, rightRef.current].filter(Boolean) as HTMLAudioElement[];
    if (playing) {
      players.forEach((player) => player.pause());
      setPlaying(false);
      return;
    }
    sync(time);
    await Promise.allSettled(players.map((player) => player.play()));
    setPlaying(true);
  }

  if (!left || !right) {
    return <div className="px-4 py-3 text-sm text-slate-500">Choose two rendered files to compare.</div>;
  }

  return (
    <div className="border-t border-white/10 bg-[#080c11] px-4 py-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="min-w-0 text-sm text-slate-300">
          Compare <span className="text-slate-100">{left.filename}</span> /{" "}
          <span className="text-slate-100">{right.filename}</span>
        </div>
        <button
          type="button"
          className="grid h-9 w-9 place-items-center border border-white/10 bg-white/[0.04] text-slate-100 transition hover:bg-white/[0.08]"
          onClick={toggle}
          title={playing ? "Pause comparison" : "Play comparison"}
        >
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
      </div>
      <input
        className="w-full accent-cyan-300"
        type="range"
        min={0}
        max={duration || 1}
        step={0.1}
        value={time}
        onChange={(event) => sync(Number(event.target.value))}
      />
      <div className="mt-1 flex justify-between text-xs text-slate-500">
        <span>{formatTime(time)}</span>
        <span>{formatTime(duration)}</span>
      </div>
      <audio ref={leftRef} src={audioUrl(left)} onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)} />
      <audio ref={rightRef} src={audioUrl(right)} />
    </div>
  );
}
