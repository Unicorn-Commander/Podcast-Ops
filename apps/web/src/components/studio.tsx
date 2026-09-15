"use client";

import Editor, { type BeforeMount, type OnMount } from "@monaco-editor/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Bot,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Copy,
  FileText,
  FolderOpen,
  Headphones,
  Keyboard,
  MessageSquare,
  Mic2,
  Music2,
  PlayCircle,
  RotateCcw,
  Save,
  Search,
  Send,
  Settings,
  SlidersHorizontal,
  Trash2,
  Upload,
  Volume2,
  WandSparkles,
  X,
  type LucideIcon,
} from "lucide-react";
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AudioPlayer, type AudioPlayerHandle } from "@/components/audio-player";
import { ComparePlayer } from "@/components/compare-player";
import {
  API_BASE,
  addAnnotation,
  aiScriptEdit,
  audioUrl,
  cancelRenderJob,
  cloneVoice,
  duplicateEpisode,
  getEpisode,
  getRenderJob,
  getNotes,
  getChatHistory,
  getShow,
  getSourceDoc,
  listChatAgents,
  listRenderJobs,
  listMusicBeds,
  listShows,
  listVoices,
  mixEpisode,
  openAudioFile,
  saveNotes,
  saveShowDefaults,
  saveScript,
  startRender,
  streamBrigadeChat,
  type ChatMessage,
  type EpisodeRef,
  type RenderJob,
  type SeasonRef,
  type ShowDefaults,
  type ShowRef,
} from "@/lib/api";
import { nextVersion, parseCast, parseSections, replaceCastVoice, replaceSection, wordCount } from "@/lib/script";
import { cn, formatTime } from "@/lib/utils";

type Selection = {
  show: string;
  season: string;
  episode: string;
};

type AnnotationDraft = {
  time: number;
  version: string;
  file: string;
};

type AiTarget =
  | { kind: "section"; sectionId: string; text: string }
  | { kind: "selection"; start: number; end: number; text: string };

type PendingEdit = {
  target: AiTarget;
  edited: string;
  diff: string;
  source: string;
  error?: string | null;
};

type EpisodeContextMenu = {
  x: number;
  y: number;
  show: ShowRef;
  season: SeasonRef;
  episode: EpisodeRef;
};

type DuplicateDraft = {
  show: string;
  season: string;
  episode: string;
  newSlug: string;
  newTitle: string;
};

type RightRailTab = "voices" | "render" | "mix" | "jobs" | "chat";

type MonacoEditor = Parameters<OnMount>[0];
type MonacoInstance = Parameters<OnMount>[1];

const speakerPalette = ["teal", "amber", "fuchsia", "sky", "lime", "rose"];
const rightRailTabs: Array<{ id: RightRailTab; label: string; icon: LucideIcon }> = [
  { id: "voices", label: "Voices", icon: Mic2 },
  { id: "render", label: "Render", icon: SlidersHorizontal },
  { id: "mix", label: "Mix", icon: Music2 },
  { id: "jobs", label: "Jobs", icon: Clock },
  { id: "chat", label: "Chat", icon: MessageSquare },
];

function defaultSelection(shows: ShowRef[]): Selection | null {
  const preferredShow = shows.find((show) => show.slug === "a-layer-below") ?? shows[0];
  const preferredSeason =
    preferredShow?.seasons.find((season) => season.slug === "season-1-majiks") ?? preferredShow?.seasons[0];
  const preferredEpisode =
    preferredSeason?.episodes.find((episode) => episode.slug === "ep01-creative-ai-suite") ??
    preferredSeason?.episodes[0];
  if (!preferredShow || !preferredSeason || !preferredEpisode) {
    return null;
  }
  return { show: preferredShow.slug, season: preferredSeason.slug, episode: preferredEpisode.slug };
}

function isSelected(selection: Selection | null, show: ShowRef, season: SeasonRef, episode: EpisodeRef) {
  return (
    selection?.show === show.slug && selection?.season === season.slug && selection?.episode === episode.slug
  );
}

function selectStyle() {
  return "h-9 min-w-0 rounded-md border border-[var(--studio-border)] bg-[var(--studio-input)] px-2 text-sm text-[var(--studio-text)] outline-none transition focus:border-[var(--studio-purple)] focus:ring-2 focus:ring-[rgba(163,107,255,0.22)]";
}

function inputStyle() {
  return "h-9 min-w-0 border border-[var(--studio-border)] bg-[var(--studio-input)] px-2 text-sm text-[var(--studio-text)] outline-none transition placeholder:text-[var(--studio-muted)] focus:border-[var(--studio-purple)] focus:ring-2 focus:ring-[rgba(163,107,255,0.22)]";
}

function modalShellStyle() {
  return "fixed inset-0 z-50 grid place-items-center bg-black/65 px-4";
}

function panelStyle() {
  return "studio-panel w-full max-w-xl p-4 shadow-2xl";
}

function shortcutLabel(key: string) {
  return `${typeof navigator !== "undefined" && navigator.platform.includes("Mac") ? "⌘" : "Ctrl+"}${key}`;
}

function renderJobVersion(job: RenderJob) {
  const version = job.params.version;
  return typeof version === "string" ? version : "render";
}

function formatEta(seconds: number | null | undefined) {
  if (!seconds) {
    return "0:00";
  }
  return formatTime(seconds);
}

function relativeTime(iso: string | null | undefined) {
  if (!iso) {
    return "not rendered";
  }
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) {
    return "not rendered";
  }
  const diff = Date.now() - then;
  const minutes = Math.max(1, Math.round(diff / 60000));
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 48) {
    return `${hours}h ago`;
  }
  return `${Math.round(hours / 24)}d ago`;
}

function episodeStatus(episode: EpisodeRef, jobs: RenderJob[]) {
  if (jobs.some((job) => job.episode === episode.slug && ["queued", "running"].includes(job.status))) {
    return "rendering";
  }
  const raw = String(episode.status ?? "").toLowerCase();
  if (raw.includes("ready") || (episode.audio_count ?? 0) > 0) {
    return "ready";
  }
  return raw.includes("draft") ? "draft" : raw || "draft";
}

function statusBadgeClass(status: string) {
  if (status === "rendering") {
    return "bg-[rgba(251,191,36,0.16)] text-[var(--studio-gold)] animate-pulse";
  }
  if (status === "ready") {
    return "bg-[rgba(94,234,212,0.14)] text-[var(--studio-success)]";
  }
  return "bg-white/[0.06] text-[var(--studio-muted)]";
}

function iconButtonStyle(active = false) {
  return cn(
    "grid h-8 w-8 place-items-center rounded-md transition disabled:opacity-40",
    active
      ? "bg-[rgba(163,107,255,0.18)] text-[var(--studio-purple)]"
      : "text-[var(--studio-secondary)] hover:bg-white/[0.06] hover:text-[var(--studio-text)]",
  );
}

function primaryButtonStyle() {
  return "inline-flex h-9 items-center justify-center gap-2 rounded-md bg-[var(--studio-purple)] px-3 text-sm font-medium text-white shadow-[0_10px_30px_rgba(163,107,255,0.18)] transition hover:bg-[#9258f5] disabled:opacity-40";
}

function secondaryButtonStyle() {
  return "inline-flex h-9 items-center justify-center gap-2 rounded-md border border-[rgba(163,107,255,0.38)] px-3 text-sm font-medium text-[var(--studio-purple)] transition hover:bg-[rgba(163,107,255,0.10)] disabled:opacity-40";
}

function ghostButtonStyle() {
  return "inline-flex h-9 items-center justify-center gap-2 rounded-md px-3 text-sm text-[var(--studio-secondary)] transition hover:bg-white/[0.06] hover:text-[var(--studio-text)] disabled:opacity-40";
}

function renderEstimate(wordsValue: number, ddpm: number) {
  const minutes = Math.max(wordsValue / 165, 0.2);
  return Math.max(20, Math.round(minutes * 60 * 1.35 * (ddpm / 50)));
}

function defaultsWithFallback(defaults?: ShowDefaults): Required<ShowDefaults> {
  return {
    cast: defaults?.cast ?? { aria: "alice", beck: "carter" },
    music_bed: defaults?.music_bed ?? "",
    ddpm_steps: defaults?.ddpm_steps ?? 50,
    cfg_scale: defaults?.cfg_scale ?? 1.3,
    target_minutes: defaults?.target_minutes ?? 9,
    intro_hot_s: defaults?.intro_hot_s ?? 3.5,
    intro_fade_s: defaults?.intro_fade_s ?? 4,
    outro_s: defaults?.outro_s ?? 7,
    pronunciation_notes: defaults?.pronunciation_notes ?? "",
  };
}

