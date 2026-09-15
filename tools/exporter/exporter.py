"""Read-only, explicitly selected Podcast rail export protocol v1."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

import httpx
import yaml

MEDIA = {'.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.flac': 'audio/flac'}
SLUG = re.compile(r'^[a-z0-9][a-z0-9_-]{0,119}$')
MAX_SIZE = 20 * 1024**3


def relative(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ValueError('Invalid relative path')
    if '\\' in value or '%' in value or ':' in value or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid relative path')
    if value.startswith('/') or any(p in ('', '.', '..') for p in value.split('/')):
        raise ValueError('Traversal rejected')
    return value


def resolve(root: Path, value: str) -> Path:
    path = root.resolve() / relative(value)
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('Symlink escapes allowlisted root')
    return resolved


def signature(path: Path):
    st = path.stat()
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def snapshot(root: Path, value: str, seconds: float, output=None):
    """Open a confined file; check descriptor and path before/after observation/read."""
    path = resolve(root, value)
    with path.open('rb') as handle:
        first = signature(path)
        fst = os.fstat(handle.fileno())
        if not path.is_file() or (fst.st_dev, fst.st_ino) != first[:2]:
            raise ValueError('Source changed')
        time.sleep(seconds)
        if signature(resolve(root, value)) != first:
            raise ValueError('Source still changing')
        digest = hashlib.sha256()
        count = 0
        while data := handle.read(1024 * 1024):
            count += len(data)
            if count > MAX_SIZE:
                raise ValueError('Source too large')
            digest.update(data)
            if output is not None:
                output.write(data)
        last = os.fstat(handle.fileno())
        if signature(resolve(root, value)) != first or (last.st_dev, last.st_ino, last.st_size, last.st_mtime_ns, last.st_ctime_ns) != first or count != first[2]:
            raise ValueError('Source changed while reading')
        return {'path': value, 'size': count, 'sha256': digest.hexdigest(), 'mtimeNs': str(first[3])}


def selection_file(path: Path):
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or set(data) != {'version', 'sourceInstallationId', 'tenantNamespace', 'episodes'} or data['version'] != 1:
        raise ValueError('Invalid selection v1')
    for name in ('sourceInstallationId', 'tenantNamespace'):
        if not isinstance(data[name], str) or not SLUG.fullmatch(data[name]):
            raise ValueError('Invalid namespace')
    if not isinstance(data['episodes'], list) or not 1 <= len(data['episodes']) <= 100:
        raise ValueError('Select 1–100 episodes')
    keys, paths = set(), set()
    for row in data['episodes']:
        if not isinstance(row, dict) or set(row) - {'show', 'season', 'episode', 'artifact', 'annotations'} or not {'show', 'season', 'episode', 'artifact'} <= set(row):
            raise ValueError('Invalid episode selection')
        for name in ('show', 'season', 'episode'):
            if not isinstance(row[name], str) or not SLUG.fullmatch(row[name]):
                raise ValueError('Invalid episode key')
        base = f"shows/{data['tenantNamespace']}/{row['show']}/{row['season']}/episodes/{row['episode']}/"
        artifact = relative(row['artifact'])
        if not artifact.startswith(base) or PurePosixPath(artifact).suffix.lower() not in MEDIA:
            raise ValueError('Artifact is outside selected tenant/episode or not media')
        key = '/'.join([data['tenantNamespace'], row['show'], row['season'], row['episode']])
        if key in keys or artifact in paths:
            raise ValueError('Duplicate selection')
        keys.add(key)
        paths.add(artifact)
        if 'annotations' in row and relative(row['annotations']) != base + 'episode.annotations.jsonl':
            raise ValueError('Annotations must belong to selected episode')
    return data


def metadata_file(root, path, seconds):
    import io
    content = io.BytesIO()
    info = snapshot(root, path, seconds, content)
    if info['size'] > 2 * 1024**2:
        raise ValueError('Metadata too large')
    return info, content.getvalue()


def build_manifest(root: Path, repo: Path, selection: dict, seconds: float):
    if seconds <= 0 or not math.isfinite(seconds):
        raise ValueError('Stability interval must be positive')
    sha = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    manifest = {'version': 1, 'sourceInstallationId': selection['sourceInstallationId'], 'tenantNamespace': selection['tenantNamespace'],
                'sourceRevision': {'gitSha': sha, 'fileMtimes': {}}, 'selectedPaths': [r['artifact'] for r in selection['episodes']], 'episodes': []}
    mtimes = manifest['sourceRevision']['fileMtimes']
    for row in selection['episodes']:
        key = '/'.join([selection['tenantNamespace'], row['show'], row['season'], row['episode']])
        entry = {k: row[k] for k in ('show', 'season', 'episode')}
        entry.update({'sourceKey': key, 'artifact': None, 'selectedPath': row['artifact'], 'available': False, 'scriptRevision': None,
                      'renderStatus': 'unknown', 'mixStatus': 'unknown', 'annotations': []})
        artifact = resolve(root, row['artifact'])
        if artifact.exists():
            info = snapshot(root, row['artifact'], seconds)
            if info['size'] <= 0:
                raise ValueError('Empty media')
            mtimes[info['path']] = info.pop('mtimeNs')
            entry.update({'available': True, 'artifact': {**info, 'mimeType': MEDIA[artifact.suffix.lower()]}})
        # Metadata belongs to the episode directory, independent of artifact subfolders.
        base = f"shows/{selection['tenantNamespace']}/{row['show']}/{row['season']}/episodes/{row['episode']}"
        for name in ('script.md', 'episode.state.json'):
            path = f'{base}/{name}'
            if resolve(root, path).exists():
                info, content = metadata_file(root, path, seconds)
                mtimes[path] = info['mtimeNs']
                if name == 'script.md':
                    entry['scriptRevision'] = info['sha256']  # No script body export.
                else:
                    state = json.loads(content)
                    for collection, field in (('renders', 'renderStatus'), ('mixes', 'mixStatus')):
                        records = state.get(collection, [])
                        # Observed rail history, never filename-based approval.
                        if records:
                            status = records[-1].get('status', 'recorded')
                            entry[field] = status if status in ('queued', 'running', 'completed', 'failed', 'cancelled', 'recorded') else 'recorded'
        if row.get('annotations') and resolve(root, row['annotations']).exists():
            info, content = metadata_file(root, row['annotations'], seconds)
            mtimes[info['path']] = info['mtimeNs']
            for line in content.decode().splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                canonical = json.dumps(item, sort_keys=True, separators=(',', ':'))
                entry['annotations'].append({'sourceId': hashlib.sha256(canonical.encode()).hexdigest(),
                    'author': str(item.get('author') or 'Podcast-Ops (source author unspecified)')[:200],
                    'timestamp': str(item.get('timestamp', 'unknown'))[:100], 'body': str(item.get('text', ''))[:10000],
                    'sourceVersion': str(item.get('version', 'unknown'))[:200],
                    'timeSeconds': max(0, float(item.get('time_s') or 0))})
        manifest['episodes'].append(entry)
    return manifest


def propose(root: Path, tenant: str, show: str, season: str):
    root = root.resolve()
    for slug in (tenant, show, season):
        if not SLUG.fullmatch(slug):
            raise ValueError('Invalid namespace')
    base = resolve(root, f'shows/{tenant}/{show}/{season}/episodes')
    lines = ['# Proposed selection — operator confirmation required', '', 'No artifact is selected by this report.', '', '| Episode | Candidate relative path | Bytes | Duration seconds |', '| --- | --- | ---: | ---: |']
    count = 0
    for episode in sorted(base.iterdir()):
        if not episode.is_dir():
            continue
        found = False
        for path in sorted(episode.rglob('*')):
            if path.suffix.lower() not in MEDIA:
                continue
            rel = path.relative_to(root).as_posix()
            safe = resolve(root, rel)
            if not safe.is_file():
                continue
            before = signature(safe)
            result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', str(safe)], capture_output=True, text=True, timeout=30)
            if result.returncode or before != signature(resolve(root, rel)):
                continue
            probe = json.loads(result.stdout)
            if not any(s.get('codec_type') == 'audio' for s in probe.get('streams', [])):
                continue
            duration = float(probe.get('format', {}).get('duration', 0))
            if duration <= 0:
                continue
            lines.append(f'| {episode.name} | `{rel.replace("|", "&#124;")}` | {before[2]} | {duration:.3f} |')
            found = True
            count += 1
        if not found:
            lines.append(f'| {episode.name} | No playable candidate found | — | — |')
    return '\n'.join(lines) + f'\n\n{count} candidates. Choose exactly one canonical artifact per episode in selection.yaml.\n'


def secure_url(value):
    url = urlsplit(value)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError('Export requires HTTPS without URL credentials')
    return value.rstrip('/')


def push(root: Path, manifest: dict, selection: dict, endpoint: str, token: str, seconds: float):
    endpoint = secure_url(endpoint)
    allowed = {row['artifact'] for row in selection['episodes']}
    if manifest['selectedPaths'] != [row['artifact'] for row in selection['episodes']] or manifest['tenantNamespace'] != selection['tenantNamespace'] or manifest['sourceInstallationId'] != selection['sourceInstallationId']:
        raise ValueError('Manifest does not match operator selection')
    # Only generated manifests are accepted by CLI; defense in depth before network activity.
    for entry in manifest['episodes']:
        if entry['selectedPath'] not in allowed or (entry['artifact'] and entry['artifact']['path'] != entry['selectedPath']):
            raise ValueError('Unlisted media rejected')
    with httpx.Client(timeout=1800, follow_redirects=False) as client:
        def api(action, body):
            response = client.post(f'{endpoint}/{action}', json=body, headers={'Authorization': f'Bearer {token}'})
            if response.status_code != 200:
                raise ValueError(f'Producer {action} refused ({response.status_code}); no response details logged')
            return response.json()
        prepared = api('manifest', manifest)
        for item in prepared['uploads']:
            entry = next(e for e in manifest['episodes'] if e['sourceKey'] == item['sourceKey'])
            artifact = entry['artifact']
            if not artifact or artifact['path'] not in allowed:
                raise ValueError('Server requested unlisted media')
            # Private temporary snapshot prevents a writer changing media during transfer.
            with tempfile.TemporaryFile(dir='/tmp') as staged:
                info = snapshot(root, artifact['path'], seconds, staged)
                if info['size'] != artifact['size'] or info['sha256'] != artifact['sha256']:
                    raise ValueError('Selected media changed since manifest; rescan required')
                staged.seek(0)
                for number in range(1, math.ceil(info['size'] / item['partSize']) + 1):
                    signed = api('parts', {'uploadId': item['uploadId'], 'partNumbers': [number]})
                    url = secure_url(signed[0]['url'])
                    response = client.put(url, content=staged.read(item['partSize']))
                    if response.status_code not in (200, 204):
                        raise ValueError('Media part upload failed')
                api('complete', {'uploadId': item['uploadId']})
    return len(prepared['uploads'])


def main():
    parser = argparse.ArgumentParser(prog='podcast-ops-export')
    parser.add_argument('command', choices=['propose', 'manifest', 'push'])
    parser.add_argument('--root', type=Path, required=True, help='Explicit allowlisted rail root')
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--stable-seconds', type=float, default=3)
    parser.add_argument('--tenant', default='magic-unicorn')
    parser.add_argument('--show', default='the-layer-above')
    parser.add_argument('--season', default='season-1-majiks')
    parser.add_argument('--endpoint', help='Producer /api/podcast base URL')
    args = parser.parse_args()
    try:
        if args.command == 'propose':
            result = propose(args.root, args.tenant, args.show, args.season)
        else:
            if not args.selection:
                raise ValueError('--selection is required')
            selection = selection_file(args.selection)
            manifest = build_manifest(args.root, args.repo, selection, args.stable_seconds)
            if args.command == 'push':
                token = os.environ.get('PODCAST_EXPORT_TOKEN')
                if not token or not args.endpoint:
                    raise ValueError('PODCAST_EXPORT_TOKEN and --endpoint required')
                count = push(args.root, manifest, selection, args.endpoint, token, args.stable_seconds)
                result = f'Export complete: {count} media uploads; other entries reconciled.\n'
            else:
                result = json.dumps(manifest, indent=2) + '\n'
        if args.output:
            args.output.write_text(result)
        else:
            print(result, end='')
    except Exception:
        # Upstream exceptions can contain URLs, credentials or source contents.
        print('Export refused. Check selection, root confinement, file stability and server configuration.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
