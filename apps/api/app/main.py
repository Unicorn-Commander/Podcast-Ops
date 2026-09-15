from __future__ import annotations

import asyncio
import contextlib
import difflib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
import yaml
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

API_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(os.environ.get("PODCAST_OPS_ROOT", API_DIR.parents[1])).resolve()
SHOWS_DIR = PROJECT_ROOT / "shows"
TOOLS_DIR = PROJECT_ROOT / "tools"
STATE_FILE = "episode.state.json"
ANNOTATIONS_FILE = "episode.annotations.jsonl"
CHAT_FILE = "episode.chat.jsonl"
NOTES_FILE = "notes.md"

VIBEVOICE_URL = os.environ.get("VIBEVOICE_URL", "http://magicunicorn:8885").rstrip("/")
BRIGADE_BASE_URL = os.environ.get("BRIGADE_BASE_URL", "").rstrip("/")
BRIGADE_API_KEY = os.environ.get("BRIGADE_API_KEY", "")
BRIGADE_SCRIPT_AGENT = os.environ.get("BRIGADE_SCRIPT_AGENT", "podcast-scriptwriter")
BRIGADE_CHAT_AGENTS = {
    "majik": "Main producer agent; knows the Magic's Studio ecosystem.",
    "the-general": "Strategic and high-level direction.",
    "gunny": "Pragmatic implementation and execution.",
    "gflow": "Operational process and workflow.",
}
MUSIC_CATALOG_PATH = Path(
    os.environ.get(
        "MUSIC_CATALOG_PATH",
        "/Volumes/Studio Storage/Majiks-Lyric-Videos/output",
    )
)
VOICE_MOUNT_REMOTE = os.environ.get(
    "VIBEVOICE_VOICE_MOUNT_REMOTE",
    "magicunicorn:/opt/vibevoice-models/voices",
)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SECTION_RE = re.compile(r"^##\s+§\s*([A-Za-z0-9_.-]+)\s*[·•.\-]?\s*(.*?)\s*$", re.MULTILINE)
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'.-]*")

