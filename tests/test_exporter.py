import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave

SPEC = importlib.util.spec_from_file_location('exporter', Path(__file__).parents[1] / 'tools/exporter/exporter.py')
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class ExportContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='/tmp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'synthetic'], check=True)
        self.base = 'shows/tenant-a/same-show/season-1/episodes/ep01'
        self.media = f'{self.base}/audio/selected.wav'
        self.make_wav(self.media)
        (self.root / self.base / 'script.md').write_text('Synthetic script only')
        self.selection = {'version': 1, 'sourceInstallationId': 'fixture-install', 'tenantNamespace': 'tenant-a',
                          'episodes': [{'show': 'same-show', 'season': 'season-1', 'episode': 'ep01', 'artifact': self.media}]}

    def make_wav(self, path):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(target), 'wb') as handle:
            handle.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            handle.writeframes(b'\x00\x00' * 800)

    def selected(self, data=None):
        path = self.root / 'selection.yaml'
        path.write_text(json.dumps(self.selection if data is None else data))
        return exporter.selection_file(path)

    def manifest(self, selection=None):
        return exporter.build_manifest(self.root, self.root, selection or self.selected(), .001)

    def test_same_slug_two_tenants_stable_keys(self):
        a = self.manifest()
        self.assertEqual(a, self.manifest())
        other = copy.deepcopy(self.selection)
        other['tenantNamespace'] = 'tenant-b'
        other['episodes'][0]['artifact'] = self.media.replace('tenant-a', 'tenant-b')
        self.make_wav(other['episodes'][0]['artifact'])
        b = self.manifest(self.selected(other))
        self.assertNotEqual(a['episodes'][0]['sourceKey'], b['episodes'][0]['sourceKey'])
        self.assertEqual(a['episodes'][0]['artifact']['sha256'], b['episodes'][0]['artifact']['sha256'])

    def test_no_automatic_final_selection_or_script_body(self):
        self.make_wav(f'{self.base}/audio/newer-FINAL.wav')
        manifest = self.manifest()
        self.assertEqual(manifest['selectedPaths'], [self.media])
        self.assertNotIn('Synthetic script', json.dumps(manifest))
        self.assertEqual(manifest['episodes'][0]['mixStatus'], 'unknown')

    def test_traversal_unlisted_duplicate_cross_tenant(self):
        for path in ('../outside.wav', '/tmp/out.wav', self.media.replace('tenant-a', 'tenant-b'), self.media.replace('/audio/', '/audio/../'), self.media + '%2f', self.media.replace('/', '\\')):
            data = copy.deepcopy(self.selection)
            data['episodes'][0]['artifact'] = path
            with self.assertRaises(ValueError):
                self.selected(data)
        data = copy.deepcopy(self.selection)
        data['episodes'] *= 2
        with self.assertRaises(ValueError):
            self.selected(data)

    def test_external_symlink_rejected_internal_allowed(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as outside:
            external = Path(outside) / 'outside.wav'
            external.write_bytes(b'not selected')
            selected = self.root / self.media
            selected.unlink()
            selected.symlink_to(external)
            with self.assertRaises(ValueError):
                self.manifest()
            selected.unlink()
            self.make_wav(f'{self.base}/audio/inside.wav')
            selected.symlink_to('inside.wav')
            self.assertTrue(self.manifest()['episodes'][0]['available'])

    def test_changing_file_rejected(self):
        def mutate(_):
            with (self.root / self.media).open('ab') as handle:
                handle.write(b'new bytes')
        with patch.object(exporter.time, 'sleep', mutate):
            with self.assertRaisesRegex(ValueError, 'changing'):
                self.manifest()

    def test_empty_and_missing_media(self):
        (self.root / self.media).write_bytes(b'')
        with self.assertRaises(ValueError):
            self.manifest()
        (self.root / self.media).unlink()
        entry = self.manifest()['episodes'][0]
        self.assertFalse(entry['available'])
        self.assertIsNone(entry['artifact'])

    def test_annotation_opt_in_and_attribution(self):
        path = f'{self.base}/episode.annotations.jsonl'
        (self.root / path).write_text(json.dumps({'id': 'source-id', 'text': 'synthetic note', 'timestamp': '2026-09-15', 'version': 'v1', 'time_s': 1}) + '\n')
        self.assertEqual(self.manifest()['episodes'][0]['annotations'], [])
        self.selection['episodes'][0]['annotations'] = path
        a = self.manifest()['episodes'][0]['annotations'][0]
        self.assertIn('unspecified', a['author'])
        self.assertEqual(a['sourceVersion'], 'v1')
        self.assertEqual(a, self.manifest()['episodes'][0]['annotations'][0])

    def test_proposed_report_metadata_only(self):
        report = exporter.propose(self.root, 'tenant-a', 'same-show', 'season-1')
        self.assertIn(self.media, report)
        self.assertIn('1644', report)
        self.assertIn('0.100', report)
        self.assertNotIn('Synthetic script', report)

    def test_unlisted_push_rejected_before_network(self):
        manifest = self.manifest()
        manifest['episodes'][0]['artifact']['path'] = f'{self.base}/audio/unlisted.wav'
        with patch.object(exporter.httpx, 'Client') as client:
            with self.assertRaisesRegex(ValueError, 'Unlisted'):
                exporter.push(self.root, manifest, self.selected(), 'https://producer.example.invalid/api/podcast', 'synthetic', .001)
            client.assert_not_called()

    def test_push_transfers_only_selected_snapshot_and_never_bearer_to_storage(self):
        manifest = self.manifest()
        calls = []
        real_client = exporter.httpx.Client
        def handle(request):
            calls.append(request)
            if request.url.host == 'storage.example.invalid':
                self.assertNotIn('authorization', request.headers)
                self.assertEqual(request.content, (self.root / self.media).read_bytes())
                return exporter.httpx.Response(200)
            self.assertEqual(request.headers['authorization'], 'Bearer synthetic')
            action = request.url.path.split('/')[-1]
            if action == 'manifest':
                self.assertEqual(json.loads(request.content), manifest)
                return exporter.httpx.Response(200, json={'uploads': [{'sourceKey': manifest['episodes'][0]['sourceKey'], 'uploadId': 'server-id', 'partSize': 1024 * 1024}]})
            if action == 'parts':
                self.assertEqual(json.loads(request.content), {'uploadId': 'server-id', 'partNumbers': [1]})
                return exporter.httpx.Response(200, json=[{'number': 1, 'url': 'https://storage.example.invalid/opaque-key'}])
            self.assertEqual(action, 'complete')
            return exporter.httpx.Response(200, json={'assetId': 'server-asset'})
        transport = exporter.httpx.MockTransport(handle)
        with patch.object(exporter.httpx, 'Client', lambda **kwargs: real_client(transport=transport, **kwargs)):
            self.assertEqual(exporter.push(self.root, manifest, self.selected(), 'https://producer.example.invalid/api/podcast', 'synthetic', .001), 1)
        self.assertEqual(len(calls), 4)

    def test_changed_after_manifest_never_transfers_media(self):
        manifest = self.manifest()
        (self.root / self.media).write_bytes(b'changed')
        real_client = exporter.httpx.Client
        def handle(request):
            self.assertTrue(request.url.path.endswith('/manifest'))
            return exporter.httpx.Response(200, json={'uploads': [{'sourceKey': manifest['episodes'][0]['sourceKey'], 'uploadId': 'server-id', 'partSize': 1024}]})
        with patch.object(exporter.httpx, 'Client', lambda **kwargs: real_client(transport=exporter.httpx.MockTransport(handle), **kwargs)):
            with self.assertRaisesRegex(ValueError, 'changed since manifest'):
                exporter.push(self.root, manifest, self.selected(), 'https://producer.example.invalid/api/podcast', 'synthetic', .001)

    def test_stability_interval_and_insecure_destination_refused(self):
        for seconds in (0, -1, float('nan')):
            with self.assertRaises(ValueError):
                exporter.build_manifest(self.root, self.root, self.selected(), seconds)
        for url in ('http://example.invalid', 'http://example.invalid', 'https://example.invalid/#fragment'):
            with self.assertRaises(ValueError):
                exporter.secure_url(url)


if __name__ == '__main__':
    unittest.main()