function InlineMarkdown({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return (
    <>
      {parts.map((part, index) => {
        if (/^\*\*[^*]+\*\*$/.test(part)) {
          return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
        }
        if (/^`[^`]+`$/.test(part)) {
          return (
            <code key={`${part}-${index}`} className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.9em] text-[var(--studio-gold)]">
              {part.slice(1, -1)}
            </code>
          );
        }
        return <span key={`${part}-${index}`}>{part}</span>;
      })}
    </>
  );
}

function MiniMarkdown({ content }: { content: string }) {
  const lines = content.split("\n");
  const nodes: ReactNode[] = [];
  let codeLines: string[] = [];
  let inCode = false;
  lines.forEach((line, index) => {
    if (/^```/.test(line)) {
      if (inCode) {
        nodes.push(
          <pre key={`code-${index}`} className="my-2 overflow-x-auto rounded-md border border-white/10 bg-black/25 p-2 font-mono text-xs leading-5 text-[var(--studio-secondary)]">
            {codeLines.join("\n")}
          </pre>,
        );
        codeLines = [];
      }
      inCode = !inCode;
      return;
    }
    if (inCode) {
      codeLines.push(line);
      return;
    }
    if (!line.trim()) {
      nodes.push(<div key={`space-${index}`} className="h-2" />);
      return;
    }
    if (/^#{1,3}\s+/.test(line)) {
      nodes.push(
        <div key={`heading-${index}`} className="pt-1 text-sm font-semibold text-[var(--studio-text)]">
          <InlineMarkdown text={line.replace(/^#{1,3}\s+/, "")} />
        </div>,
      );
      return;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      nodes.push(
        <div key={`bullet-${index}`} className="grid grid-cols-[14px_minmax(0,1fr)] gap-1">
          <span className="text-[var(--studio-purple)]">-</span>
          <span>
            <InlineMarkdown text={line.replace(/^\s*[-*]\s+/, "")} />
          </span>
        </div>,
      );
      return;
    }
    nodes.push(
      <p key={`p-${index}`}>
        <InlineMarkdown text={line} />
      </p>,
    );
  });
  return <div className="space-y-1">{nodes}</div>;
}

function HighlightedText({ text, query }: { text: string; query: string }) {
  const needle = query.trim();
  if (!needle) {
    return <>{text}</>;
  }
  const parts = text.split(new RegExp(`(${needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"));
  return (
    <>
      {parts.map((part, index) =>
        part.toLowerCase() === needle.toLowerCase() ? (
          <mark key={`${part}-${index}`} className="bg-amber-300/30 px-0.5 text-amber-50">
            {part}
          </mark>
        ) : (
          <span key={`${part}-${index}`}>{part}</span>
        ),
      )}
    </>
  );
}

function BriefMarkdown({ content, query }: { content: string | null | undefined; query: string }) {
  if (!content) {
    return (
      <div className="p-5">
        <div className="studio-empty">
          <FileText size={22} />
          <div>No source-of-truth brief found for this season.</div>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-2 px-6 py-5 text-sm leading-6 text-[var(--studio-secondary)]">
      {content.split("\n").map((line, index) => {
        const key = `${index}-${line}`;
        if (/^###\s+/.test(line)) {
          return (
            <h3 key={key} className="pt-4 text-base font-semibold text-[var(--studio-gold)]">
              <HighlightedText text={line.replace(/^###\s+/, "")} query={query} />
            </h3>
          );
        }
        if (/^##\s+/.test(line)) {
          return (
            <h2 key={key} className="pt-5 text-lg font-semibold text-[var(--studio-text)]">
              <HighlightedText text={line.replace(/^##\s+/, "")} query={query} />
            </h2>
          );
        }
        if (/^#\s+/.test(line)) {
          return (
            <h1 key={key} className="pb-1 text-xl font-semibold text-[var(--studio-text)]">
              <HighlightedText text={line.replace(/^#\s+/, "")} query={query} />
            </h1>
          );
        }
        if (/^\s*[-*]\s+/.test(line)) {
          return (
            <div key={key} className="pl-4 text-[var(--studio-secondary)]">
              <span className="mr-2 text-[var(--studio-purple)]">-</span>
              <HighlightedText text={line.replace(/^\s*[-*]\s+/, "")} query={query} />
            </div>
          );
        }
        if (line.trim() === "") {
          return <div key={key} className="h-2" />;
        }
        return (
          <p key={key}>
            <HighlightedText text={line} query={query} />
          </p>
        );
      })}
    </div>
  );
}

export function Studio() {
  const queryClient = useQueryClient();
  const sectionsRef = useRef(parseSections(""));
  const editorRef = useRef<MonacoEditor | null>(null);
  const monacoRef = useRef<MonacoInstance | null>(null);
  const speakerDecorationIdsRef = useRef<string[]>([]);
  const speakerColorIndexesRef = useRef<Map<string, number>>(new Map());
  const audioRefs = useRef<Record<string, AudioPlayerHandle | null>>({});
  const briefSearchRef = useRef<HTMLInputElement | null>(null);
  const chatInputRef = useRef<HTMLTextAreaElement | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [script, setScript] = useState("");
  const [notes, setNotes] = useState("");
  const [activeEditorTab, setActiveEditorTab] = useState<"script" | "brief" | "notes">("script");
  const [frontmatterOpen, setFrontmatterOpen] = useState(false);
  const [briefSearch, setBriefSearch] = useState("");
  const [selectedSectionId, setSelectedSectionId] = useState<string | null>(null);
  const [version, setVersion] = useState("v1");
  const [ddpmSteps, setDdpmSteps] = useState(50);
  const [cfgScale, setCfgScale] = useState(1.3);
  const [jobId, setJobId] = useState<string | null>(null);
  const [renderLog, setRenderLog] = useState<string[]>([]);
  const [aiInstruction, setAiInstruction] = useState("");
  const [aiModalOpen, setAiModalOpen] = useState(false);
  const [aiTarget, setAiTarget] = useState<AiTarget | null>(null);
  const [pendingEdit, setPendingEdit] = useState<PendingEdit | null>(null);
  const [annotationDraft, setAnnotationDraft] = useState<AnnotationDraft | null>(null);
  const [annotationText, setAnnotationText] = useState("");
  const [compareLeft, setCompareLeft] = useState("");
  const [compareRight, setCompareRight] = useState("");
  const [mixMode, setMixMode] = useState<"music_under_voice" | "music_off">("music_under_voice");
  const [mixVoice, setMixVoice] = useState("");
  const [mixBed, setMixBed] = useState("");
  const [introHot, setIntroHot] = useState(3.5);
  const [introFade, setIntroFade] = useState(4);
  const [outro, setOutro] = useState(7);
  const [masterLufs, setMasterLufs] = useState(-16);
  const [cloneName, setCloneName] = useState("");
  const [contextMenu, setContextMenu] = useState<EpisodeContextMenu | null>(null);
  const [duplicateDraft, setDuplicateDraft] = useState<DuplicateDraft | null>(null);
  const [settingsShow, setSettingsShow] = useState<string | null>(null);
  const [settingsDefaults, setSettingsDefaults] = useState<ShowDefaults | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [shortcutTip, setShortcutTip] = useState(false);
  const [episodeSwitcherOpen, setEpisodeSwitcherOpen] = useState(false);
  const [episodeSearch, setEpisodeSearch] = useState("");
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [bottomCollapsed, setBottomCollapsed] = useState(false);
  const [rightRailTab, setRightRailTab] = useState<RightRailTab>("render");
  const [selectedAudio, setSelectedAudio] = useState("");
  const [shortcutOverlayOpen, setShortcutOverlayOpen] = useState(false);
  const [chatAgent, setChatAgent] = useState("majik");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatStreaming, setChatStreaming] = useState(false);
  const [chatContextOpen, setChatContextOpen] = useState(false);

  const showsQuery = useQuery({ queryKey: ["shows"], queryFn: listShows });
  const voicesQuery = useQuery({ queryKey: ["voices"], queryFn: listVoices });
  const musicQuery = useQuery({ queryKey: ["music-beds"], queryFn: listMusicBeds });
  const chatAgentsQuery = useQuery({ queryKey: ["chat-agents"], queryFn: listChatAgents });
  const settingsShowQuery = useQuery({
    queryKey: ["show", settingsShow],
    queryFn: () => getShow(settingsShow!),
    enabled: Boolean(settingsShow),
  });
  const sourceQuery = useQuery({
    queryKey: ["source", selection?.show, selection?.season],
    queryFn: () => getSourceDoc(selection!.show, selection!.season),
    enabled: Boolean(selection),
  });
  const notesQuery = useQuery({
    queryKey: ["notes", selection],
    queryFn: () => getNotes(selection!.show, selection!.season, selection!.episode),
    enabled: Boolean(selection),
  });
  const chatHistoryQuery = useQuery({
    queryKey: ["chat", selection],
    queryFn: () => getChatHistory(selection!.show, selection!.season, selection!.episode),
    enabled: Boolean(selection),
  });
  const renderJobsQuery = useQuery({
    queryKey: ["render-jobs", "active"],
    queryFn: () => listRenderJobs({ status: "active" }),
    refetchInterval: 2000,
  });
  const recentJobsQuery = useQuery({
    queryKey: ["render-jobs", "episode", selection?.episode],
    queryFn: () => listRenderJobs({ episode: selection!.episode, limit: 10 }),
    enabled: Boolean(selection),
    refetchInterval: 5000,
  });
  const episodeQuery = useQuery({
    queryKey: ["episode", selection],
    queryFn: () => getEpisode(selection!.show, selection!.season, selection!.episode),
    enabled: Boolean(selection),
  });
  const jobQuery = useQuery({
    queryKey: ["render-job", jobId],
    queryFn: () => getRenderJob(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" ? false : 1200;
    },
  });

  useEffect(() => {
    if (!selection && showsQuery.data?.length) {
      setSelection(defaultSelection(showsQuery.data));
    }
  }, [selection, showsQuery.data]);

  useEffect(() => {
    if (episodeQuery.data) {
      setScript(episodeQuery.data.script);
      const proposed = nextVersion(episodeQuery.data.audio.map((file) => file.filename));
      const finalMp3s = episodeQuery.data.audio.filter((file) => file.kind === "final" && file.filename.endsWith(".mp3"));
      const playable = episodeQuery.data.audio.filter(
        (file) => file.filename.endsWith(".mp3") || file.filename.endsWith(".wav"),
      );
      setVersion(proposed);
      setMixVoice(episodeQuery.data.audio.find((file) => file.kind === "voice")?.filename ?? "");
      setCompareLeft(finalMp3s[0]?.filename ?? playable[0]?.filename ?? "");
      setCompareRight(finalMp3s[1]?.filename ?? playable[1]?.filename ?? "");
      setSelectedAudio(finalMp3s[0]?.filename ?? playable[0]?.filename ?? "");
      const frontmatter = episodeQuery.data.metrics.frontmatter ?? {};
      setDdpmSteps(Number(frontmatter.ddpm_steps ?? 50));
      setCfgScale(Number(frontmatter.cfg_scale ?? 1.3));
      if (typeof frontmatter.music_bed === "string") {
        setMixBed(frontmatter.music_bed);
      }
      setIntroHot(Number(frontmatter.intro_hot_s ?? 3.5));
      setIntroFade(Number(frontmatter.intro_fade_s ?? 4));
      setOutro(Number(frontmatter.outro_s ?? 7));
    }
  }, [episodeQuery.data]);

  useEffect(() => {
    setNotes(notesQuery.data ?? "");
  }, [notesQuery.data]);

  useEffect(() => {
    setChatMessages(
      (chatHistoryQuery.data ?? [])
        .filter((message) => message.role === "user" || message.role === "assistant")
        .slice(-16),
    );
  }, [chatHistoryQuery.data]);

  useEffect(() => {
    if (!mixBed && musicQuery.data?.length) {
      setMixBed(musicQuery.data[0].filename);
    }
  }, [mixBed, musicQuery.data]);

  useEffect(() => {
    if (settingsShowQuery.data) {
      setSettingsDefaults(defaultsWithFallback(settingsShowQuery.data.defaults));
    }
  }, [settingsShowQuery.data]);

  const sections = useMemo(() => parseSections(script), [script]);
  const cast = useMemo(() => parseCast(script), [script]);
  const audio = episodeQuery.data?.audio ?? [];
  const selectedSection = sections.find((section) => section.id === selectedSectionId) ?? sections[0];
  const dirty = script !== (episodeQuery.data?.script ?? "");
  const words = wordCount(script);
  const estimatedMinutes = words / 165;
  const playableAudio = audio.filter((file) => file.filename.endsWith(".mp3") || file.filename.endsWith(".wav"));
  const compareLeftFile = playableAudio.find((file) => file.filename === compareLeft);
  const compareRightFile = playableAudio.find((file) => file.filename === compareRight);
  const selectedAudioFile = playableAudio.find((file) => file.filename === selectedAudio) ?? playableAudio[0];
  const frontmatter = episodeQuery.data?.metrics.frontmatter ?? {};
  const episodeTitle = String(frontmatter.title ?? "Select an episode");
  const estimatedRenderSeconds = renderEstimate(words, ddpmSteps);
  const selectedSectionWords = selectedSection ? wordCount(selectedSection.markdown) : 0;
  const selectedSectionRenderSeconds = renderEstimate(selectedSectionWords, ddpmSteps);
  const activeJobs = useMemo(() => renderJobsQuery.data ?? [], [renderJobsQuery.data]);
  const recentJobs = useMemo(() => recentJobsQuery.data ?? [], [recentJobsQuery.data]);
  const jobList = [
    ...activeJobs,
    ...recentJobs.filter((recent) => !activeJobs.some((active) => active.id === recent.id)),
  ];
  const runningJobs = activeJobs.filter((job) => job.status === "running");
  const queuedJobs = activeJobs.filter((job) => job.status === "queued");
  const activeJobLabel = `Jobs: ${runningJobs.length} running, ${queuedJobs.length} queued`;
  const episodeChoices = useMemo(
    () =>
      (showsQuery.data ?? []).flatMap((show) =>
        show.seasons.flatMap((season) =>
          season.episodes.map((episode) => ({
            show,
            season,
            episode,
            haystack: `${show.title} ${season.title} ${episode.title} ${episode.slug}`.toLowerCase(),
          })),
        ),
      ),
    [showsQuery.data],
  );
  const filteredEpisodeChoices = episodeChoices
    .filter((item) => item.haystack.includes(episodeSearch.trim().toLowerCase()))
    .slice(0, 20);

  useEffect(() => {
    sectionsRef.current = sections;
  }, [sections]);

  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) {
      return;
    }
    const lines = script.split("\n");
    const decorations: Parameters<MonacoEditor["deltaDecorations"]>[1] = [];
    let activeSpeaker: string | null = null;
    lines.forEach((line, index) => {
      const lineNumber = index + 1;
      const speakerMatch = line.match(/^\*\*([A-Z][A-Z0-9]*):\*\*/);
      if (speakerMatch) {
        activeSpeaker = speakerMatch[1];
      } else if (/^##\s+/.test(line) || line.trim() === "") {
        activeSpeaker = null;
      }
      if (!activeSpeaker) {
        return;
      }
      if (!speakerColorIndexesRef.current.has(activeSpeaker)) {
        speakerColorIndexesRef.current.set(activeSpeaker, speakerColorIndexesRef.current.size % speakerPalette.length);
      }
      const palette = speakerPalette[speakerColorIndexesRef.current.get(activeSpeaker) ?? 0];
      decorations.push({
        range: new monaco.Range(lineNumber, 1, lineNumber, Math.max(line.length + 1, 1)),
        options: {
          isWholeLine: true,
          className: `podcast-speaker-line-${palette}`,
          inlineClassName: `podcast-speaker-text-${palette}`,
        },
      });
    });
    speakerDecorationIdsRef.current = editor.deltaDecorations(speakerDecorationIdsRef.current, decorations);
  }, [script]);

  useEffect(() => {
    if (!jobId) {
      return;
    }
    const wsBase = API_BASE.replace(/^http/, "ws");
    const socket = new WebSocket(`${wsBase}/render-jobs/${jobId}/stream`);
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data) as { lines?: string[]; status?: string };
      if (data.lines?.length) {
        setRenderLog((current) => [...current, ...data.lines!].slice(-220));
      }
      if (data.status === "completed" || data.status === "failed" || data.status === "cancelled") {
        queryClient.invalidateQueries({ queryKey: ["episode", selection] });
        queryClient.invalidateQueries({ queryKey: ["render-jobs"] });
      }
    };
    return () => socket.close();
  }, [jobId, queryClient, selection]);

  useEffect(() => {
    if (!contextMenu) {
      return;
    }
    const close = () => setContextMenu(null);
    window.addEventListener("click", close);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", close);
    };
  }, [contextMenu]);

  useEffect(() => {
    if (["completed", "failed", "cancelled"].includes(jobQuery.data?.status ?? "")) {
      queryClient.invalidateQueries({ queryKey: ["episode", selection] });
      queryClient.invalidateQueries({ queryKey: ["render-jobs"] });
    }
  }, [jobQuery.data?.status, queryClient, selection]);

  const showToast = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 5200);
  }, []);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!selection) {
        throw new Error("No episode selected");
      }
      return saveScript(selection.show, selection.season, selection.episode, script);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["episode", selection] }),
  });

  const notesMutation = useMutation({
    mutationFn: async () => {
      if (!selection) {
        throw new Error("No episode selected");
      }
      return saveNotes(selection.show, selection.season, selection.episode, notes);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notes", selection] });
      showToast("Episode notes saved.");
    },
  });

  const renderMutation = useMutation({
    mutationFn: async (scope: "all" | string[]) => {
      if (!selection) {
        throw new Error("No episode selected");
      }
      if (dirty) {
        await saveScript(selection.show, selection.season, selection.episode, script);
      }
      return startRender(selection.show, selection.season, selection.episode, {
        version,
        ddpm_steps: ddpmSteps,
        cfg_scale: cfgScale,
        sections: scope,
      });
    },
    onSuccess: (result) => {
      setJobId(result.job_id);
      setRenderLog([]);
      queryClient.invalidateQueries({ queryKey: ["episode", selection] });
      queryClient.invalidateQueries({ queryKey: ["render-jobs"] });
    },
  });

  const mixMutation = useMutation({
    mutationFn: async () => {
      if (!selection) {
        throw new Error("No episode selected");
      }
      return mixEpisode(selection.show, selection.season, selection.episode, {
        voice_wav: mixVoice,
        music_bed: mixBed,
        mode: mixMode,
        intro_hot_s: introHot,
        intro_fade_s: introFade,
        outro_s: outro,
        master_lufs: masterLufs,
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["episode", selection] }),
  });

  const annotationMutation = useMutation({
    mutationFn: async () => {
      if (!selection || !annotationDraft) {
        throw new Error("No annotation target selected");
      }
      return addAnnotation(selection.show, selection.season, selection.episode, {
        version: annotationDraft.version,
        time_s: annotationDraft.time,
        text: annotationText,
        section: selectedSection?.id ?? null,
      });
    },
    onSuccess: () => {
      setAnnotationDraft(null);
      setAnnotationText("");
      queryClient.invalidateQueries({ queryKey: ["episode", selection] });
    },
  });

  const aiMutation = useMutation({
    mutationFn: async () => {
      const target =
        aiTarget ??
        (selectedSection
          ? { kind: "section" as const, sectionId: selectedSection.id, text: selectedSection.markdown }
          : null);
      if (!target) {
        throw new Error("Select text or a section first");
      }
      const result = await aiScriptEdit({
        current_script: target.text,
        instruction: aiInstruction,
        model: "claude-3.5-haiku",
      });
      return { target, result };
    },
    onSuccess: ({ target, result }) => {
      if (result.ok === false) {
        showToast("AI edit unavailable — set BRIGADE_API_KEY in apps/api/.env to enable. Using local fallback for now.");
      }
      setPendingEdit({
        target,
        edited: result.edited_script,
        diff: result.diff,
        source: result.source,
        error: result.error,
      });
    },
  });

  const cloneMutation = useMutation({
    mutationFn: async (file: File) => cloneVoice(cloneName, file),
    onSuccess: () => {
      setCloneName("");
      queryClient.invalidateQueries({ queryKey: ["voices"] });
    },
  });

  const duplicateMutation = useMutation({
    mutationFn: async () => {
      if (!duplicateDraft) {
        throw new Error("No episode selected to duplicate");
      }
      return duplicateEpisode(duplicateDraft.show, duplicateDraft.season, duplicateDraft.episode, {
        new_slug: duplicateDraft.newSlug,
        new_title: duplicateDraft.newTitle,
        carry_body: false,
      });
    },
    onSuccess: (result) => {
      setDuplicateDraft(null);
      queryClient.invalidateQueries({ queryKey: ["shows"] });
      setSelection({ show: result.show, season: result.season, episode: result.episode });
    },
  });

  const saveDefaultsMutation = useMutation({
    mutationFn: async () => {
      if (!settingsShow || !settingsDefaults) {
        throw new Error("No show defaults to save");
      }
      return saveShowDefaults(settingsShow, settingsDefaults);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["show", settingsShow] });
      queryClient.invalidateQueries({ queryKey: ["shows"] });
      showToast("Show settings saved.");
    },
  });

  const cancelJobMutation = useMutation({
    mutationFn: cancelRenderJob,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["render-jobs"] }),
  });

  const beforeMount: BeforeMount = (monaco) => {
    monaco.languages.register({ id: "podcast-markdown" });
    monaco.languages.setMonarchTokensProvider("podcast-markdown", {
      tokenizer: {
        root: [
          [/^---$/, "delimiter"],
          [/^##\s+§.*$/, "section"],
          [/^\*\*[A-Z0-9_ -]+:\*\*/, "speaker"],
          [/#\s*voice:\s*[A-Za-z0-9_-]+.*$/, "voice"],
          [/\[[^\]]+\]/, "cue"],
          [/\*\*[^*]+\*\*/, "strong"],
        ],
      },
    });
    monaco.editor.defineTheme("podcast-ops-dark", {
      base: "vs-dark",
      inherit: true,
      rules: [
        { token: "delimiter", foreground: "64748b" },
        { token: "section", foreground: "ffc875", fontStyle: "bold" },
        { token: "speaker", foreground: "e8ecf2", fontStyle: "bold" },
        { token: "voice", foreground: "5eead4" },
        { token: "cue", foreground: "a36bff" },
        { token: "strong", foreground: "e8ecf2" },
      ],
      colors: {
        "editor.background": "#0a0e1a",
        "editor.foreground": "#e8ecf2",
        "editor.lineHighlightBackground": "#141826",
        "editorCursor.foreground": "#a36bff",
        "editorLineNumber.foreground": "#5a6478",
        "editor.selectionBackground": "#a36bff44",
        "editor.inactiveSelectionBackground": "#a36bff22",
      },
    });
  };

  const onMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    editor.onDidChangeCursorPosition((event) => {
      const active = [...sectionsRef.current].reverse().find((section) => section.line <= event.position.lineNumber);
      if (active) {
        setSelectedSectionId(active.id);
      }
    });
  };

  function playVoiceSample(voice: string) {
    if (!voice) {
      return;
    }
    const audioSample = new Audio(`${API_BASE}/voices/${voice}/sample`);
    audioSample.play().catch(() => undefined);
  }

  const saveCurrentScript = useCallback(() => {
    if (!selection || saveMutation.isPending) {
      return;
    }
    saveMutation.mutate();
  }, [saveMutation, selection]);

  const renderSelectedSection = useCallback(() => {
    const sectionId = selectedSection?.id ?? selectedSectionId;
    if (!sectionId) {
      return;
    }
    renderMutation.mutate([sectionId]);
  }, [renderMutation, selectedSection?.id, selectedSectionId]);

  const openAiPromptForSelection = useCallback(() => {
    const editor = editorRef.current;
    const model = editor?.getModel();
    const range = editor?.getSelection();
    if (model && range && !range.isEmpty()) {
      const text = model.getValueInRange(range);
      setAiTarget({
        kind: "selection",
        start: model.getOffsetAt(range.getStartPosition()),
        end: model.getOffsetAt(range.getEndPosition()),
        text,
      });
    } else if (selectedSection) {
      setAiTarget({ kind: "section", sectionId: selectedSection.id, text: selectedSection.markdown });
    } else {
      return;
    }
    setAiInstruction("");
    setPendingEdit(null);
    setAiModalOpen(true);
  }, [selectedSection]);

  const approvePendingEdit = useCallback(() => {
    if (!pendingEdit) {
      return;
    }
    const target = pendingEdit.target;
    const edited = pendingEdit.edited;
    if (target.kind === "section") {
      setScript((current) => replaceSection(current, target.sectionId, edited));
    } else {
      setScript((current) => `${current.slice(0, target.start)}${edited}${current.slice(target.end)}`);
    }
    setPendingEdit(null);
    setAiModalOpen(false);
  }, [pendingEdit]);

  const sectionStartForFile = useCallback(
    (duration: number | null | undefined) => {
      if (!duration || !selectedSection) {
        return 0;
      }
      const sectionWords = sections.map((section) => wordCount(section.markdown));
      const totalWords = sectionWords.reduce((sum, count) => sum + count, 0);
      if (!totalWords) {
        return 0;
      }
      const wordsBefore = sectionWords.slice(0, selectedSection.index).reduce((sum, count) => sum + count, 0);
      return duration * (wordsBefore / totalWords);
    },
    [sections, selectedSection],
  );

  const playCurrentSection = useCallback(() => {
    const file = selectedAudioFile ?? playableAudio[0];
    if (!file) {
      return;
    }
    audioRefs.current[file.filename]?.playFrom(sectionStartForFile(file.duration_s));
  }, [playableAudio, sectionStartForFile, selectedAudioFile]);

  const playSection = useCallback(
    (sectionId: string) => {
      const section = sections.find((item) => item.id === sectionId);
      const file = selectedAudioFile ?? playableAudio[0];
      if (!section || !file) {
        return;
      }
      const sectionWords = sections.map((item) => wordCount(item.markdown));
      const totalWords = sectionWords.reduce((sum, count) => sum + count, 0);
      const wordsBefore = sectionWords.slice(0, section.index).reduce((sum, count) => sum + count, 0);
      const start = totalWords && file.duration_s ? file.duration_s * (wordsBefore / totalWords) : 0;
      audioRefs.current[file.filename]?.playFrom(start);
    },
    [playableAudio, sections, selectedAudioFile],
  );

  const buildEpisodeContext = useCallback(() => {
    const editor = editorRef.current;
    const model = editor?.getModel();
    const range = editor?.getSelection();
    const selectedText = model && range && !range.isEmpty() ? model.getValueInRange(range) : "";
    return {
      show: selection?.show,
      season: selection?.season,
      episode: selection?.episode,
      title: episodeTitle,
      selected_section: selectedSection
        ? {
            id: selectedSection.id,
            title: selectedSection.title,
            markdown: selectedSection.markdown.slice(0, 5000),
          }
        : null,
      selected_text: selectedText.slice(0, 5000),
      script_excerpt: script.slice(0, 9000),
      brief_excerpt: (sourceQuery.data?.content ?? "").slice(0, 5000),
      recent_annotations: (episodeQuery.data?.annotations ?? []).slice(-3),
      active_jobs: activeJobs.slice(0, 5),
    };
  }, [
    activeJobs,
    episodeQuery.data?.annotations,
    episodeTitle,
    script,
    selectedSection,
    selection?.episode,
    selection?.season,
    selection?.show,
    sourceQuery.data?.content,
  ]);

  const sendChatMessage = useCallback(async () => {
    const content = chatInput.trim();
    if (!content || chatStreaming) {
      return;
    }
    if (content === "/render") {
      setChatInput("");
      if (window.confirm(`Render ${selectedSection?.id ?? "the current section"} with current params?`)) {
        renderSelectedSection();
      }
      return;
    }
    if (content === "/mix") {
      setChatInput("");
      if (window.confirm("Run the current mix settings now?")) {
        mixMutation.mutate();
      }
      return;
    }
    if (content === "/tighten" || content === "/punch-up") {
      setChatInput("");
      if (selectedSection) {
        setAiTarget({ kind: "section", sectionId: selectedSection.id, text: selectedSection.markdown });
        setAiInstruction(content === "/tighten" ? "make this section tighter" : "make this section more energetic");
        setAiModalOpen(true);
      }
      return;
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      agent: chatAgent,
      timestamp: new Date().toISOString(),
    };
    const assistantId = crypto.randomUUID();
    setChatInput("");
    setChatStreaming(true);
    setChatMessages((current) => [
      ...current,
      userMessage,
      { id: assistantId, role: "assistant", content: "", agent: chatAgent, timestamp: new Date().toISOString() },
    ]);
    try {
      await streamBrigadeChat(
        {
          agent: chatAgent,
          messages: [...chatMessages, userMessage].slice(-12).map((message) => ({
            role: message.role,
            content: message.content,
          })),
          episode_context: buildEpisodeContext(),
        },
        (delta) => {
          setChatMessages((current) =>
            current.map((message) =>
              message.id === assistantId ? { ...message, content: `${message.content}${delta}` } : message,
            ),
          );
        },
      );
      queryClient.invalidateQueries({ queryKey: ["chat", selection] });
    } catch (error) {
      setChatMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, content: `Chat unavailable: ${error instanceof Error ? error.message : String(error)}` }
            : message,
        ),
      );
    } finally {
      setChatStreaming(false);
    }
  }, [
    buildEpisodeContext,
    chatAgent,
    chatInput,
    chatMessages,
    chatStreaming,
    mixMutation,
    queryClient,
    renderSelectedSection,
    selectedSection,
    selection,
  ]);

  const openDuplicateModal = useCallback((show: ShowRef, season: SeasonRef, episode: EpisodeRef) => {
    setDuplicateDraft({
      show: show.slug,
      season: season.slug,
      episode: episode.slug,
      newSlug: "",
      newTitle: "",
    });
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const tag = (document.activeElement?.tagName ?? "").toLowerCase();
      if (event.key === "?" && !event.metaKey && !event.ctrlKey && !event.altKey) {
        if (!["input", "textarea"].includes(tag)) {
          event.preventDefault();
          setShortcutOverlayOpen(true);
        }
      }
      if (!event.metaKey && !event.ctrlKey && !event.altKey && !["input", "textarea"].includes(tag)) {
        const player = selectedAudioFile ? audioRefs.current[selectedAudioFile.filename] : null;
        if (event.key === " ") {
          event.preventDefault();
          player?.playPause();
        } else if (event.key.toLowerCase() === "j") {
          event.preventDefault();
          player?.seekBy(-5);
        } else if (event.key.toLowerCase() === "k") {
          event.preventDefault();
          player?.seekBy(5);
        } else if (event.key.toLowerCase() === "m" && selectedAudioFile) {
          event.preventDefault();
          setAnnotationDraft({
            time: player?.getTime() ?? 0,
            version: selectedAudioFile.filename,
            file: selectedAudioFile.filename,
          });
        }
      }
      const mod = event.metaKey || event.ctrlKey;
      if (!mod) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "s") {
        event.preventDefault();
        saveCurrentScript();
      } else if (key === "r") {
        event.preventDefault();
        renderSelectedSection();
      } else if (key === "enter") {
        event.preventDefault();
        if (document.activeElement === chatInputRef.current || rightRailTab === "chat") {
          void sendChatMessage();
        } else {
          playCurrentSection();
        }
      } else if (key === "e") {
        event.preventDefault();
        openAiPromptForSelection();
      } else if (key === "k" || key === "p") {
        event.preventDefault();
        setEpisodeSwitcherOpen(true);
      } else if (key === "f" && activeEditorTab === "brief") {
        event.preventDefault();
        briefSearchRef.current?.focus();
      } else if (/^[1-5]$/.test(key)) {
        event.preventDefault();
        setRightRailTab(rightRailTabs[Number(key) - 1]?.id ?? "voices");
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    activeEditorTab,
    openAiPromptForSelection,
    playCurrentSection,
    renderSelectedSection,
    saveCurrentScript,
    rightRailTab,
    sendChatMessage,
    selectedAudioFile,
  ]);

  const busy =
    saveMutation.isPending ||
    renderMutation.isPending ||
    mixMutation.isPending ||
    notesMutation.isPending ||
    aiMutation.isPending ||
    cloneMutation.isPending ||
    duplicateMutation.isPending ||
    saveDefaultsMutation.isPending ||
    cancelJobMutation.isPending;

  return (
    <main className="studio-shell flex h-screen min-h-[760px] flex-col overflow-hidden text-[var(--studio-text)]">
      <div
        className={cn(
          "grid min-h-0 flex-1 border-b border-[var(--studio-border)] transition-[grid-template-columns]",
          leftCollapsed
            ? "grid-cols-[56px_minmax(0,1fr)_380px]"
            : "grid-cols-[292px_minmax(0,1fr)_380px]",
        )}
      >
        <aside className="studio-sidebar flex min-h-0 flex-col border-r border-[var(--studio-border)]">
          <div className="flex h-[72px] items-center gap-3 border-b border-[var(--studio-border)] px-3">
            <button
              type="button"
              className={iconButtonStyle()}
              onClick={() => setLeftCollapsed((collapsed) => !collapsed)}
              title={leftCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {leftCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
            </button>
            {!leftCollapsed ? (
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-[15px] font-semibold tracking-tight">
                  <span className="text-[var(--studio-purple)]">✦</span>
                  Podcast-Ops
                </div>
                <div className="text-[11px] uppercase tracking-[0.22em] text-[var(--studio-muted)]">Studio</div>
              </div>
            ) : null}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 py-3">
            {leftCollapsed ? (
              <div className="space-y-2">
                {episodeChoices.slice(0, 18).map(({ show, season, episode }) => {
                  const status = episodeStatus(episode, activeJobs);
                  return (
                    <button
                      key={`${show.slug}/${season.slug}/${episode.slug}`}
                      type="button"
                      className={cn(
                        "relative grid h-10 w-10 place-items-center rounded-md text-xs font-semibold transition",
                        isSelected(selection, show, season, episode)
                          ? "bg-[rgba(163,107,255,0.18)] text-[var(--studio-purple)]"
                          : "text-[var(--studio-secondary)] hover:bg-white/[0.06]",
                      )}
                      onClick={() => setSelection({ show: show.slug, season: season.slug, episode: episode.slug })}
                      title={episode.title}
                    >
                      {episode.slug.match(/ep(\d+)/)?.[1] ?? "•"}
                      <span
                        className={cn(
                          "absolute bottom-1 right-1 h-1.5 w-1.5 rounded-full",
                          status === "rendering"
                            ? "bg-[var(--studio-gold)]"
                            : status === "ready"
                              ? "bg-[var(--studio-success)]"
                              : "bg-[var(--studio-muted)]",
                        )}
                      />
                    </button>
                  );
                })}
              </div>
            ) : (
              <>
                {showsQuery.data?.map((show) => (
                  <div key={show.slug} className="mb-5">
                    <div className="group mb-2 flex items-center gap-2 px-2 text-sm font-medium text-[var(--studio-text)]">
                      <ChevronDown size={14} className="shrink-0 text-[var(--studio-purple)]" />
                      <span className="min-w-0 flex-1 truncate">{show.title}</span>
                      <button
                        type="button"
                        className="grid h-7 w-7 place-items-center rounded-md text-[var(--studio-muted)] opacity-0 transition hover:bg-white/[0.06] hover:text-[var(--studio-text)] group-hover:opacity-100"
                        onClick={() => setSettingsShow(show.slug)}
                        title="Show settings"
                      >
                        <Settings size={14} />
                      </button>
                    </div>
                    {show.seasons.map((season) => (
                      <div key={season.slug} className="mb-3 pl-3">
                        <div className="mb-1 px-2 text-[10px] uppercase tracking-[0.18em] text-[var(--studio-muted)]">
                          {season.title}
                        </div>
                        <div className="space-y-1">
                          {season.episodes.map((episode) => {
                            const status = episodeStatus(episode, activeJobs);
                            return (
                              <button
                                key={episode.slug}
                                type="button"
                                className={cn(
                                  "group relative w-full rounded-md border px-3 py-2 text-left transition",
                                  isSelected(selection, show, season, episode)
                                    ? "border-[rgba(163,107,255,0.32)] bg-[rgba(163,107,255,0.13)] text-[var(--studio-text)] before:absolute before:bottom-1 before:left-0 before:top-1 before:w-0.5 before:rounded-full before:bg-[var(--studio-purple)]"
                                    : "border-transparent text-[var(--studio-secondary)] hover:bg-white/[0.045] hover:text-[var(--studio-text)]",
                                )}
                                onContextMenu={(event) => {
                                  event.preventDefault();
                                  setContextMenu({ x: event.clientX, y: event.clientY, show, season, episode });
                                }}
                                onClick={() =>
                                  setSelection({ show: show.slug, season: season.slug, episode: episode.slug })
                                }
                              >
                                <div className="flex items-start gap-2">
                                  <div className="min-w-0 flex-1">
                                    <div className="truncate text-sm font-medium">{episode.title}</div>
                                    <div className="mt-0.5 text-[11px] text-[var(--studio-muted)]">
                                      {episode.slug} · {relativeTime(episode.last_rendered_at)}
                                    </div>
                                  </div>
                                  <span className={cn("rounded-full px-2 py-0.5 text-[10px]", statusBadgeClass(status))}>
                                    {status}
                                  </span>
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
                <div className="mt-6 border-t border-[var(--studio-border)] pt-4">
                  <div className="mb-2 px-2 text-[10px] uppercase tracking-[0.18em] text-[var(--studio-muted)]">
                    Voices
                  </div>
                  <div className="grid grid-cols-2 gap-1">
                    {voicesQuery.data?.slice(0, 8).map((voice) => (
                      <button
                        key={voice.id}
                        type="button"
                        className="flex h-8 items-center gap-2 rounded-md px-2 text-left text-xs text-[var(--studio-secondary)] hover:bg-white/[0.05] hover:text-[var(--studio-text)]"
                        onMouseEnter={() => playVoiceSample(voice.id)}
                        title="Hover to preview voice"
                      >
                        <Volume2 size={12} className="text-[var(--studio-purple)]" />
                        <span className="truncate">{voice.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
          {!leftCollapsed ? (
            <div className="border-t border-[var(--studio-border)] p-3">
              <div className="grid grid-cols-2 gap-2">
                <button type="button" className={ghostButtonStyle()} title="New show">
                  + New show
                </button>
                <button type="button" className={secondaryButtonStyle()} onClick={() => setRightRailTab("voices")}>
                  + Voice clone
                </button>
              </div>
            </div>
          ) : null}
        </aside>

        <section className="flex min-h-0 flex-col bg-[var(--studio-bg)]">
          <header className="flex min-h-[72px] items-center justify-between gap-3 border-b border-[var(--studio-border)] px-5">
            <div className="min-w-0">
              <input
                className="w-full truncate bg-transparent text-xl font-semibold tracking-tight text-[var(--studio-text)] outline-none"
                value={episodeTitle}
                readOnly
                title="Episode title is currently sourced from frontmatter"
              />
              <div className="mt-1 flex flex-wrap gap-3 text-xs text-[var(--studio-muted)]">
                <span>{words.toLocaleString()} words</span>
                <span>{estimatedMinutes.toFixed(1)} min audio</span>
                <span>{formatEta(estimatedRenderSeconds)} render est.</span>
                <span>{sections.length} sections</span>
                {dirty ? <span className="text-[var(--studio-gold)]">unsaved edits</span> : <span>saved</span>}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button type="button" className={iconButtonStyle()} onClick={() => setShortcutOverlayOpen(true)} title="Keyboard shortcuts">
                <Keyboard size={15} />
              </button>
              <button
                type="button"
                className={dirty ? primaryButtonStyle() : secondaryButtonStyle()}
                disabled={!selection || !dirty || saveMutation.isPending}
                onClick={saveCurrentScript}
                title={`Save script (${shortcutLabel("S")})`}
              >
                <Save size={15} />
                Save
              </button>
            </div>
          </header>
          <div className="flex h-11 items-center justify-between border-b border-[var(--studio-border)] px-4">
            <div className="flex items-center gap-5">
              {(["script", "brief", "notes"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  className={cn(
                    "h-11 border-b-2 text-sm capitalize transition",
                    activeEditorTab === tab
                      ? "border-[var(--studio-purple)] text-[var(--studio-text)]"
                      : "border-transparent text-[var(--studio-secondary)] hover:text-[var(--studio-text)]",
                  )}
                  onClick={() => setActiveEditorTab(tab)}
                >
                  {tab}
                </button>
              ))}
            </div>
            {activeEditorTab === "brief" ? (
              <label className="flex h-8 w-64 items-center gap-2 rounded-md border border-[var(--studio-border)] bg-[var(--studio-input)] px-2 text-xs text-[var(--studio-muted)]">
                <Search size={13} />
                <input
                  ref={briefSearchRef}
                  className="h-full min-w-0 flex-1 bg-transparent text-sm text-[var(--studio-text)] outline-none placeholder:text-[var(--studio-muted)]"
                  value={briefSearch}
                  onChange={(event) => setBriefSearch(event.target.value)}
                  placeholder="Command-F search brief"
                />
              </label>
            ) : shortcutTip ? (
              <div className="text-xs text-[var(--studio-purple)]">Try {shortcutLabel("S")} to save</div>
            ) : null}
          </div>
          {activeEditorTab === "script" ? (
            <div className="border-b border-[var(--studio-border)] bg-[rgba(20,24,38,0.55)] px-4 py-2">
              <button
                type="button"
                className="flex w-full items-center justify-between text-left text-xs uppercase tracking-[0.16em] text-[var(--studio-muted)]"
                onClick={() => setFrontmatterOpen((open) => !open)}
              >
                <span>
                  Frontmatter · cast {cast.map((member) => member.speaker).join(" / ") || "none"} ·{" "}
                  {String(frontmatter.status ?? "draft")}
                </span>
                <ChevronDown size={14} className={cn("transition", frontmatterOpen ? "rotate-180" : "")} />
              </button>
              {frontmatterOpen ? (
                <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                  <label className="text-[var(--studio-muted)]">
                    Title
                    <input className={cn(inputStyle(), "mt-1 w-full")} value={episodeTitle} readOnly />
                  </label>
                  <label className="text-[var(--studio-muted)]">
                    Status
                    <input className={cn(inputStyle(), "mt-1 w-full")} value={String(frontmatter.status ?? "draft")} readOnly />
                  </label>
                </div>
              ) : null}
            </div>
          ) : null}
          <div className="relative flex min-h-0 flex-1">
            {activeEditorTab === "script" ? (
              <>
                <div className="w-24 shrink-0 overflow-y-auto border-r border-[var(--studio-border)] bg-[rgba(15,18,25,0.75)] px-2 py-4">
                  <div className="mb-3 text-center text-[10px] uppercase tracking-[0.16em] text-[var(--studio-muted)]">Sections</div>
                  <div className="space-y-2">
                    {sections.map((section) => (
                      <div
                        key={section.id}
                        className={cn(
                          "rounded-md border p-1.5 text-center transition",
                          selectedSection?.id === section.id
                            ? "border-[rgba(163,107,255,0.42)] bg-[rgba(163,107,255,0.12)]"
                            : "border-transparent bg-white/[0.025]",
                        )}
                      >
                        <button
                          type="button"
                          className="block w-full text-xs font-semibold text-[var(--studio-text)]"
                          onClick={() => {
                            setSelectedSectionId(section.id);
                            editorRef.current?.revealLineInCenter(section.line);
                          }}
                        >
                          {section.id}
                        </button>
                        <div className="mt-1 flex justify-center gap-1">
                          <button
                            type="button"
                            className={iconButtonStyle()}
                            onClick={() => renderMutation.mutate([section.id])}
                            title={`Render ${section.id}`}
                          >
                            <PlayCircle size={12} />
                          </button>
                          <button
                            type="button"
                            className={iconButtonStyle()}
                            onClick={() => playSection(section.id)}
                            title={`Play ${section.id}`}
                          >
                            <Headphones size={12} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="relative min-w-0 flex-1">
                  <div className="absolute right-4 top-3 z-10 flex overflow-hidden rounded-md border border-[var(--studio-border)] bg-[rgba(20,24,38,0.92)] shadow-xl backdrop-blur">
                    <button type="button" className={ghostButtonStyle()} onClick={openAiPromptForSelection}>
                      <WandSparkles size={14} />
                      AI edit
                    </button>
                    <button type="button" className={ghostButtonStyle()} onClick={renderSelectedSection}>
                      <PlayCircle size={14} />
                      Render
                    </button>
                    <button type="button" className={ghostButtonStyle()} onClick={playCurrentSection}>
                      <Headphones size={14} />
                      Play
                    </button>
                  </div>
                  <Editor
                    beforeMount={beforeMount}
                    onMount={onMount}
                    theme="podcast-ops-dark"
                    language="podcast-markdown"
                    value={script}
                    onChange={(value) => {
                      setScript(value ?? "");
                      if (!shortcutTip && typeof window !== "undefined" && !window.localStorage.getItem("podcast-ops-shortcut-tip")) {
                        window.localStorage.setItem("podcast-ops-shortcut-tip", "seen");
                        setShortcutTip(true);
                      }
                    }}
                    options={{
                      fontFamily: "var(--font-geist-mono)",
                      fontSize: 15,
                      lineHeight: 24,
                      minimap: { enabled: false },
                      wordWrap: "on",
                      padding: { top: 24, bottom: 24 },
                      scrollBeyondLastLine: false,
                      renderLineHighlight: "line",
                      tabSize: 2,
                    }}
                  />
                </div>
              </>
            ) : activeEditorTab === "brief" ? (
              <div className="h-full flex-1 overflow-auto">
                <BriefMarkdown content={sourceQuery.data?.content} query={briefSearch} />
              </div>
            ) : (
              <div className="flex min-h-0 flex-1 flex-col p-5">
                <textarea
                  className="min-h-0 flex-1 resize-none rounded-md border border-[var(--studio-border)] bg-[var(--studio-input)] p-4 font-mono text-sm leading-6 text-[var(--studio-text)] outline-none focus:border-[var(--studio-purple)] focus:ring-2 focus:ring-[rgba(163,107,255,0.22)]"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  placeholder="Episode notes, post-render feedback, producer reminders..."
                />
                <div className="mt-3 flex justify-end">
                  <button type="button" className={primaryButtonStyle()} onClick={() => notesMutation.mutate()} disabled={!selection || notesMutation.isPending}>
                    Save notes
                  </button>
                </div>
              </div>
            )}
          </div>
          <div className="flex h-10 items-center gap-2 overflow-x-auto border-t border-[var(--studio-border)] px-4 text-xs text-[var(--studio-muted)]">
            {sections.map((section) => (
              <button
                key={section.id}
                type="button"
                className={cn(
                  "shrink-0 rounded-full border px-3 py-1 transition",
                  selectedSection?.id === section.id
                    ? "border-[rgba(163,107,255,0.44)] bg-[rgba(163,107,255,0.12)] text-[var(--studio-text)]"
                    : "border-[var(--studio-border)] hover:bg-white/[0.05]",
                )}
                onClick={() => {
                  setSelectedSectionId(section.id);
                  editorRef.current?.revealLineInCenter(section.line);
                }}
              >
                {section.id} · {formatEta(renderEstimate(wordCount(section.markdown), ddpmSteps))}
              </button>
            ))}
          </div>
        </section>

        <aside className="studio-right-rail flex min-h-0 flex-col border-l border-[var(--studio-border)]">
          <div className="grid grid-cols-5 border-b border-[var(--studio-border)]">
            {rightRailTabs.map((tab, index) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  type="button"
                  className={cn(
                    "flex h-12 flex-col items-center justify-center gap-0.5 border-b-2 text-[10px] transition",
                    rightRailTab === tab.id
                      ? "border-[var(--studio-purple)] bg-[rgba(163,107,255,0.10)] text-[var(--studio-text)]"
                      : "border-transparent text-[var(--studio-muted)] hover:bg-white/[0.04] hover:text-[var(--studio-text)]",
                  )}
                  onClick={() => setRightRailTab(tab.id)}
                  title={`${tab.label} (${shortcutLabel(String(index + 1))})`}
                >
                  <Icon size={15} />
                  {tab.label}
                </button>
              );
            })}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {rightRailTab === "voices" ? (
              <div className="space-y-5">
                <div>
                  <div className="studio-panel-title mb-3">Voice cast</div>
                  {cast.length ? (
                    <div className="space-y-2">
                      {cast.map((member) => (
                        <div key={member.speaker} className="grid grid-cols-[72px_minmax(0,1fr)_34px] items-center gap-2">
                          <div className="rounded-md bg-white/[0.05] px-2 py-2 text-xs font-semibold text-[var(--studio-text)]">
                            {member.speaker}
                          </div>
                          <select
                            className={selectStyle()}
                            value={member.voice}
                            onChange={(event) => setScript(replaceCastVoice(script, member.speaker, event.target.value))}
                          >
                            <option value="">No voice</option>
                            {voicesQuery.data?.map((voice) => (
                              <option key={voice.id} value={voice.id}>
                                {voice.label}
                              </option>
                            ))}
                          </select>
                          <button type="button" className={iconButtonStyle()} onClick={() => playVoiceSample(member.voice)} title="Preview voice">
                            <Volume2 size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="studio-empty">
                      <Mic2 size={22} />
                      <div>No voice cast yet.</div>
                      <button type="button" className={secondaryButtonStyle()}>
                        Add a voice
                      </button>
                    </div>
                  )}
                </div>
                <div>
                  <div className="studio-panel-title mb-3">Clone new voice</div>
                  <div className="rounded-md border border-dashed border-[rgba(163,107,255,0.35)] bg-[rgba(163,107,255,0.06)] p-3">
                    <input className={cn(inputStyle(), "mb-2 w-full")} value={cloneName} onChange={(event) => setCloneName(event.target.value)} placeholder="voice name" />
                    <label className={cn(secondaryButtonStyle(), "w-full cursor-pointer")}>
                      <Upload size={14} />
                      Upload voice sample
                      <input
                        className="hidden"
                        type="file"
                        accept="audio/*"
                        disabled={!cloneName}
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          if (file) {
                            cloneMutation.mutate(file);
                          }
                        }}
                      />
                    </label>
                  </div>
                </div>
              </div>
            ) : rightRailTab === "render" ? (
              <div className="space-y-5">
                <div>
                  <div className="studio-panel-title mb-3">Render target</div>
                  <div className="rounded-md bg-white/[0.04] p-3">
                    <div className="text-sm font-medium text-[var(--studio-text)]">{selectedSection?.id ?? "No section"} {selectedSection?.title}</div>
                    <div className="mt-1 text-xs text-[var(--studio-muted)]">{selectedSectionWords} words · {formatEta(selectedSectionRenderSeconds)} est.</div>
                  </div>
                </div>
                <label className="block text-xs text-[var(--studio-muted)]">
                  Version
                  <input className={cn(inputStyle(), "mt-1 w-full")} value={version} onChange={(event) => setVersion(event.target.value)} />
                </label>
                <label className="block text-xs text-[var(--studio-muted)]">
                  <div className="mb-1 flex justify-between"><span>DDPM</span><span>{ddpmSteps}</span></div>
                  <input className="w-full accent-[var(--studio-purple)]" type="range" min={10} max={100} step={5} value={ddpmSteps} onChange={(event) => setDdpmSteps(Number(event.target.value))} />
                </label>
                <label className="block text-xs text-[var(--studio-muted)]">
                  <div className="mb-1 flex justify-between"><span>CFG</span><span>{cfgScale.toFixed(1)}</span></div>
                  <input className="w-full accent-[var(--studio-purple)]" type="range" min={1} max={2} step={0.1} value={cfgScale} onChange={(event) => setCfgScale(Number(event.target.value))} />
                </label>
                <select className={cn(selectStyle(), "w-full")} defaultValue="vibevoice-7b">
                  <option value="vibevoice-7b">VibeVoice 7B</option>
                </select>
                <button type="button" className={cn(primaryButtonStyle(), "w-full")} disabled={!selection || renderMutation.isPending} onClick={renderSelectedSection}>
                  <PlayCircle size={15} />
                  Render {selectedSection?.id ?? "section"}
                </button>
                <button type="button" className={cn(secondaryButtonStyle(), "w-full")} disabled={!selection || renderMutation.isPending} onClick={() => renderMutation.mutate("all")}>
                  Render full episode
                </button>
              </div>
            ) : rightRailTab === "mix" ? (
              <div className="space-y-4">
                <div className="studio-panel-title">Mix bed</div>
                <select className={cn(selectStyle(), "w-full")} value={mixVoice} onChange={(event) => setMixVoice(event.target.value)}>
                  <option value="">Voice WAV</option>
                  {audio.filter((file) => file.kind === "voice" && file.filename.endsWith(".wav")).map((file) => (
                    <option key={file.filename} value={file.filename}>{file.filename}</option>
                  ))}
                </select>
                <div className="grid grid-cols-[minmax(0,1fr)_34px] gap-2">
                  <select className={cn(selectStyle(), "w-full")} value={mixBed} onChange={(event) => setMixBed(event.target.value)}>
                    <option value="">Music bed</option>
                    {musicQuery.data?.map((bed) => <option key={bed.path} value={bed.filename}>{bed.title}</option>)}
                  </select>
                  <button type="button" className={iconButtonStyle()} title="Preview music bed">
                    <Volume2 size={14} />
                  </button>
                </div>
                <label className="flex items-center justify-between rounded-md bg-white/[0.04] px-3 py-2 text-sm">
                  <span>Music off</span>
                  <input type="checkbox" checked={mixMode === "music_off"} onChange={(event) => setMixMode(event.target.checked ? "music_off" : "music_under_voice")} className="accent-[var(--studio-purple)]" />
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    ["Intro hot", introHot, setIntroHot],
                    ["Intro fade", introFade, setIntroFade],
                    ["Outro", outro, setOutro],
                    ["LUFS", masterLufs, setMasterLufs],
                  ].map(([label, value, setter]) => (
                    <label key={String(label)} className="text-xs text-[var(--studio-muted)]">
                      {String(label)}
                      <input className={cn(inputStyle(), "mt-1 w-full")} type="number" step={0.5} value={Number(value)} onChange={(event) => (setter as (value: number) => void)(Number(event.target.value))} />
                    </label>
                  ))}
                </div>
                <div className="h-20 rounded-md border border-[var(--studio-border)] bg-[linear-gradient(90deg,rgba(163,107,255,0.18)_0_12%,rgba(94,234,212,0.10)_12%_68%,rgba(255,200,117,0.18)_68%)]" />
                <button type="button" className={cn(primaryButtonStyle(), "w-full")} disabled={!mixVoice || (!mixBed && mixMode !== "music_off") || mixMutation.isPending} onClick={() => mixMutation.mutate()}>
                  <Music2 size={15} />
                  Mix now
                </button>
              </div>
            ) : rightRailTab === "jobs" ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="studio-panel-title">Queue</div>
                  <div className="text-xs text-[var(--studio-muted)]">{activeJobLabel}</div>
                </div>
                {renderLog.length ? (
                  <div className="rounded-md border border-[var(--studio-border)] bg-black/20 p-3">
                    <div className="mb-2 text-xs font-medium uppercase tracking-[0.14em] text-[var(--studio-muted)]">
                      Live log
                    </div>
                    <pre className="max-h-28 overflow-auto whitespace-pre-wrap text-[11px] leading-4 text-[var(--studio-secondary)]">
                      {renderLog.slice(-8).join("\n")}
                    </pre>
                  </div>
                ) : null}
                {jobList.length ? jobList.map((job) => (
                  <div key={job.id} className="rounded-md border border-[var(--studio-border)] bg-white/[0.035] p-3">
                    <div className="mb-2 flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">{job.episode}</div>
                        <div className="text-xs text-[var(--studio-muted)]">{renderJobVersion(job)} · {job.status} · ETA {formatEta(job.eta_s)}</div>
                      </div>
                      <button type="button" className={iconButtonStyle()} disabled={cancelJobMutation.isPending} onClick={() => cancelJobMutation.mutate(job.id)} title="Cancel job">
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                      <div className="h-full rounded-full bg-[var(--studio-purple)]" style={{ width: `${job.progress_pct ?? 0}%` }} />
                    </div>
                    <pre className="mt-2 max-h-20 overflow-hidden whitespace-pre-wrap text-[11px] leading-4 text-[var(--studio-muted)]">
                      {(job.log ?? []).slice(-3).join("\n")}
                    </pre>
                  </div>
                )) : (
                  <div className="studio-empty">
                    <Clock size={22} />
                    <div>No active jobs. Try rendering a section.</div>
                    <button type="button" className={primaryButtonStyle()} onClick={renderSelectedSection}>
                      <PlayCircle size={14} />
                      Render section
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex h-full min-h-0 flex-col">
                <div className="mb-3 grid grid-cols-[minmax(0,1fr)_34px] gap-2">
                  <select className={selectStyle()} value={chatAgent} onChange={(event) => setChatAgent(event.target.value)}>
                    {(chatAgentsQuery.data ?? [
                      { id: "majik", label: "majik", description: "knows the whole ecosystem" },
                      { id: "the-general", label: "the-general", description: "strategic" },
                      { id: "gunny", label: "gunny", description: "pragmatic implementation" },
                      { id: "gflow", label: "gflow", description: "operations" },
                    ]).map((agent) => (
                      <option key={agent.id} value={agent.id}>{agent.label} — {agent.description}</option>
                    ))}
                  </select>
                  <button type="button" className={iconButtonStyle()} onClick={() => setChatContextOpen((open) => !open)} title="Episode context">
                    <FileText size={14} />
                  </button>
                </div>
                {chatContextOpen ? (
                  <div className="mb-3 rounded-md border border-[var(--studio-border)] bg-white/[0.035] p-2 text-xs leading-5 text-[var(--studio-secondary)]">
                    Context: {episodeTitle} · {selectedSection?.id ?? "no section"} · last {(episodeQuery.data?.annotations ?? []).slice(-3).length} annotations · brief excerpt.
                  </div>
                ) : (
                  <div className="mb-3 rounded-full border border-[rgba(163,107,255,0.28)] bg-[rgba(163,107,255,0.08)] px-3 py-1 text-xs text-[var(--studio-secondary)]">
                    Context attached: {selectedSection?.id ?? "episode"} + last 3 annotations
                  </div>
                )}
                <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
                  {chatMessages.length ? chatMessages.map((message, messageIndex) => (
                    <div key={message.id ?? `${message.role}-${message.content}`} className={cn("flex", message.role === "user" ? "justify-end" : "justify-start")}>
                      <div className={cn("max-w-[86%] rounded-lg px-3 py-2 text-sm leading-6", message.role === "user" ? "bg-[var(--studio-purple)] text-white" : "bg-white/[0.06] text-[var(--studio-text)]")}>
                        <div className="mb-1 text-[10px] uppercase tracking-[0.14em] opacity-60">{message.role === "user" ? "You" : message.agent ?? chatAgent}</div>
                        <div className="whitespace-pre-wrap">
                          {message.content ? <MiniMarkdown content={message.content} /> : chatStreaming ? "Thinking..." : ""}
                        </div>
                        {message.role === "assistant" && message.content ? (
                          <div className="mt-2 flex gap-1 border-t border-white/10 pt-2">
                            <button type="button" className={iconButtonStyle()} onClick={() => {
                              const previousUser = chatMessages
                                .slice(0, messageIndex)
                                .reverse()
                                .find((item) => item.role === "user");
                              setChatInput(previousUser?.content ?? "");
                              window.setTimeout(() => chatInputRef.current?.focus(), 0);
                            }} title="Retry">
                              <RotateCcw size={12} />
                            </button>
                            <button type="button" className={iconButtonStyle()} onClick={() => navigator.clipboard?.writeText(message.content)} title="Copy">
                              <Copy size={12} />
                            </button>
                            <button type="button" className={iconButtonStyle()} onClick={() => {
                              const editor = editorRef.current;
                              const position = editor?.getPosition();
                              if (editor && position) {
                                editor.executeEdits("chat-insert", [{ range: { startLineNumber: position.lineNumber, startColumn: position.column, endLineNumber: position.lineNumber, endColumn: position.column }, text: message.content }]);
                              }
                            }} title="Insert at cursor">
                              <FileText size={12} />
                            </button>
                            <button type="button" className={iconButtonStyle()} onClick={() => chatInputRef.current?.focus()} title="Follow up">
                              <MessageSquare size={12} />
                            </button>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  )) : (
                    <div className="studio-empty">
                      <Bot size={22} />
                      <div>Ask Majik about this episode, a section rewrite, or production notes.</div>
                    </div>
                  )}
                </div>
                <div className="mt-3">
                  <textarea
                    ref={chatInputRef}
                    className="min-h-24 w-full resize-none rounded-md border border-[var(--studio-border)] bg-[var(--studio-input)] p-3 text-sm text-[var(--studio-text)] outline-none placeholder:text-[var(--studio-muted)] focus:border-[var(--studio-purple)] focus:ring-2 focus:ring-[rgba(163,107,255,0.22)]"
                    value={chatInput}
                    onChange={(event) => setChatInput(event.target.value)}
                    onKeyDown={(event) => {
                      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                        event.preventDefault();
                        void sendChatMessage();
                      }
                    }}
                    placeholder="/tighten, /punch-up, /research comps, or ask a question"
                  />
                  <button type="button" className={cn(primaryButtonStyle(), "mt-2 w-full")} disabled={!chatInput.trim() || chatStreaming} onClick={() => void sendChatMessage()}>
                    <Send size={14} />
                    Send to {chatAgent}
                  </button>
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>

      <section className={cn("studio-bottom-panel border-t border-[var(--studio-border)] transition-[height]", bottomCollapsed ? "h-12" : "h-[292px]")}>
        <div className="flex h-12 items-center justify-between border-b border-[var(--studio-border)] px-4">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Headphones size={16} className="text-[var(--studio-purple)]" />
            Audio + annotations
            <span className="text-xs font-normal text-[var(--studio-muted)]">{playableAudio.length} playable files</span>
          </div>
          <button type="button" className={iconButtonStyle()} onClick={() => setBottomCollapsed((collapsed) => !collapsed)} title="Collapse audio panel">
            <ChevronDown size={15} className={cn("transition", bottomCollapsed ? "rotate-180" : "")} />
          </button>
        </div>
        {!bottomCollapsed ? (
          <div className="grid h-[240px] grid-cols-[260px_minmax(0,1fr)_340px]">
            <div className="min-h-0 overflow-y-auto border-r border-[var(--studio-border)] p-3">
              {playableAudio.length ? playableAudio.slice(0, 12).map((file) => (
                <button
                  key={file.filename}
                  type="button"
                  className={cn(
                    "mb-1 w-full rounded-md px-3 py-2 text-left text-xs transition",
                    selectedAudioFile?.filename === file.filename ? "bg-[rgba(163,107,255,0.14)] text-[var(--studio-text)]" : "text-[var(--studio-secondary)] hover:bg-white/[0.05]",
                  )}
                  onClick={() => setSelectedAudio(file.filename)}
                >
                  <div className="truncate font-medium">{file.filename}</div>
                  <div className="mt-0.5 text-[11px] text-[var(--studio-muted)]">{file.kind} · {formatTime(file.duration_s)}</div>
                </button>
              )) : (
                <div className="studio-empty">
                  <Headphones size={22} />
                  <div>No rendered audio yet.</div>
                  <button type="button" className={primaryButtonStyle()} onClick={renderSelectedSection}>
                    Render section
                  </button>
                </div>
              )}
            </div>
            <div className="min-h-0 overflow-y-auto">
              {selectedAudioFile ? (
                <>
                  <AudioPlayer
                    ref={(node) => {
                      audioRefs.current[selectedAudioFile.filename] = node;
                    }}
                    title={selectedAudioFile.filename}
                    src={audioUrl(selectedAudioFile)}
                    duration={selectedAudioFile.duration_s}
                    onAnnotate={(time) => setAnnotationDraft({ time, version: selectedAudioFile.filename, file: selectedAudioFile.filename })}
                  />
                  <div className="relative mx-4 mt-2 h-8 rounded-md bg-white/[0.035]">
                    {sections.map((section) => (
                      <button
                        key={section.id}
                        type="button"
                        className="absolute top-0 h-8 border-l border-[var(--studio-purple)] pl-1 text-[10px] text-[var(--studio-muted)]"
                        style={{ left: `${sections.length ? (section.index / sections.length) * 100 : 0}%` }}
                        onClick={() => playSection(section.id)}
                        title={section.title}
                      >
                        {section.id}
                      </button>
                    ))}
                    {(episodeQuery.data?.annotations ?? []).map((annotation) => (
                      <button
                        key={annotation.id}
                        type="button"
                        className="absolute top-3 h-2 w-2 rounded-full bg-[var(--studio-gold)]"
                        style={{ left: `${selectedAudioFile.duration_s ? Math.min((annotation.time_s / selectedAudioFile.duration_s) * 100, 99) : 0}%` }}
                        onClick={() => audioRefs.current[selectedAudioFile.filename]?.playFrom(annotation.time_s)}
                        title={annotation.text}
                      />
                    ))}
                  </div>
                  <div className="flex justify-between px-4 py-2">
                    <button type="button" className={ghostButtonStyle()} disabled={!selection} onClick={() => selection && openAudioFile(selection.show, selection.season, selection.episode, selectedAudioFile.filename)}>
                      <FolderOpen size={13} />
                      Open audio folder
                    </button>
                    <div className="flex gap-2">
                      <select className={selectStyle()} value={compareLeft} onChange={(event) => setCompareLeft(event.target.value)}>
                        <option value="">Left</option>
                        {playableAudio.map((file) => <option key={file.filename} value={file.filename}>{file.filename}</option>)}
                      </select>
                      <select className={selectStyle()} value={compareRight} onChange={(event) => setCompareRight(event.target.value)}>
                        <option value="">Right</option>
                        {playableAudio.map((file) => <option key={file.filename} value={file.filename}>{file.filename}</option>)}
                      </select>
                    </div>
                  </div>
                  <ComparePlayer left={compareLeftFile} right={compareRightFile} />
                </>
              ) : null}
            </div>
            <aside className="min-h-0 overflow-y-auto border-l border-[var(--studio-border)] p-3">
              <div className="mb-2 text-sm font-semibold">Annotations</div>
              {annotationDraft ? (
                <div className="mb-3 rounded-md border border-[rgba(163,107,255,0.32)] bg-[rgba(163,107,255,0.10)] p-2">
                  <div className="mb-2 text-xs text-[var(--studio-text)]">{annotationDraft.file} at {formatTime(annotationDraft.time)}</div>
                  <textarea className="min-h-16 w-full resize-none rounded-md border border-[var(--studio-border)] bg-[var(--studio-input)] p-2 text-sm outline-none" value={annotationText} onChange={(event) => setAnnotationText(event.target.value)} placeholder="note this moment" />
                  <button type="button" className={cn(primaryButtonStyle(), "mt-2 w-full")} disabled={!annotationText || annotationMutation.isPending} onClick={() => annotationMutation.mutate()}>
                    Save annotation
                  </button>
                </div>
              ) : null}
              <div className="space-y-2">
                {episodeQuery.data?.annotations.length ? episodeQuery.data.annotations.map((annotation) => (
                  <button key={annotation.id} type="button" className="block w-full rounded-md border-l border-[var(--studio-purple)] bg-white/[0.035] px-3 py-2 text-left" onClick={() => selectedAudioFile && audioRefs.current[selectedAudioFile.filename]?.playFrom(annotation.time_s)}>
                    <div className="mb-1 flex justify-between gap-2 text-xs text-[var(--studio-muted)]"><span className="truncate">{annotation.version}</span><span>{formatTime(annotation.time_s)}</span></div>
                    <div className="text-sm text-[var(--studio-text)]">{annotation.text}</div>
                  </button>
                )) : (
                  <div className="studio-empty">
                    <AlertCircle size={20} />
                    <div>No annotations yet. Click the waveform plus button to mark feedback.</div>
                  </div>
                )}
              </div>
            </aside>
          </div>
        ) : null}
      </section>

      {contextMenu ? (
        <div
          className="fixed z-50 w-52 rounded-md border border-[var(--studio-border)] bg-[var(--studio-surface)] p-1 shadow-2xl"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            type="button"
            className="flex h-9 w-full items-center gap-2 rounded px-2 text-left text-sm text-[var(--studio-text)] hover:bg-white/[0.06]"
            onClick={() => {
              openDuplicateModal(contextMenu.show, contextMenu.season, contextMenu.episode);
              setContextMenu(null);
            }}
          >
            <Copy size={14} />
            Duplicate
          </button>
          <button
            type="button"
            className="flex h-9 w-full items-center gap-2 rounded px-2 text-left text-sm text-[var(--studio-secondary)] hover:bg-white/[0.06] hover:text-[var(--studio-text)]"
            onClick={() => {
              setContextMenu(null);
              showToast("Rename needs an episode filesystem operation; keeping this pass non-destructive.");
            }}
          >
            <FileText size={14} />
            Rename
          </button>
          <button
            type="button"
            className="flex h-9 w-full items-center gap-2 rounded px-2 text-left text-sm text-[var(--studio-secondary)] hover:bg-white/[0.06] hover:text-[var(--studio-text)]"
            onClick={() => {
              if (
                selection?.show === contextMenu.show.slug &&
                selection.season === contextMenu.season.slug &&
                selection.episode === contextMenu.episode.slug &&
                selectedAudioFile
              ) {
                void openAudioFile(contextMenu.show.slug, contextMenu.season.slug, contextMenu.episode.slug, selectedAudioFile.filename);
              } else {
                setSelection({ show: contextMenu.show.slug, season: contextMenu.season.slug, episode: contextMenu.episode.slug });
                showToast("Episode selected. Pick an audio version to reveal its folder.");
              }
              setContextMenu(null);
            }}
          >
            <FolderOpen size={14} />
            Open audio folder
          </button>
          <button
            type="button"
            className="flex h-9 w-full items-center gap-2 rounded px-2 text-left text-sm text-[var(--studio-danger)] hover:bg-[rgba(248,113,113,0.10)]"
            onClick={() => {
              setContextMenu(null);
              if (window.confirm(`Delete ${contextMenu.episode.title}?`)) {
                showToast("Delete is intentionally not wired without a backend delete endpoint.");
              }
            }}
          >
            <Trash2 size={14} />
            Delete
          </button>
        </div>
      ) : null}

      {duplicateDraft ? (
        <div className={modalShellStyle()}>
          <div className={panelStyle()}>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-lg font-semibold text-[var(--studio-text)]">Duplicate Episode</div>
                <div className="text-xs text-[var(--studio-muted)]">{duplicateDraft.episode}</div>
              </div>
              <button
                type="button"
                className={iconButtonStyle()}
                onClick={() => setDuplicateDraft(null)}
                title="Close"
              >
                <X size={15} />
              </button>
            </div>
            <div className="space-y-3">
              <label className="block text-xs text-[var(--studio-muted)]">
                New slug
                <input
                  className={cn(inputStyle(), "mt-1 w-full")}
                  value={duplicateDraft.newSlug}
                  onChange={(event) => setDuplicateDraft({ ...duplicateDraft, newSlug: event.target.value })}
                  placeholder="ep02-product-loop"
                />
              </label>
              <label className="block text-xs text-[var(--studio-muted)]">
                New title
                <input
                  className={cn(inputStyle(), "mt-1 w-full")}
                  value={duplicateDraft.newTitle}
                  onChange={(event) => setDuplicateDraft({ ...duplicateDraft, newTitle: event.target.value })}
                  placeholder="Make music that lives somewhere"
                />
              </label>
              <button
                type="button"
                className={cn(primaryButtonStyle(), "w-full")}
                disabled={!duplicateDraft.newSlug || !duplicateDraft.newTitle || duplicateMutation.isPending}
                onClick={() => duplicateMutation.mutate()}
              >
                Create duplicate
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {settingsShow ? (
        <div className={modalShellStyle()}>
          <div className={cn(panelStyle(), "max-w-2xl")}>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-lg font-semibold text-[var(--studio-text)]">Show Settings</div>
                <div className="text-xs text-[var(--studio-muted)]">{settingsShow}</div>
              </div>
              <button
                type="button"
                className={iconButtonStyle()}
                onClick={() => {
                  setSettingsShow(null);
                  setSettingsDefaults(null);
                }}
                title="Close"
              >
                <X size={15} />
              </button>
            </div>
            {settingsDefaults ? (
              <div className="grid gap-4">
                <div>
                  <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[var(--studio-text)]">
                    <Mic2 size={14} className="text-[var(--studio-purple)]" />
                    Cast voices
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(defaultsWithFallback(settingsDefaults).cast).map(([speaker, voice]) => (
                      <label key={speaker} className="text-xs uppercase tracking-[0.12em] text-[var(--studio-muted)]">
                        {speaker}
                        <select
                          className={cn(selectStyle(), "mt-1 w-full")}
                          value={voice}
                          onChange={(event) =>
                            setSettingsDefaults((current) => ({
                              ...defaultsWithFallback(current ?? undefined),
                              cast: { ...defaultsWithFallback(current ?? undefined).cast, [speaker]: event.target.value },
                            }))
                          }
                        >
                          <option value="">Voice</option>
                          {voicesQuery.data?.map((voiceOption) => (
                            <option key={voiceOption.id} value={voiceOption.id}>
                              {voiceOption.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    ))}
                  </div>
                </div>
                <label className="block text-xs text-[var(--studio-muted)]">
                  Music bed
                  <select
                    className={cn(selectStyle(), "mt-1 w-full")}
                    value={defaultsWithFallback(settingsDefaults).music_bed}
                    onChange={(event) =>
                      setSettingsDefaults((current) => ({
                        ...defaultsWithFallback(current ?? undefined),
                        music_bed: event.target.value,
                      }))
                    }
                  >
                    <option value="">Music bed</option>
                    {musicQuery.data?.map((bed) => (
                      <option key={bed.path} value={bed.filename}>
                        {bed.title}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    ["DDPM", "ddpm_steps", 1, 100, 1],
                    ["CFG", "cfg_scale", 0.1, 3, 0.1],
                    ["Minutes", "target_minutes", 1, 30, 1],
                  ].map(([label, key, min, max, step]) => (
                    <label key={String(key)} className="text-xs text-[var(--studio-muted)]">
                      <div className="mb-1 flex items-center justify-between">
                        <span>{String(label)}</span>
                        <span className="text-[var(--studio-text)]">{String(defaultsWithFallback(settingsDefaults)[key as keyof ShowDefaults] ?? "")}</span>
                      </div>
                      <input
                        type="range"
                        className="w-full accent-[var(--studio-purple)]"
                        min={Number(min)}
                        max={Number(max)}
                        step={Number(step)}
                        value={Number(defaultsWithFallback(settingsDefaults)[key as keyof ShowDefaults] ?? min)}
                        onChange={(event) =>
                          setSettingsDefaults((current) => ({
                            ...defaultsWithFallback(current ?? undefined),
                            [String(key)]: Number(event.target.value),
                          }))
                        }
                      />
                    </label>
                  ))}
                </div>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    ["Intro hot", "intro_hot_s"],
                    ["Intro fade", "intro_fade_s"],
                    ["Outro", "outro_s"],
                  ].map(([label, key]) => (
                    <label key={key} className="text-xs text-[var(--studio-muted)]">
                      {label}
                      <input
                        className={cn(inputStyle(), "mt-1 w-full")}
                        type="number"
                        step={0.5}
                        value={Number(defaultsWithFallback(settingsDefaults)[key as keyof ShowDefaults] ?? 0)}
                        onChange={(event) =>
                          setSettingsDefaults((current) => ({
                            ...defaultsWithFallback(current ?? undefined),
                            [key]: Number(event.target.value),
                          }))
                        }
                      />
                    </label>
                  ))}
                </div>
                <label className="block text-xs text-[var(--studio-muted)]">
                  Pronunciation notes
                  <textarea
                    className="mt-1 min-h-24 w-full resize-none rounded-md border border-[var(--studio-border)] bg-[var(--studio-input)] p-2 text-sm text-[var(--studio-text)] outline-none focus:border-[var(--studio-purple)]"
                    value={defaultsWithFallback(settingsDefaults).pronunciation_notes}
                    onChange={(event) =>
                      setSettingsDefaults((current) => ({
                        ...defaultsWithFallback(current ?? undefined),
                        pronunciation_notes: event.target.value,
                      }))
                    }
                  />
                </label>
                <button
                  type="button"
                  className={cn(primaryButtonStyle(), "w-full")}
                  disabled={saveDefaultsMutation.isPending}
                  onClick={() => saveDefaultsMutation.mutate()}
                >
                  Save settings
                </button>
              </div>
            ) : (
              <div className="p-4 text-sm text-[var(--studio-muted)]">Loading settings...</div>
            )}
          </div>
        </div>
      ) : null}

      {aiModalOpen ? (
        <div className={modalShellStyle()}>
          <div className={panelStyle()}>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-lg font-semibold text-[var(--studio-text)]">AI Edit</div>
                <div className="text-xs text-[var(--studio-muted)]">
                  {aiTarget?.kind === "selection" ? "Selected text" : aiTarget?.kind === "section" ? aiTarget.sectionId : "No target"}
                </div>
              </div>
              <button
                type="button"
                className={iconButtonStyle()}
                onClick={() => setAiModalOpen(false)}
                title="Close"
              >
                <X size={15} />
              </button>
            </div>
            <textarea
              className="min-h-24 w-full resize-none rounded-md border border-[var(--studio-border)] bg-[var(--studio-input)] p-2 text-sm text-[var(--studio-text)] outline-none placeholder:text-[var(--studio-muted)] focus:border-[var(--studio-purple)]"
              value={aiInstruction}
              onChange={(event) => setAiInstruction(event.target.value)}
              placeholder="make this punchier"
              autoFocus
            />
            <button
              type="button"
              className={cn(primaryButtonStyle(), "mt-3 w-full")}
              disabled={!aiInstruction || !aiTarget || aiMutation.isPending}
              onClick={() => aiMutation.mutate()}
            >
              Run edit
            </button>
            {pendingEdit ? (
              <div className="mt-3 rounded-md border border-[var(--studio-border)] bg-black/20">
                <div className="flex items-center justify-between border-b border-[var(--studio-border)] px-2 py-2 text-xs text-[var(--studio-secondary)]">
                  <span
                    className={cn(
                      pendingEdit.source === "local-fallback"
                        ? "border border-amber-300/30 bg-amber-300/10 px-2 py-0.5 text-amber-100"
                        : "text-[var(--studio-secondary)]",
                    )}
                  >
                    {pendingEdit.source === "local-fallback" ? "local fallback" : pendingEdit.source}
                  </span>
                  <button
                    type="button"
                    className="h-7 rounded-md border border-[rgba(94,234,212,0.36)] bg-[rgba(94,234,212,0.10)] px-3 text-[var(--studio-success)]"
                    onClick={approvePendingEdit}
                  >
                    Approve
                  </button>
                </div>
                <pre className="max-h-56 overflow-auto whitespace-pre-wrap p-2 text-xs leading-5 text-[var(--studio-secondary)]">
                  {pendingEdit.diff || "No text changes returned."}
                </pre>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {episodeSwitcherOpen ? (
        <div className={modalShellStyle()}>
          <div className={panelStyle()}>
            <div className="mb-3 flex items-center gap-2 rounded-md border border-[var(--studio-border)] bg-[var(--studio-input)] px-2">
              <Search size={15} className="text-[var(--studio-purple)]" />
              <input
                className="h-10 min-w-0 flex-1 bg-transparent text-sm text-[var(--studio-text)] outline-none placeholder:text-[var(--studio-muted)]"
                value={episodeSearch}
                onChange={(event) => setEpisodeSearch(event.target.value)}
                placeholder="Switch episode"
                autoFocus
              />
            </div>
            <div className="max-h-80 overflow-y-auto">
              {filteredEpisodeChoices.map(({ show, season, episode }) => (
                <button
                  key={`${show.slug}/${season.slug}/${episode.slug}`}
                  type="button"
                  className="flex w-full items-center gap-3 border-b border-white/5 px-2 py-3 text-left hover:bg-white/[0.04]"
                  onClick={() => {
                    setSelection({ show: show.slug, season: season.slug, episode: episode.slug });
                    setEpisodeSwitcherOpen(false);
                    setEpisodeSearch("");
                  }}
                >
                  <FileText size={15} className="text-[var(--studio-purple)]" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm text-[var(--studio-text)]">{episode.title}</span>
                    <span className="block truncate text-xs text-[var(--studio-muted)]">
                      {show.title} / {season.title} / {episode.slug}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      {shortcutOverlayOpen ? (
        <div className={modalShellStyle()}>
          <div className={cn(panelStyle(), "max-w-lg")}>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-lg font-semibold text-[var(--studio-text)]">Keyboard Shortcuts</div>
                <div className="text-xs text-[var(--studio-muted)]">Studio actions stay close to the editor.</div>
              </div>
              <button type="button" className={iconButtonStyle()} onClick={() => setShortcutOverlayOpen(false)} title="Close">
                <X size={15} />
              </button>
            </div>
            <div className="grid gap-2 text-sm">
              {[
                [shortcutLabel("S"), "Save script"],
                [shortcutLabel("R"), "Render current section"],
                [shortcutLabel("Enter"), "Play section, or send chat when Chat is active"],
                [shortcutLabel("E"), "Edit selection with AI"],
                [shortcutLabel("K"), "Switch episode"],
                [shortcutLabel("1-5"), "Switch right rail tab"],
                ["Space", "Play or pause audio"],
                ["J / K", "Scrub audio backward / forward"],
                ["M", "Add annotation at playhead"],
              ].map(([keys, label]) => (
                <div key={keys} className="flex items-center justify-between rounded-md bg-white/[0.04] px-3 py-2">
                  <span className="text-[var(--studio-secondary)]">{label}</span>
                  <kbd className="rounded border border-[var(--studio-border)] bg-black/25 px-2 py-1 font-mono text-xs text-[var(--studio-text)]">
                    {keys}
                  </kbd>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      {toast ? (
        <div className="fixed bottom-14 left-3 z-50 max-w-md rounded-md border border-[rgba(255,200,117,0.34)] bg-[rgba(255,200,117,0.10)] px-3 py-2 text-xs leading-5 text-[var(--studio-gold)]">
          {toast}
        </div>
      ) : null}

      {busy ? (
        <div className="pointer-events-none fixed bottom-3 left-3 rounded-md border border-[rgba(163,107,255,0.36)] bg-[rgba(163,107,255,0.10)] px-3 py-2 text-xs text-[var(--studio-text)]">
          Working...
        </div>
      ) : null}
    </main>
  );
}