app = FastAPI(title="Podcast-Ops Studio API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):(3000|3001|3002|3003|3004)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def bearer_token_when_configured(request: Request, call_next):
    token = os.environ.get("PODCAST_OPS_API_TOKEN")
    if token and request.url.path not in {"/health"}:
        expected = f"Bearer {token}"
        if request.headers.get("authorization") != expected:
            raise HTTPException(status_code=401, detail="invalid bearer token")
    return await call_next(request)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug_to_title(slug: str) -> str:
    return slug.replace("_", "-").replace("-", " ").title()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


def ensure_under(root: Path, candidate: Path) -> Path:
    root_resolved = root.resolve()
    candidate_resolved = candidate.resolve()
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes project root") from exc
    return candidate_resolved


def has_seasons(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(child.is_dir() and (child / "episodes").is_dir() for child in path.iterdir())


def iter_show_dirs() -> list[tuple[str | None, Path]]:
    shows: list[tuple[str | None, Path]] = []
    if not SHOWS_DIR.exists():
        return shows
    for first in sorted(SHOWS_DIR.iterdir()):
        if first.name.startswith(".") or not first.is_dir():
            continue
        if has_seasons(first):
            shows.append((None, first))
            continue
        for show_dir in sorted(first.iterdir()):
            if show_dir.name.startswith(".") or not show_dir.is_dir():
                continue
            if has_seasons(show_dir):
                shows.append((first.name, show_dir))
    return shows


def find_show_dir(show: str) -> tuple[str | None, Path]:
    for tenant, show_dir in iter_show_dirs():
        if show_dir.name == show:
            return tenant, show_dir
    raise HTTPException(status_code=404, detail=f"show not found: {show}")


def episode_dir(show: str, season: str, ep: str) -> Path:
    _, show_dir = find_show_dir(show)
    path = show_dir / season / "episodes" / ep
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=404, detail=f"episode not found: {show}/{season}/{ep}")
    return ensure_under(PROJECT_ROOT, path)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_state(ep_dir: Path) -> dict[str, Any]:
    state = read_json(ep_dir / STATE_FILE, {})
    state.setdefault("renders", [])
    state.setdefault("mixes", [])
    state.setdefault("script_saves", [])
    state.setdefault("updated_at", now_iso())
    return state


def save_state(ep_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    write_json(ep_dir / STATE_FILE, state)


def read_annotations(ep_dir: Path) -> list[dict[str, Any]]:
    path = ep_dir / ANNOTATIONS_FILE
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        with contextlib.suppress(json.JSONDecodeError):
            rows.append(json.loads(line))
    return rows


def append_annotation(ep_dir: Path, row: dict[str, Any]) -> None:
    with (ep_dir / ANNOTATIONS_FILE).open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        with contextlib.suppress(json.JSONDecodeError):
            rows.append(json.loads(line))
    return rows


def append_chat_message(ep_dir: Path, row: dict[str, Any]) -> None:
    with (ep_dir / CHAT_FILE).open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def parse_frontmatter(script: str) -> tuple[dict[str, Any], str, str]:
    match = FRONTMATTER_RE.match(script)
    if not match:
        return {}, "", script
    raw = match.group(1)
    try:
        parsed = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        parsed = {}
    return parsed, script[: match.end()], script[match.end() :]


def parse_frontmatter_raw(script: str) -> tuple[dict[str, Any], str, str]:
    match = FRONTMATTER_RE.match(script)
    if not match:
        return {}, "", script
    raw = match.group(1)
    try:
        parsed = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        parsed = {}
    return parsed, raw, script[match.end() :]


def read_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return yaml.safe_load(path.read_text()) or default
    except yaml.YAMLError:
        return default


def show_config_path(show_dir: Path) -> Path:
    return show_dir / "show.yaml"


def load_show_config(show_dir: Path) -> dict[str, Any]:
    data = read_yaml(show_config_path(show_dir), {})
    return data if isinstance(data, dict) else {}


def extract_cast_voices(raw_frontmatter: str, parsed_frontmatter: dict[str, Any]) -> dict[str, str]:
    voices: dict[str, str] = {}
    for match in re.finditer(
        r"^\s{2,}([A-Za-z0-9_-]+):\s*[^#\n]*?(?:\s*#\s*voice:\s*([A-Za-z0-9_-]+))",
        raw_frontmatter,
        re.MULTILINE,
    ):
        voices[match.group(1)] = match.group(2)
    cast = parsed_frontmatter.get("cast")
    if isinstance(cast, dict):
        for speaker, value in cast.items():
            if speaker in voices:
                continue
            if isinstance(value, dict) and value.get("voice"):
                voices[str(speaker)] = str(value["voice"])
    return voices


def infer_show_defaults(show_dir: Path) -> dict[str, Any]:
    scripts = sorted(show_dir.glob("*/episodes/*/script.md"))
    if not scripts:
        return {}
    script = scripts[0].read_text()
    frontmatter, raw_frontmatter, _ = parse_frontmatter_raw(script)
    defaults: dict[str, Any] = {}
    for key in (
        "cast",
        "music_bed",
        "ddpm_steps",
        "cfg_scale",
        "target_minutes",
        "intro_hot_s",
        "intro_fade_s",
        "outro_s",
        "pronunciation_notes",
    ):
        if key in frontmatter:
            defaults[key] = frontmatter[key]
    cast = frontmatter.get("cast")
    if isinstance(cast, dict):
        voices = extract_cast_voices(raw_frontmatter, frontmatter)
        if voices:
            defaults["cast"] = {speaker: voices.get(str(speaker), "") for speaker in cast}
    return defaults


def get_show_defaults(show_dir: Path) -> dict[str, Any]:
    config = load_show_config(show_dir)
    defaults = config.get("defaults")
    if isinstance(defaults, dict):
        return defaults
    return infer_show_defaults(show_dir)


def scalar_yaml_line(key: str, value: Any) -> list[str]:
    dumped = yaml.safe_dump(
        {key: value},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).strip()
    if dumped.endswith("\n..."):
        dumped = dumped[:-4].rstrip()
    return dumped.splitlines()


def dump_script_frontmatter(data: dict[str, Any], cast_voices: dict[str, str]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if key == "cast" and isinstance(value, dict):
            lines.append("cast:")
            for speaker, role_value in value.items():
                role = "host"
                if isinstance(role_value, str):
                    role = role_value.split("#", 1)[0].strip() or "host"
                elif isinstance(role_value, dict):
                    role = str(role_value.get("role") or "host")
                voice = cast_voices.get(str(speaker), "")
                if voice:
                    lines.append(f"  {speaker}: {role:<10} # voice: {voice}")
                else:
                    lines.append(f"  {speaker}: {role}")
            continue
        if isinstance(value, str) and "\n" in value:
            lines.append(f"{key}: |")
            for row in value.rstrip("\n").splitlines():
                lines.append(f"  {row}")
            if value.endswith("\n"):
                lines.append("")
            continue
        lines.extend(scalar_yaml_line(key, value))
    return "\n".join(lines).rstrip() + "\n"


def merged_episode_frontmatter(
    source_frontmatter: dict[str, Any],
    raw_frontmatter: str,
    show_defaults: dict[str, Any],
    *,
    new_slug: str,
    new_title: str,
) -> str:
    data = dict(source_frontmatter)
    for key in (
        "music_bed",
        "ddpm_steps",
        "cfg_scale",
        "target_minutes",
        "intro_hot_s",
        "intro_fade_s",
        "outro_s",
        "pronunciation_notes",
    ):
        value = show_defaults.get(key)
        if value not in (None, ""):
            data[key] = value

    cast_voices = extract_cast_voices(raw_frontmatter, source_frontmatter)
    cast_defaults = show_defaults.get("cast")
    source_cast = data.get("cast")
    if isinstance(cast_defaults, dict):
        next_cast: dict[str, Any] = {}
        if isinstance(source_cast, dict):
            next_cast.update(source_cast)
        for speaker, voice in cast_defaults.items():
            next_cast.setdefault(str(speaker), "host")
            if voice not in (None, ""):
                cast_voices[str(speaker)] = str(voice)
        data["cast"] = next_cast

    data["slug"] = new_slug
    data["title"] = new_title
    data["status"] = "draft"
    data["last_updated"] = datetime.now(timezone.utc).date().isoformat()
    return dump_script_frontmatter(data, cast_voices)


def split_sections(script: str) -> list[dict[str, Any]]:
    _, _, body = parse_frontmatter(script)
    matches = list(SECTION_RE.finditer(body))
    sections: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        header = match.group(0)
        number = match.group(1)
        line = body[:start].count("\n") + 1
        sections.append(
            {
                "id": f"§{number}",
                "number": number,
                "index": index,
                "title": match.group(2).strip(),
                "line": line,
                "header": header,
                "markdown": body[start:end].strip() + "\n",
            }
        )
    return sections


def normalize_section_id(section: str) -> str:
    section = str(section).strip()
    if section.lower().startswith("section-"):
        with contextlib.suppress(ValueError):
            return f"index:{int(section.split('-', 1)[1])}"
    return section if section.startswith("§") else f"§{section}"


def script_metrics(script: str) -> dict[str, Any]:
    frontmatter, _, body = parse_frontmatter(script)
    cleaned = re.sub(r"^---.*?---", "", script, flags=re.DOTALL)
    cleaned = re.sub(r"^#+\s+.*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\*\*[A-Z0-9_ -]+:\*\*\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\[[^\]]+\]", "", cleaned)
    words = WORD_RE.findall(cleaned)
    word_count = len(words)
    duration_minutes = word_count / 165 if word_count else 0
    render_minutes = duration_minutes * 1.35
    return {
        "frontmatter": frontmatter,
        "word_count": word_count,
        "estimated_audio_minutes": round(duration_minutes, 1),
        "estimated_render_minutes": round(render_minutes, 1),
        "sections": split_sections(script),
        "speakers": sorted({m.group(1) for m in re.finditer(r"^\*\*([A-Z0-9_ -]+):\*\*", body, re.MULTILINE)}),
    }


def audio_kind(name: str) -> str:
    lower = name.lower()
    if "final" in lower:
        return "final"
    if "nomusic" in lower or "no-music" in lower:
        return "nomusic"
    if "voice-only" in lower or "voice_only" in lower:
        return "voice"
    return "audio"


def file_duration(path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )
        return round(float(result.stdout.strip()), 2)
    except (subprocess.SubprocessError, ValueError):
        return None


def list_audio_files(ep_dir: Path, show: str, season: str, ep: str) -> list[dict[str, Any]]:
    audio_dir = ep_dir / "audio"
    if not audio_dir.exists():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted(audio_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_dir() or path.suffix.lower() not in {".wav", ".mp3", ".m4a", ".flac"}:
            continue
        stat = path.stat()
        files.append(
            {
                "filename": path.name,
                "kind": audio_kind(path.name),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "duration_s": file_duration(path),
                "url": f"/shows/{show}/seasons/{season}/episodes/{ep}/audio/{path.name}",
            }
        )
    return files


def episode_audio_prefix(script: str, ep_slug: str, version: str) -> str:
    frontmatter, _, _ = parse_frontmatter(script)
    show_title = str(frontmatter.get("show") or "")
    initials = "".join(word[0] for word in re.findall(r"[A-Za-z0-9]+", show_title)).lower()
    initials = initials or slugify(show_title or ep_slug)[:8] or "episode"
    episode_no = frontmatter.get("episode")
    if isinstance(episode_no, int):
        ep_part = f"ep{episode_no:02d}"
    else:
        ep_part = ep_slug.split("-", 1)[0] if ep_slug.startswith("ep") else ep_slug
    return f"{initials}-{ep_part}-{version}"


class RenderRequest(BaseModel):
    version: str = Field(default_factory=lambda: f"v{int(time.time())}")
    ddpm_steps: int = 50
    cfg_scale: float = 1.3
    sections: Literal["all"] | list[str] = "all"
    model_name: str = "vibevoice-7b"


class MixRequest(BaseModel):
    voice_wav: str
    music_bed: str
    mode: Literal["music_under_voice", "music_off"] = "music_under_voice"
    intro_hot_s: float = 3.5
    intro_fade_s: float = 4.0
    outro_s: float = 7.0
    master_lufs: float = -16


class AnnotationRequest(BaseModel):
    version: str
    time_s: float
    text: str
    line: int | None = None
    section: str | None = None


class MusicExtractRequest(BaseModel):
    source_mp4: str
    start_s: float = 0
    duration_s: float = 33
    slug: str


class AIScriptEditRequest(BaseModel):
    current_script: str
    instruction: str
    model: str = "claude-3.5-haiku"


class AIGenerateScriptRequest(BaseModel):
    topic: str
    show: str
    format: str = "documentary-2host"
    target_minutes: int = 9
    model: str = "brigade:podcast-scriptwriter"


class OpenPathRequest(BaseModel):
    filename: str


class DuplicateEpisodeRequest(BaseModel):
    new_slug: str
    new_title: str
    carry_body: bool = False


class ShowDefaultsRequest(BaseModel):
    slug: str | None = None
    title: str | None = None
    defaults: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    agent: str = "majik"
    messages: list[dict[str, str]]
    episode_context: dict[str, Any] | None = None
    stream: bool = True


@dataclass
class JobRecord:
    id: str
    kind: str
    show: str
    season: str
    episode: str
    status: str
    params: dict[str, Any]
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    started_at: str | None = None
    completed_at: str | None = None
    returncode: int | None = None
    log: list[str] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)
    error: str | None = None

    def add_log(self, line: str) -> None:
        self.log.append(line.rstrip())
        self.updated_at = now_iso()

    def public(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["eta_s"] = estimate_job_eta_s(self)
        payload["progress_pct"] = estimate_job_progress_pct(self)
        return payload


JOBS: dict[str, JobRecord] = {}
JOB_PROCESSES: dict[str, asyncio.subprocess.Process] = {}
RENDER_REQUESTS: dict[str, RenderRequest] = {}
RENDER_QUEUE: asyncio.Queue[str] | None = None
RENDER_WORKER_TASK: asyncio.Task[None] | None = None


class JobCancelled(RuntimeError):
    pass


def job_created_ts(job: JobRecord) -> float:
    with contextlib.suppress(ValueError):
        return datetime.fromisoformat(job.created_at).timestamp()
    return 0


def estimate_job_total_s(job: JobRecord) -> int:
    try:
        ep_path = episode_dir(job.show, job.season, job.episode)
        script = (ep_path / "script.md").read_text()
        if isinstance(job.params.get("sections"), list):
            parts = selected_sections(script, [str(item) for item in job.params["sections"]])
            words = sum(len(WORD_RE.findall(part["markdown"])) for part in parts)
        else:
            words = script_metrics(script)["word_count"]
    except Exception:
        words = 900
    ddpm = int(job.params.get("ddpm_steps") or 50)
    audio_minutes = max(words / 165, 0.35)
    render_multiplier = max(ddpm, 1) / 50
    return max(45, int(audio_minutes * 60 * 1.35 * render_multiplier))


def estimate_job_eta_s(job: JobRecord) -> int | None:
    if job.status in {"completed", "failed", "cancelled"}:
        return 0
    total = estimate_job_total_s(job)
    if job.status == "running" and job.started_at:
        with contextlib.suppress(ValueError):
            elapsed = time.time() - datetime.fromisoformat(job.started_at).timestamp()
            return max(1, int(total - elapsed))
    return total


def estimate_job_progress_pct(job: JobRecord) -> int:
    if job.status == "completed":
        return 100
    if job.status in {"failed", "cancelled"}:
        return 0
    if job.status != "running" or not job.started_at:
        return 0
    total = max(estimate_job_total_s(job), 1)
    with contextlib.suppress(ValueError):
        elapsed = time.time() - datetime.fromisoformat(job.started_at).timestamp()
        return max(1, min(95, int((elapsed / total) * 100)))
    return 0


async def render_worker() -> None:
    assert RENDER_QUEUE is not None
    while True:
        job_id = await RENDER_QUEUE.get()
        try:
            job = JOBS.get(job_id)
            request = RENDER_REQUESTS.get(job_id)
            if not job or not request or job.status == "cancelled":
                continue
            await run_render_job(job_id, request)
        finally:
            RENDER_QUEUE.task_done()


def ensure_render_worker() -> asyncio.Queue[str]:
    global RENDER_QUEUE, RENDER_WORKER_TASK
    if RENDER_QUEUE is None:
        RENDER_QUEUE = asyncio.Queue()
    if RENDER_WORKER_TASK is None or RENDER_WORKER_TASK.done():
        RENDER_WORKER_TASK = asyncio.create_task(render_worker())
    return RENDER_QUEUE


async def run_logged_process(job: JobRecord, cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
    job.add_log("$ " + " ".join(cmd))
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    JOB_PROCESSES[job.id] = process
    assert process.stdout is not None
    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            job.add_log(line.decode(errors="replace").rstrip())
        return await process.wait()
    finally:
        JOB_PROCESSES.pop(job.id, None)


async def concat_section_wavs(job: JobRecord, section_dir: Path, output_wav: Path, silence_s: float = 0.6) -> None:
    wav_paths = sorted(section_dir.glob("section-*.wav"))
    if not wav_paths:
        raise RuntimeError(f"no section WAVs found in {section_dir}")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as list_file:
        list_path = Path(list_file.name)
        silence_path = list_path.with_suffix(".silence.wav")
        silence_cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-t",
            str(silence_s),
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-c:a",
            "pcm_s16le",
            str(silence_path),
        ]
        rc = await run_logged_process(job, silence_cmd, cwd=PROJECT_ROOT, env=os.environ.copy())
        if job.status == "cancelled":
            raise JobCancelled("render cancelled")
        if rc != 0:
            raise RuntimeError("failed to create section silence")
        for index, path in enumerate(wav_paths):
            list_file.write(f"file '{path}'\n")
            if index < len(wav_paths) - 1:
                list_file.write(f"file '{silence_path}'\n")
    concat_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        str(output_wav),
    ]
    try:
        rc = await run_logged_process(job, concat_cmd, cwd=PROJECT_ROOT, env=os.environ.copy())
        if job.status == "cancelled":
            raise JobCancelled("render cancelled")
        if rc != 0:
            raise RuntimeError("failed to concatenate section WAVs")
    finally:
        list_path.unlink(missing_ok=True)
        silence_path.unlink(missing_ok=True)


def selected_sections(script: str, requested: list[str]) -> list[dict[str, Any]]:
    sections = split_sections(script)
    requested_ids = {normalize_section_id(item) for item in requested}
    picked: list[dict[str, Any]] = []
    for section in sections:
        if section["id"] in requested_ids or f"index:{section['index']}" in requested_ids:
            picked.append(section)
    missing = requested_ids - {s["id"] for s in picked} - {f"index:{s['index']}" for s in picked}
    if missing:
        raise HTTPException(status_code=400, detail=f"unknown sections: {', '.join(sorted(missing))}")
    return picked


def seed_section_dir(target_section_dir: Path, audio_dir: Path) -> bool:
    if target_section_dir.exists() and list(target_section_dir.glob("section-*.wav")):
        return True
    candidates = sorted(
        [path for path in audio_dir.glob("*.sections") if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return False
    shutil.copytree(candidates[0], target_section_dir, dirs_exist_ok=True)
    return True


async def run_render_job(job_id: str, request: RenderRequest) -> None:
    job = JOBS[job_id]
    if job.status == "cancelled":
        return
    job.status = "running"
    job.started_at = now_iso()
    ep_dir = episode_dir(job.show, job.season, job.episode)
    script_path = ep_dir / "script.md"
    script = script_path.read_text()
    audio_dir = ep_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    prefix = episode_audio_prefix(script, job.episode, request.version)
    output_wav = audio_dir / f"{prefix}-voice-only.wav"
    section_dir = audio_dir / f"{output_wav.stem}.sections"
    env = os.environ.copy()
    env["VIBEVOICE_DDPM_STEPS"] = str(request.ddpm_steps)
    env["VIBEVOICE_CFG_SCALE"] = str(request.cfg_scale)
    env.setdefault("PYTHONUNBUFFERED", "1")
    render_script = TOOLS_DIR / "audio" / "render_episode.py"

    try:
        if request.sections == "all":
            cmd = [
                sys.executable,
                str(render_script),
                str(script_path),
                str(output_wav),
                "--host",
                VIBEVOICE_URL,
                "--keep-sections",
            ]
            rc = await run_logged_process(job, cmd, cwd=PROJECT_ROOT, env=env)
            if job.status == "cancelled":
                raise JobCancelled("render cancelled")
            if rc != 0:
                raise RuntimeError(f"render failed with exit code {rc}")
        else:
            has_section_cache = seed_section_dir(section_dir, audio_dir)
            if not has_section_cache:
                section_dir.mkdir(parents=True, exist_ok=True)
                job.add_log(
                    "[section-render] no prior section cache found; "
                    "writing an isolated section render for review"
                )
            frontmatter, frontmatter_block, _ = parse_frontmatter(script)
            rendered_count = 0
            for section in selected_sections(script, request.sections):
                with tempfile.TemporaryDirectory(prefix="podcast-ops-section-") as tempdir:
                    tempdir_path = Path(tempdir)
                    temp_script = tempdir_path / "script.md"
                    temp_output = tempdir_path / "section.wav"
                    temp_script.write_text(frontmatter_block + "\n" + section["markdown"])
                    cmd = [
                        sys.executable,
                        str(render_script),
                        str(temp_script),
                        str(temp_output),
                        "--host",
                        VIBEVOICE_URL,
                        "--keep-sections",
                    ]
                    job.add_log(
                        f"[section-render] rendering {section['id']} "
                        f"({frontmatter.get('show', job.show)})"
                    )
                    rc = await run_logged_process(job, cmd, cwd=PROJECT_ROOT, env=env)
                    if job.status == "cancelled":
                        raise JobCancelled("render cancelled")
                    if rc != 0:
                        raise RuntimeError(f"section {section['id']} render failed with exit code {rc}")
                    generated = tempdir_path / "section.sections" / "section-00.wav"
                    target_index = section["index"] if has_section_cache else rendered_count
                    target = section_dir / f"section-{target_index:02d}.wav"
                    shutil.copy2(generated, target)
                    verb = "swapped" if has_section_cache else "wrote"
                    job.add_log(f"[section-render] {verb} {section['id']} into {target.name}")
                    rendered_count += 1
            await concat_section_wavs(job, section_dir, output_wav)

        job.output_files = [str(output_wav.relative_to(ep_dir))]
        state = load_state(ep_dir)
        state["renders"].append(
            {
                "job_id": job.id,
                "status": "completed",
                "version": request.version,
                "params": request.model_dump(),
                "output": str(output_wav.relative_to(ep_dir)),
                "section_dir": str(section_dir.relative_to(ep_dir)),
                "started_at": job.started_at,
                "completed_at": now_iso(),
            }
        )
        save_state(ep_dir, state)
        job.status = "completed"
        job.returncode = 0
    except JobCancelled as exc:
        job.status = "cancelled"
        job.error = str(exc)
        job.returncode = -int(signal.SIGTERM)
        state = load_state(ep_dir)
        state["renders"].append(
            {
                "job_id": job.id,
                "status": "cancelled",
                "version": request.version,
                "params": request.model_dump(),
                "error": str(exc),
                "started_at": job.started_at,
                "completed_at": now_iso(),
            }
        )
        save_state(ep_dir, state)
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.returncode = 1
        job.add_log(f"[error] {exc}")
        state = load_state(ep_dir)
        state["renders"].append(
            {
                "job_id": job.id,
                "status": "failed",
                "version": request.version,
                "params": request.model_dump(),
                "error": str(exc),
                "started_at": job.started_at,
                "completed_at": now_iso(),
            }
        )
        save_state(ep_dir, state)
    finally:
        job.completed_at = now_iso()
        job.updated_at = now_iso()


def resolve_music_bed(name: str) -> Path:
    raw = Path(name)
    if raw.is_absolute() and raw.exists():
        return ensure_under(PROJECT_ROOT.parent.parent if str(raw).startswith("/Volumes") else PROJECT_ROOT, raw)
    candidates: list[Path] = []
    candidates.extend(PROJECT_ROOT.glob(f"assets/music-beds/{name}"))
    candidates.extend(SHOWS_DIR.glob(f"**/assets/music-beds/{name}"))
    candidates.extend(SHOWS_DIR.glob(f"**/audio/{name}"))
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    raise HTTPException(status_code=404, detail=f"music bed not found: {name}")


def find_catalog_track(source_mp4: str) -> Path:
    raw = Path(source_mp4)
    if raw.is_absolute() and raw.exists():
        return raw.resolve()
    candidates = list(MUSIC_CATALOG_PATH.glob(f"**/{source_mp4}"))
    if candidates:
        return candidates[0].resolve()
    raise HTTPException(status_code=404, detail=f"catalog track not found: {source_mp4}")


async def call_brigade(messages: list[dict[str, str]], model: str) -> tuple[str | None, str | None]:
    if not BRIGADE_BASE_URL or not BRIGADE_API_KEY:
        return None, "brigade_unconfigured"
    headers = {"Content-Type": "application/json"}
    headers["Authorization"] = f"Bearer {BRIGADE_API_KEY}"
    async with httpx.AsyncClient(timeout=10) as client:
        openai_url = f"{BRIGADE_BASE_URL}/openai/v1/chat/completions"
        try:
            response = await client.post(
                openai_url,
                headers=headers,
                json={"model": model, "messages": messages, "temperature": 0.4},
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"], None
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, httpx.RequestError):
            return None, "brigade_timeout"
        except Exception:
            agent_url = f"{BRIGADE_BASE_URL}/agents/{BRIGADE_SCRIPT_AGENT}/chat"
            try:
                response = await client.post(
                    agent_url,
                    headers=headers,
                    json={"model": model, "messages": messages},
                )
                response.raise_for_status()
                data = response.json()
                return data.get("content") or data.get("message") or json.dumps(data), None
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, httpx.RequestError):
                return None, "brigade_timeout"
            except Exception:
                return None, "brigade_error"


def strip_markdown_fence(text: str) -> str:
    match = re.search(r"```(?:markdown|md)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


def local_tighten_fallback(script: str, instruction: str) -> str:
    if "tight" not in instruction.lower() and "short" not in instruction.lower():
        return script
    replacements = {
        " actually ": " ",
        " genuinely ": " ",
        " really ": " ",
        " very ": " ",
        " just ": " ",
        " basically ": " ",
        " kind of ": " ",
        " sort of ": " ",
    }
    edited = script
    for src, dst in replacements.items():
        edited = edited.replace(src, dst)
    lines = [line.rstrip() for line in edited.splitlines()]
    return "\n".join(line for line in lines if line.strip() != "") + "\n"


def show_payload(show: str) -> dict[str, Any]:
    tenant, show_dir = find_show_dir(show)
    config = load_show_config(show_dir)
    return {
        "tenant": tenant,
        "slug": show_dir.name,
        "title": str(config.get("title") or config.get("name") or slug_to_title(show_dir.name)),
        "path": str(show_dir),
        "defaults": get_show_defaults(show_dir),
    }


def season_path(show: str, season: str) -> Path:
    _, show_dir = find_show_dir(show)
    path = show_dir / season
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=404, detail=f"season not found: {show}/{season}")
    return ensure_under(PROJECT_ROOT, path)


def episode_payload(show: str, season: str, ep: str) -> dict[str, Any]:
    ep_path = episode_dir(show, season, ep)
    script_path = ep_path / "script.md"
    script = script_path.read_text() if script_path.exists() else ""
    return {
        "show": show,
        "season": season,
        "episode": ep,
        "path": str(ep_path),
        "script": script,
        "metrics": script_metrics(script) if script else {},
        "audio": list_audio_files(ep_path, show, season, ep),
        "state": load_state(ep_path),
        "annotations": read_annotations(ep_path),
    }


def source_doc_path(show: str, season: str) -> Path | None:
    tenant, show_dir = find_show_dir(show)
    direct_candidates = [
        show_dir / season / "source" / "source-of-truth.md",
        show_dir / "source" / "source-of-truth.md",
    ]
    for candidate in direct_candidates:
        if candidate.exists() and candidate.is_file():
            return ensure_under(PROJECT_ROOT, candidate)

    # A Layer Below currently shares the Layer Above source pack.
    if tenant:
        tenant_dir = show_dir.parent
        for sibling in sorted(tenant_dir.iterdir()):
            candidate = sibling / season / "source" / "source-of-truth.md"
            if candidate.exists() and candidate.is_file():
                return ensure_under(PROJECT_ROOT, candidate)
    return None


def episode_context_dir(context: dict[str, Any] | None) -> Path | None:
    if not context:
        return None
    show = context.get("show")
    season = context.get("season")
    episode = context.get("episode")
    if not all(isinstance(item, str) and item for item in [show, season, episode]):
        return None
    with contextlib.suppress(HTTPException):
        return episode_dir(show, season, episode)
    return None


def chat_system_prompt(agent: str, context: dict[str, Any] | None) -> str:
    description = BRIGADE_CHAT_AGENTS.get(agent, BRIGADE_CHAT_AGENTS["majik"])
    context_json = json.dumps(context or {}, indent=2, sort_keys=True)[:12000]
    return (
        f"You are {agent}, a Podcast-Ops studio collaborator. {description}\n"
        "Be concise by default. Ground responses in the episode context. "
        "When suggesting script edits, provide replacement text that can be applied cleanly.\n\n"
        f"Episode context:\n{context_json}"
    )


def chat_sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "root": str(PROJECT_ROOT),
        "vibevoice_url": VIBEVOICE_URL,
        "brigade_configured": bool(BRIGADE_BASE_URL and BRIGADE_API_KEY),
    }


@app.get("/shows")
async def list_shows() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for tenant, show_dir in iter_show_dirs():
        seasons: list[dict[str, Any]] = []
        for season_dir in sorted(show_dir.iterdir()):
            episodes_dir = season_dir / "episodes"
            if not episodes_dir.is_dir():
                continue
            episodes = []
            for ep_dir in sorted(episodes_dir.iterdir()):
                if ep_dir.name.startswith(".") or not ep_dir.is_dir():
                    continue
                script_path = ep_dir / "script.md"
                title = slug_to_title(ep_dir.name)
                status_value = None
                if script_path.exists():
                    frontmatter, _, _ = parse_frontmatter(script_path.read_text())
                    title = str(frontmatter.get("title") or title)
                    status_value = frontmatter.get("status")
                audio_paths = [
                    path
                    for path in (ep_dir / "audio").glob("*")
                    if path.is_file() and path.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac"}
                ]
                last_rendered_at = None
                if audio_paths:
                    latest = max(audio_paths, key=lambda path: path.stat().st_mtime)
                    last_rendered_at = datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat()
                episodes.append(
                    {
                        "slug": ep_dir.name,
                        "title": title,
                        "has_script": script_path.exists(),
                        "status": status_value or ("ready" if audio_paths else "draft"),
                        "audio_count": len(audio_paths),
                        "last_rendered_at": last_rendered_at,
                    }
                )
            seasons.append(
                {
                    "slug": season_dir.name,
                    "title": slug_to_title(season_dir.name),
                    "episodes": episodes,
                }
            )
        result.append(
            {
                "tenant": tenant,
                "slug": show_dir.name,
                "title": slug_to_title(show_dir.name),
                "seasons": seasons,
            }
        )
    return result


@app.get("/shows/{show}")
async def get_show(show: str) -> dict[str, Any]:
    return show_payload(show)


@app.put("/shows/{show}/defaults")
async def put_show_defaults(show: str, request: Request) -> dict[str, Any]:
    _, show_dir = find_show_dir(show)
    payload = await request.json()
    defaults = payload.get("defaults") if isinstance(payload, dict) and "defaults" in payload else payload
    if not isinstance(defaults, dict):
        raise HTTPException(status_code=400, detail="defaults must be an object")
    config = load_show_config(show_dir)
    config["slug"] = str(config.get("slug") or show)
    config["title"] = str(payload.get("title") or config.get("title") or slug_to_title(show)) if isinstance(payload, dict) else slug_to_title(show)
    config["defaults"] = defaults
    show_config_path(show_dir).write_text(
        yaml.safe_dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False)
    )
    return {"ok": True, **show_payload(show)}


@app.get("/shows/{show}/seasons/{season}/source")
async def get_source_doc(show: str, season: str) -> dict[str, Any]:
    path = source_doc_path(show, season)
    if path is None:
        return {"content": None, "path": None}
    return {"content": path.read_text(), "path": str(path.relative_to(PROJECT_ROOT))}


@app.get("/shows/{show}/seasons/{season}/episodes/{ep}/script", response_class=PlainTextResponse)
async def get_script(show: str, season: str, ep: str) -> str:
    path = episode_dir(show, season, ep) / "script.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="script.md not found")
    return path.read_text()


@app.put("/shows/{show}/seasons/{season}/episodes/{ep}/script")
async def put_script(show: str, season: str, ep: str, request: Request) -> dict[str, Any]:
    ep_path = episode_dir(show, season, ep)
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
        script = payload.get("script", "")
    else:
        script = (await request.body()).decode()
    if not script.strip():
        raise HTTPException(status_code=400, detail="script cannot be empty")
    (ep_path / "script.md").write_text(script)
    state = load_state(ep_path)
    state["script_saves"].append({"timestamp": now_iso(), "bytes": len(script.encode())})
    save_state(ep_path, state)
    return {"ok": True, "metrics": script_metrics(script)}


@app.get("/shows/{show}/seasons/{season}/episodes/{ep}/notes", response_class=PlainTextResponse)
async def get_episode_notes(show: str, season: str, ep: str) -> str:
    path = episode_dir(show, season, ep) / NOTES_FILE
    return path.read_text() if path.exists() else ""


@app.put("/shows/{show}/seasons/{season}/episodes/{ep}/notes")
async def put_episode_notes(show: str, season: str, ep: str, request: Request) -> dict[str, Any]:
    ep_path = episode_dir(show, season, ep)
    notes = (await request.body()).decode()
    (ep_path / NOTES_FILE).write_text(notes)
    return {"ok": True, "bytes": len(notes.encode())}


@app.get("/shows/{show}/seasons/{season}/episodes/{ep}/chat")
async def get_episode_chat(show: str, season: str, ep: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = read_jsonl(episode_dir(show, season, ep) / CHAT_FILE)
    return rows[-max(1, min(limit, 200)) :]


@app.get("/shows/{show}/seasons/{season}/episodes/{ep}")
async def get_episode(show: str, season: str, ep: str) -> dict[str, Any]:
    return episode_payload(show, season, ep)


@app.post("/shows/{show}/seasons/{season}/episodes/{ep}/duplicate")
async def duplicate_episode(show: str, season: str, ep: str, request: DuplicateEpisodeRequest) -> dict[str, Any]:
    source_dir = episode_dir(show, season, ep)
    source_script = source_dir / "script.md"
    if not source_script.exists():
        raise HTTPException(status_code=404, detail="source script.md not found")
    new_slug = slugify(request.new_slug)
    if new_slug != request.new_slug:
        raise HTTPException(status_code=400, detail=f"new_slug must be URL-safe; try {new_slug}")
    target_dir = season_path(show, season) / "episodes" / new_slug
    target_dir = ensure_under(PROJECT_ROOT, target_dir)
    if target_dir.exists():
        raise HTTPException(status_code=409, detail=f"episode already exists: {new_slug}")
    source_text = source_script.read_text()
    frontmatter, raw_frontmatter, body = parse_frontmatter_raw(source_text)
    if not raw_frontmatter:
        raise HTTPException(status_code=400, detail="source script has no YAML frontmatter")
    _, show_dir = find_show_dir(show)
    merged_frontmatter = merged_episode_frontmatter(
        frontmatter,
        raw_frontmatter,
        get_show_defaults(show_dir),
        new_slug=new_slug,
        new_title=request.new_title,
    )
    target_dir.mkdir(parents=True, exist_ok=False)
    (target_dir / "audio").mkdir(exist_ok=True)
    next_body = body.strip() + "\n" if request.carry_body else "## § 0 · Cold open\n\n"
    (target_dir / "script.md").write_text(f"---\n{merged_frontmatter}---\n\n{next_body}")
    save_state(target_dir, {"renders": [], "mixes": [], "script_saves": [{"timestamp": now_iso(), "bytes": len((target_dir / "script.md").read_bytes())}]})
    return episode_payload(show, season, new_slug)


@app.get("/shows/{show}/seasons/{season}/episodes/{ep}/audio/{filename:path}")
async def get_episode_audio(show: str, season: str, ep: str, filename: str):
    ep_path = episode_dir(show, season, ep)
    path = ensure_under(ep_path / "audio", ep_path / "audio" / filename)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="audio file not found")
    return FileResponse(path)


@app.post("/shows/{show}/seasons/{season}/episodes/{ep}/render")
async def start_render(show: str, season: str, ep: str, request: RenderRequest) -> dict[str, Any]:
    episode_dir(show, season, ep)
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = JobRecord(
        id=job_id,
        kind="render",
        show=show,
        season=season,
        episode=ep,
        status="queued",
        params=request.model_dump(),
    )
    RENDER_REQUESTS[job_id] = request
    ensure_render_worker().put_nowait(job_id)
    return {"job_id": job_id, "status": "queued"}


@app.get("/render-jobs")
async def list_render_jobs(
    status: str | None = None,
    episode: str | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    jobs = list(JOBS.values())
    if status == "active":
        jobs = [job for job in jobs if job.status in {"queued", "running"}]
    elif status:
        jobs = [job for job in jobs if job.status == status]
    if episode:
        jobs = [
            job
            for job in jobs
            if job.episode == episode or f"{job.show}/{job.season}/{job.episode}" == episode
        ]
    jobs = sorted(jobs, key=job_created_ts, reverse=status != "active")
    return [job.public() for job in jobs[: max(1, min(limit, 100))]]


@app.get("/render-jobs/{job_id}")
async def get_render_job(job_id: str) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="render job not found")
    return job.public()


@app.delete("/render-jobs/{job_id}")
async def cancel_render_job(job_id: str) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="render job not found")
    if job.status in {"completed", "failed", "cancelled"}:
        return {"ok": True, "job": job.public()}
    job.status = "cancelled"
    job.updated_at = now_iso()
    job.add_log("[cancel] requested by operator")
    process = JOB_PROCESSES.get(job_id)
    if process and process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
    return {"ok": True, "job": job.public()}


@app.websocket("/render-jobs/{job_id}/stream")
async def stream_render_job(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    last_seen = 0
    try:
        while True:
            job = JOBS.get(job_id)
            if not job:
                await websocket.send_json({"status": "missing", "lines": []})
                await websocket.close()
                return
            lines = job.log[last_seen:]
            last_seen = len(job.log)
            await websocket.send_json({"status": job.status, "job": job.public(), "lines": lines})
            if job.status in {"completed", "failed"}:
                return
            await asyncio.sleep(0.6)
    except WebSocketDisconnect:
        return


@app.post("/shows/{show}/seasons/{season}/episodes/{ep}/mix")
async def mix_episode(show: str, season: str, ep: str, request: MixRequest) -> dict[str, Any]:
    ep_path = episode_dir(show, season, ep)
    audio_dir = ep_path / "audio"
    voice = ensure_under(audio_dir, audio_dir / request.voice_wav)
    if not voice.exists():
        raise HTTPException(status_code=404, detail="voice WAV not found")
    music = voice if request.mode == "music_off" else resolve_music_bed(request.music_bed)
    suffix = "NOMUSIC" if request.mode == "music_off" else "FINAL"
    out_stem = re.sub(r"voice[-_]only", suffix, voice.stem, flags=re.IGNORECASE)
    if out_stem == voice.stem:
        out_stem = f"{voice.stem}-{suffix}"
    out_wav = audio_dir / f"{out_stem}.wav"
    out_mp3 = audio_dir / f"{out_stem}.mp3"
    env = os.environ.copy()
    env.update(
        {
            "INTRO_HOT_S": str(request.intro_hot_s),
            "INTRO_FADE_S": str(request.intro_fade_s),
            "OUTRO_S": str(request.outro_s),
            "MUSIC_OFF": "1" if request.mode == "music_off" else "0",
        }
    )
    cmd = [str(TOOLS_DIR / "audio" / "build_episode_mix.sh"), str(voice), str(music), str(out_wav)]
    try:
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, check=True, capture_output=True, text=True)
        mp3_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(out_wav),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "256k",
            str(out_mp3),
        ]
        mp3 = subprocess.run(mp3_cmd, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=(exc.stderr or exc.stdout or str(exc))[-3000:]) from exc
    state = load_state(ep_path)
    row = {
        "timestamp": now_iso(),
        "params": request.model_dump(),
        "outputs": [str(out_wav.relative_to(ep_path)), str(out_mp3.relative_to(ep_path))],
        "stdout": result.stdout + mp3.stdout,
    }
    state["mixes"].append(row)
    save_state(ep_path, state)
    return {
        "ok": True,
        "wav": str(out_wav.relative_to(ep_path)),
        "mp3": str(out_mp3.relative_to(ep_path)),
        "audio": list_audio_files(ep_path, show, season, ep),
        "log": row["stdout"],
    }


