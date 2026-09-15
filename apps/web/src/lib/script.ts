import type { ScriptSection } from "@/lib/api";

export type CastMember = {
  speaker: string;
  role: string;
  voice: string;
  line: string;
};

const frontmatterPattern = /^---\s*\n([\s\S]*?)\n---\s*\n/;
const sectionPattern = /^##\s+§\s*([A-Za-z0-9_.-]+)\s*[·•.\-]?\s*(.*?)\s*$/gm;

export function splitFrontmatter(script: string) {
  const match = script.match(frontmatterPattern);
  if (!match) {
    return { frontmatter: "", body: script, block: "" };
  }
  return {
    frontmatter: match[1],
    body: script.slice(match[0].length),
    block: match[0],
  };
}

export function parseCast(script: string): CastMember[] {
  const { frontmatter } = splitFrontmatter(script);
  const lines = frontmatter.split("\n");
  const castStart = lines.findIndex((line) => /^cast:\s*$/.test(line));
  if (castStart === -1) {
    return [];
  }
  const cast: CastMember[] = [];
  for (let index = castStart + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^\S/.test(line) && line.trim() !== "") {
      break;
    }
    const match = line.match(/^\s{2,}([A-Za-z0-9_-]+):\s*([^#\n]*?)(?:\s*#\s*voice:\s*([A-Za-z0-9_-]+).*)?$/);
    if (!match) {
      continue;
    }
    cast.push({
      speaker: match[1].toUpperCase(),
      role: match[2].trim() || "speaker",
      voice: match[3] || "",
      line,
    });
  }
  return cast;
}

export function replaceCastVoice(script: string, speaker: string, voice: string) {
  const speakerKey = speaker.toLowerCase();
  const lines = script.split("\n");
  const frontmatterEnd = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
  const end = frontmatterEnd === -1 ? lines.length : frontmatterEnd;
  const castStart = lines.findIndex((line, index) => index < end && /^cast:\s*$/.test(line));
  if (castStart === -1) {
    return script;
  }
  for (let index = castStart + 1; index < end; index += 1) {
    const line = lines[index];
    const match = line.match(/^(\s{2,})([A-Za-z0-9_-]+):(\s*[^#\n]*)(.*)$/);
    if (!match || match[2].toLowerCase() !== speakerKey) {
      if (/^\S/.test(line) && line.trim() !== "") {
        break;
      }
      continue;
    }
    const comment = match[4].includes("voice:")
      ? match[4].replace(/voice:\s*[A-Za-z0-9_-]+/, `voice: ${voice}`)
      : `       # voice: ${voice}`;
    lines[index] = `${match[1]}${match[2]}:${match[3]}${comment}`;
    return lines.join("\n");
  }
  return script;
}

export function parseSections(script: string): ScriptSection[] {
  const { body, block } = splitFrontmatter(script);
  const matches = [...body.matchAll(sectionPattern)];
  return matches.map((match, index) => {
    const start = match.index ?? 0;
    const end = index + 1 < matches.length ? matches[index + 1].index ?? body.length : body.length;
    return {
      id: `§${match[1]}`,
      number: match[1],
      index,
      title: match[2].trim(),
      line: block.split("\n").length + body.slice(0, start).split("\n").length - 1,
      header: match[0],
      markdown: body.slice(start, end).trimEnd(),
    };
  });
}

export function replaceSection(script: string, sectionId: string, replacement: string) {
  const { body, block } = splitFrontmatter(script);
  const matches = [...body.matchAll(sectionPattern)];
  const target = matches.findIndex((match) => `§${match[1]}` === sectionId);
  if (target === -1) {
    return script;
  }
  const start = matches[target].index ?? 0;
  const end = target + 1 < matches.length ? matches[target + 1].index ?? body.length : body.length;
  const next = `${body.slice(0, start)}${replacement.trimEnd()}\n\n${body.slice(end).trimStart()}`;
  return `${block}${next}`;
}

export function wordCount(script: string) {
  const withoutFrontmatter = script.replace(frontmatterPattern, "");
  const cleaned = withoutFrontmatter
    .replace(/^#+\s+.*$/gm, "")
    .replace(/^\*\*[A-Z0-9_ -]+:\*\*\s*$/gm, "")
    .replace(/\[[^\]]+\]/g, "");
  return (cleaned.match(/[A-Za-z0-9][A-Za-z0-9'.-]*/g) ?? []).length;
}

export function nextVersion(audioNames: string[]) {
  const versions = audioNames
    .flatMap((name) => [...name.matchAll(/(?:^|-)v(\d+)(?:-|\.|$)/gi)].map((match) => Number(match[1])))
    .filter((version) => Number.isFinite(version));
  const next = versions.length ? Math.max(...versions) + 1 : 1;
  return `v${next}`;
}
