import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatTime(seconds: number | null | undefined) {
  if (!seconds || Number.isNaN(seconds)) {
    return "0:00";
  }
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${minutes}:${secs}`;
}

export function absoluteApiUrl(path: string) {
  if (path.startsWith("http")) {
    return path;
  }
  return `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011"}${path}`;
}