@app.get("/shows/{show}/seasons/{season}/episodes/{ep}/annotations")
async def get_annotations(show: str, season: str, ep: str) -> list[dict[str, Any]]:
    return read_annotations(episode_dir(show, season, ep))


@app.post("/shows/{show}/seasons/{season}/episodes/{ep}/annotations")
async def add_annotation(show: str, season: str, ep: str, request: AnnotationRequest) -> dict[str, Any]:
    ep_path = episode_dir(show, season, ep)
    row = {
        "id": uuid.uuid4().hex[:10],
        "timestamp": now_iso(),
        "version": request.version,
        "time_s": request.time_s,
        "text": request.text,
        "line": request.line,
        "section": request.section,
    }
    append_annotation(ep_path, row)
    return row


@app.post("/shows/{show}/seasons/{season}/episodes/{ep}/open")
async def open_in_finder(show: str, season: str, ep: str, request: OpenPathRequest) -> dict[str, Any]:
    ep_path = episode_dir(show, season, ep)
    target = ensure_under(ep_path / "audio", ep_path / "audio" / request.filename)
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    subprocess.Popen(["open", "-R", str(target)])
    return {"ok": True, "path": str(target)}


@app.get("/voices")
async def get_voices() -> list[dict[str, Any]]:
    fallback = [
        "alice",
        "carter",
        "frank",
        "maya",
        "samuel",
        "mary",
        "anchen",
        "bowen",
        "xinran",
        "aaron",
    ]
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(f"{VIBEVOICE_URL}/voices")
            response.raise_for_status()
            data = response.json()
        if isinstance(data, dict):
            raw_voices = data.get("voices") or data.get("data") or data.get("voice_ids") or []
        else:
            raw_voices = data
        voices = []
        for item in raw_voices:
            if isinstance(item, str):
                voices.append({"id": item, "label": item, "source": "vibevoice"})
            elif isinstance(item, dict):
                voice_id = (
                    item.get("voice_id")
                    or item.get("id")
                    or item.get("name")
                    or item.get("voice")
                )
                if voice_id:
                    voices.append({"id": voice_id, "label": item.get("label") or voice_id, **item})
        if voices:
            return sorted(voices, key=lambda item: item["id"])
    except Exception:
        pass
    return [{"id": voice, "label": voice, "source": "fallback"} for voice in fallback]


