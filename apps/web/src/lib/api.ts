import { absoluteApiUrl } from "@/lib/utils";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";

export type EpisodeRef = {
  slug: string;
  title: string;
  has_script: boolean;
  status?: string | null;
  audio_count?: number;
  last_rendered_at?: string | null;
};

export type SeasonRef = {
  slug: string;
  title: string;
  episodes: EpisodeRef[];
};

export type ShowRef = {
  tenant?: string | null;
  slug: string;
  title: string;
  seasons: SeasonRef[];
};

export type ShowDefaults = {
  cast?: Record<string, string>;
  music_bed?: string;
  ddpm_steps?: number;
  cfg_scale?: number;
  target_minutes?: number;
  intro_hot_s?: number;
  intro_fade_s?: number;
  outro_s?: number;
  pronunciation_notes?: string;
};

export type ShowDetail = {
  tenant?: string | null;
  slug: string;
  title: string;
  path: string;
  defaults: ShowDefaults;
};

export type AudioFile = {
  filename: string;
  kind: "final" | "nomusic" | "voice" | "audio";
  size_bytes: number;
  modified_at: string;
  duration_s?: number | null;
  url: string;
};

export type ScriptSection = {
  id: string;
  number: string;
  index: number;
  title: string;
  line: number;
  header: string;
  markdown: string;
};

export type EpisodeState = {
  show: string;
  season: string;
  episode: string;
  path: string;
  script: string;
  metrics: {
    frontmatter?: Record<string, unknown>;
    word_count?: number;
    estimated_audio_minutes?: number;
    estimated_render_minutes?: number;
    sections?: ScriptSection[];
    speakers?: string[];
  };
  audio: AudioFile[];
  state: {
    renders?: unknown[];
    mixes?: unknown[];
    script_saves?: unknown[];
    updated_at?: string;
  };
  annotations: Annotation[];
};

export type Voice = {
  id: string;
  label: string;
  source?: string;
};

export type MusicBed = {
  filename: string;
  title: string;
  path: string;
  size_bytes: number;
  duration_s?: number | null;
};

export type RenderJob = {
  id: string;
  kind: string;
  show: string;
  season: string;
  episode: string;
  status: "queued" | "running" | "completed" | "failed" | string;
  params: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  returncode?: number | null;
  log: string[];
  output_files: string[];
  error?: string | null;
  eta_s?: number | null;
  progress_pct?: number;
};

export type Annotation = {
  id: string;
  timestamp: string;
  version: string;
  time_s: number;
  text: string;
  line?: number | null;
  section?: string | null;
};

export type ChatAgent = {
  id: string;
  label: string;
  description: string;
};

export type ChatMessage = {
  id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  agent?: string;
  timestamp?: string;
  source?: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

async function textRequest(path: string, init?: RequestInit): Promise<string> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.text();
}

export function listShows() {
  return request<ShowRef[]>("/shows");
}

export function getShow(show: string) {
  return request<ShowDetail>(`/shows/${show}`);
}

export function saveShowDefaults(show: string, defaults: ShowDefaults) {
  return request<{ ok: true } & ShowDetail>(`/shows/${show}/defaults`, {
    method: "PUT",
    body: JSON.stringify({ defaults }),
  });
}

export function getEpisode(show: string, season: string, episode: string) {
  return request<EpisodeState>(`/shows/${show}/seasons/${season}/episodes/${episode}`);
}