@app.get("/voices/{voice_id}/sample")
async def voice_sample(voice_id: str):
    voice_id = re.sub(r"[^A-Za-z0-9_-]", "", voice_id)
    if not voice_id:
        raise HTTPException(status_code=400, detail="invalid voice id")
    cache_dir = API_DIR / ".cache" / "voice-samples"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{slugify(voice_id)}.wav"
    if not out.exists():
        payload = {
            "script": [{"speaker_id": "S1", "text": "Podcast Ops voice check. Ready for the studio."}],
            "voices": {"S1": voice_id},
            "format": "wav",
        }
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{VIBEVOICE_URL}/podcast", json=payload)
            response.raise_for_status()
            out.write_bytes(response.content)
    return FileResponse(out, media_type="audio/wav")


@app.post("/voices/clone")
async def clone_voice(name: str = Form(...), file: UploadFile = File(...)) -> dict[str, Any]:
    voice_name = slugify(name)
    with tempfile.TemporaryDirectory(prefix="podcast-ops-voice-") as tempdir:
        tempdir_path = Path(tempdir)
        source = tempdir_path / (file.filename or "voice-upload")
        source.write_bytes(await file.read())
        wav = tempdir_path / f"{voice_name}.wav"
        ffmpeg_cmd = ["ffmpeg", "-y", "-i", str(source), "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(wav)]
        try:
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
            subprocess.run(["scp", str(wav), f"{VOICE_MOUNT_REMOTE}/{voice_name}.wav"], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise HTTPException(status_code=500, detail=(exc.stderr or exc.stdout or str(exc))[-3000:]) from exc
    return {"ok": True, "id": voice_name, "label": voice_name}


@app.get("/music-beds")
async def get_music_beds() -> list[dict[str, Any]]:
    beds: list[dict[str, Any]] = []
    roots = [PROJECT_ROOT / "assets" / "music-beds", *SHOWS_DIR.glob("**/assets/music-beds")]
    seen: set[Path] = set()
    for root in roots:
        if not root.exists() or root in seen:
            continue
        seen.add(root)
        for path in sorted(root.iterdir()):
            if path.suffix.lower() not in {".wav", ".mp3", ".flac", ".m4a"}:
                continue
            beds.append(
                {
                    "filename": path.name,
                    "title": path.stem.replace("__", " — ").replace("_", " "),
                    "path": str(path.relative_to(PROJECT_ROOT)),
                    "size_bytes": path.stat().st_size,
                    "duration_s": file_duration(path),
                }
            )
    return beds


@app.post("/music-beds/extract")
async def extract_music_bed(request: MusicExtractRequest) -> dict[str, Any]:
    source = find_catalog_track(request.source_mp4)
    out_dir = PROJECT_ROOT / "assets" / "music-beds"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{slugify(request.slug)}.wav"
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(request.start_s),
        "-t",
        str(request.duration_s),
        "-i",
        str(source),
        "-vn",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-c:a",
        "pcm_s16le",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=(exc.stderr or exc.stdout or str(exc))[-3000:]) from exc
    return {"ok": True, "filename": out.name, "path": str(out.relative_to(PROJECT_ROOT)), "duration_s": file_duration(out)}


@app.get("/chat/agents")
async def list_chat_agents() -> list[dict[str, str]]:
    return [{"id": agent, "label": agent, "description": description} for agent, description in BRIGADE_CHAT_AGENTS.items()]


@app.post("/chat/brigade")
async def chat_brigade(request: ChatRequest):
    agent = request.agent if request.agent in BRIGADE_CHAT_AGENTS else "majik"
    messages = [
        {"role": "system", "content": chat_system_prompt(agent, request.episode_context)},
        *request.messages,
    ]
    ep_path = episode_context_dir(request.episode_context)
    if ep_path:
        for message in request.messages[-4:]:
            append_chat_message(
                ep_path,
                {
                    "id": uuid.uuid4().hex[:10],
                    "timestamp": now_iso(),
                    "agent": agent,
                    "role": message.get("role", "user"),
                    "content": message.get("content", ""),
                },
            )

    async def event_stream():
        collected: list[str] = []
        if not BRIGADE_BASE_URL or not BRIGADE_API_KEY:
            fallback = (
                "Brigade is not configured for this API process. Set BRIGADE_API_KEY in "
                "apps/api/.env to enable live agent chat. I can still see the episode context "
                "and help with local workflow prompts."
            )
            for token in re.findall(r"\S+\s*", fallback):
                collected.append(token)
                yield chat_sse({"delta": token, "agent": agent})
                await asyncio.sleep(0.01)
            yield chat_sse({"done": True, "source": "local-fallback"})
            if ep_path:
                append_chat_message(
                    ep_path,
                    {
                        "id": uuid.uuid4().hex[:10],
                        "timestamp": now_iso(),
                        "agent": agent,
                        "role": "assistant",
                        "content": "".join(collected),
                        "source": "local-fallback",
                    },
                )
            return

        headers = {"Authorization": f"Bearer {BRIGADE_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": agent,
            "messages": messages,
            "temperature": 0.35,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{BRIGADE_BASE_URL}/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line.removeprefix("data:").strip()
                        if raw == "[DONE]":
                            break
                        with contextlib.suppress(json.JSONDecodeError, KeyError, IndexError):
                            data = json.loads(raw)
                            delta = data["choices"][0].get("delta", {}).get("content") or ""
                            if delta:
                                collected.append(delta)
                                yield chat_sse({"delta": delta, "agent": agent})
            yield chat_sse({"done": True, "source": "brigade"})
            if ep_path:
                append_chat_message(
                    ep_path,
                    {
                        "id": uuid.uuid4().hex[:10],
                        "timestamp": now_iso(),
                        "agent": agent,
                        "role": "assistant",
                        "content": "".join(collected),
                        "source": "brigade",
                    },
                )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, httpx.RequestError) as exc:
            yield chat_sse({"error": "brigade_timeout", "detail": str(exc)})
        except Exception as exc:
            yield chat_sse({"error": "brigade_error", "detail": str(exc)})

    if request.stream:
        return StreamingResponse(event_stream(), media_type="text/event-stream")

    chunks: list[str] = []
    async for event in event_stream():
        payload = json.loads(event.removeprefix("data:").strip())
        if payload.get("delta"):
            chunks.append(payload["delta"])
    return {"agent": agent, "content": "".join(chunks)}


@app.post("/ai/script-edit")
async def ai_script_edit(request: AIScriptEditRequest) -> dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": (
                "You edit Podcast-Ops markdown. Return only the edited markdown, preserving "
                "speaker tags, section headings, and frontmatter if present."
            ),
        },
        {
            "role": "user",
            "content": f"Instruction: {request.instruction}\n\nCurrent script:\n{request.current_script}",
        },
    ]
    source = "brigade"
    edited, error = await call_brigade(messages, request.model)
    if edited is None:
        source = "local-fallback"
        edited = local_tighten_fallback(request.current_script, request.instruction)
    edited = strip_markdown_fence(edited)
    diff = "\n".join(
        difflib.unified_diff(
            request.current_script.splitlines(),
            edited.splitlines(),
            fromfile="current",
            tofile="edited",
            lineterm="",
        )
    )
    return {"ok": error is None, "error": error, "edited_script": edited, "diff": diff, "source": source}


@app.post("/ai/generate-script")
async def ai_generate_script(request: AIGenerateScriptRequest) -> dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": (
                "Generate a complete Podcast-Ops script.md with YAML frontmatter, cast mapping, "
                "and ## § N sections. Use two-host documentary pacing."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Topic: {request.topic}\nShow: {request.show}\n"
                f"Format: {request.format}\nTarget minutes: {request.target_minutes}"
            ),
        },
    ]
    source = "brigade"
    script, error = await call_brigade(messages, request.model)
    if script is None:
        source = "local-fallback"
        script = f"""---
show: {request.show}
title: "{request.topic}"
target_minutes: {request.target_minutes}
cast:
  aria: host       # voice: alice
  beck: host       # voice: carter
status: draft
---

# {request.topic}

## § 0 · Cold open

**ARIA:**
Set up the central tension for {request.topic}.

**BECK:**
Ask the skeptical question the listener is already thinking.

## § 1 · The turn

**ARIA:**
Explain what changed and why it matters.

**BECK:**
Pressure-test the claim.
"""
    script = strip_markdown_fence(script)
    return {"ok": error is None, "error": error, "script": script, "source": source, "metrics": script_metrics(script)}