export function duplicateEpisode(
  show: string,
  season: string,
  episode: string,
  body: { new_slug: string; new_title: string; carry_body?: boolean },
) {
  return request<EpisodeState>(`/shows/${show}/seasons/${season}/episodes/${episode}/duplicate`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getSourceDoc(show: string, season: string) {
  return request<{ content: string | null; path: string | null }>(`/shows/${show}/seasons/${season}/source`);
}

export async function saveScript(show: string, season: string, episode: string, script: string) {
  return request<{ ok: true }>(`/shows/${show}/seasons/${season}/episodes/${episode}/script`, {
    method: "PUT",
    headers: { "Content-Type": "text/plain" },
    body: script,
  });
}

export function getNotes(show: string, season: string, episode: string) {
  return textRequest(`/shows/${show}/seasons/${season}/episodes/${episode}/notes`);
}

export function saveNotes(show: string, season: string, episode: string, notes: string) {
  return request<{ ok: true; bytes: number }>(`/shows/${show}/seasons/${season}/episodes/${episode}/notes`, {
    method: "PUT",
    headers: { "Content-Type": "text/plain" },
    body: notes,
  });
}

export function startRender(
  show: string,
  season: string,
  episode: string,
  body: { version: string; ddpm_steps: number; cfg_scale: number; sections: "all" | string[] },
) {
  return request<{ job_id: string; status: string }>(`/shows/${show}/seasons/${season}/episodes/${episode}/render`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getRenderJob(jobId: string) {
  return request<RenderJob>(`/render-jobs/${jobId}`);
}

export function listRenderJobs(params?: { status?: string; episode?: string; limit?: number }) {
  const query = new URLSearchParams();
  if (params?.status) {
    query.set("status", params.status);
  }
  if (params?.episode) {
    query.set("episode", params.episode);
  }
  if (params?.limit) {
    query.set("limit", String(params.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<RenderJob[]>(`/render-jobs${suffix}`);
}

export function cancelRenderJob(jobId: string) {
  return request<{ ok: true; job: RenderJob }>(`/render-jobs/${jobId}`, { method: "DELETE" });
}

export function listChatAgents() {
  return request<ChatAgent[]>("/chat/agents");
}

export function getChatHistory(show: string, season: string, episode: string) {
  return request<ChatMessage[]>(`/shows/${show}/seasons/${season}/episodes/${episode}/chat`);
}

export async function streamBrigadeChat(
  body: {
    agent: string;
    messages: ChatMessage[];
    episode_context?: Record<string, unknown> | null;
    stream?: boolean;
  },
  onDelta: (delta: string) => void,
) {
  const response = await fetch(`${API_BASE}/chat/brigade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, stream: true }),
  });
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let content = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const event of events) {
      const line = event
        .split("\n")
        .find((row) => row.startsWith("data:"))
        ?.replace(/^data:\s*/, "");
      if (!line) {
        continue;
      }
      const payload = JSON.parse(line) as { delta?: string; error?: string; detail?: string };
      if (payload.error) {
        throw new Error(payload.detail || payload.error);
      }
      if (payload.delta) {
        content += payload.delta;
        onDelta(payload.delta);
      }
    }
  }
  return content;
}

export function listVoices() {
  return request<Voice[]>("/voices");
}

export function listMusicBeds() {
  return request<MusicBed[]>("/music-beds");
}

export function mixEpisode(
  show: string,
  season: string,
  episode: string,
  body: {
    voice_wav: string;
    music_bed: string;
    mode: "music_under_voice" | "music_off";
    intro_hot_s: number;
    intro_fade_s: number;
    outro_s: number;
    master_lufs: number;
  },
) {
  return request<{ ok: true; wav: string; mp3: string; audio: AudioFile[]; log: string }>(
    `/shows/${show}/seasons/${season}/episodes/${episode}/mix`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function addAnnotation(
  show: string,
  season: string,
  episode: string,
  body: { version: string; time_s: number; text: string; line?: number | null; section?: string | null },
) {
  return request<Annotation>(`/shows/${show}/seasons/${season}/episodes/${episode}/annotations`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function cloneVoice(name: string, file: File) {
  const form = new FormData();
  form.append("name", name);
  form.append("file", file);
  return request<Voice>("/voices/clone", { method: "POST", body: form });
}

export function aiScriptEdit(body: { current_script: string; instruction: string; model: string }) {
  return request<{ ok?: boolean; error?: string | null; edited_script: string; diff: string; source: string }>(
    "/ai/script-edit",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function openAudioFile(show: string, season: string, episode: string, filename: string) {
  return request<{ ok: true; path: string }>(`/shows/${show}/seasons/${season}/episodes/${episode}/open`, {
    method: "POST",
    body: JSON.stringify({ filename }),
  });
}

export function audioUrl(file: AudioFile) {
  return absoluteApiUrl(file.url);
}
