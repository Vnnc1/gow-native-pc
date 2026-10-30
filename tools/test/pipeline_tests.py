"""Behavioral regression tests for generation transactions and incremental sync; no ISO required."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('recompile', ROOT / 'tools/pipeline/recompile.py')
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='gow-pipeline-')
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.build = self.root / 'build'
        self.output = self.root / 'data/demo/recomp/out'
        self.calls = 0
        self.code = 'int function() { return 1; }\n'
        files = {
            'games/demo/game.toml': '[runtime]\nfunction_map="map.csv"\nrecompiler_template="template.toml"\noverrides=[]\n',
            'engine/runtime/map.csv': 'map',
            'engine/runtime/template.toml': '@OUT@',
            'build/ps2xRecomp/ps2_recomp.exe': 'compiler',
            'game.elf': 'elf',
            'data/demo/languages.json': json.dumps({'recompile_elf': str(self.root / 'game.elf')}),
        }
        for name, data in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data, encoding='utf-8')
        self.mock = patch.object(pipeline.subprocess, 'run', side_effect=self.compile)
        self.run = self.mock.start()
        self.addCleanup(self.mock.stop)

    def compile(self, args, **kwargs):
        self.calls += 1
        self.environment = kwargs['env']
        output = Path(Path(args[1]).read_text(encoding='utf-8'))
        (output / 'register_functions.cpp').write_text(self.code, encoding='utf-8')
        (output / 'ps2_recompiled_functions.h').write_text('// declarations\n', encoding='utf-8')

    def generate(self, codegen='locals', force=False):
        return pipeline.generate(self.root, 'demo', self.build, codegen, force)

    def test_identical_inputs_skip_generator(self):
        self.assertFalse(self.generate()['cacheHit'])
        stamp = (self.output / 'register_functions.cpp').stat().st_mtime_ns
        self.assertTrue(self.generate()['cacheHit'])
        self.assertEqual(self.calls, 1)
        self.assertEqual((self.output / 'register_functions.cpp').stat().st_mtime_ns, stamp)

    def test_input_content_invalidates_even_with_same_mtime(self):
        self.generate()
        for name in ['game.elf', 'engine/runtime/map.csv', 'build/ps2xRecomp/ps2_recomp.exe']:
            path = self.root / name
            stamp = path.stat().st_mtime_ns
            path.write_bytes(path.read_bytes() + b'changed')
            os.utime(path, ns=(stamp, stamp))
            self.assertFalse(self.generate()['cacheHit'])

    def test_codegen_modes_and_environment_invalidate(self):
        with patch.dict(os.environ, {'PS2X_CODEGEN': 'locals'}):
            self.generate()
            self.assertFalse(self.generate('classic')['cacheHit'])
            self.assertEqual(self.environment['PS2X_CODEGEN'], 'classic')
        with patch.dict(os.environ, {'PS2X_STATIC_CALLS': 'dispatch'}):
            self.assertFalse(self.generate('classic')['cacheHit'])

    def test_forced_identical_generation_preserves_mtime(self):
        self.generate()
        file = self.output / 'register_functions.cpp'
        stamp = file.stat().st_mtime_ns
        self.assertFalse(self.generate(force=True)['cacheHit'])
        self.assertEqual(file.stat().st_mtime_ns, stamp)

    def test_output_corruption_regenerates(self):
        self.generate()
        (self.output / 'register_functions.cpp').write_text('damaged', encoding='utf-8')
        self.assertFalse(self.generate()['cacheHit'])
        self.assertEqual((self.output / 'register_functions.cpp').read_text(), self.code)

    def test_failed_generation_preserves_previous_output(self):
        self.generate()
        before = pipeline.inventory(self.output)
        self.run.side_effect = subprocess.CalledProcessError(1, 'compiler')
        with self.assertRaises(subprocess.CalledProcessError):
            self.generate(force=True)
        self.assertEqual(pipeline.inventory(self.output), before)
        self.assertFalse(list(self.output.parent.glob('out.pending-*')))

    def test_incomplete_output_is_not_published(self):
        self.generate()
        before = pipeline.inventory(self.output)
        self.run.side_effect = lambda *a, **k: None
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            self.generate(force=True)
        self.assertEqual(pipeline.inventory(self.output), before)

    def test_sync_preserves_mtime_and_removes_owned_stale_files(self):
        self.generate()
        destination = self.root / 'runner'
        state = self.root / 'sync.json'
        source = self.output / 'register_functions.cpp'
        first = pipeline.sync_owned({'old.cpp': source}, destination, state)
        stamp = (destination / 'old.cpp').stat().st_mtime_ns
        second = pipeline.sync_owned({'old.cpp': source}, destination, state)
        self.assertEqual((first['changed'], second['changed']), (1, 0))
        self.assertEqual((destination / 'old.cpp').stat().st_mtime_ns, stamp)
        (destination / 'foreign.cpp').write_text('handwritten', encoding='utf-8')
        result = pipeline.sync_owned({'new.cpp': source}, destination, state)
        self.assertEqual(result, {'changed': 1, 'removed': 1})
        self.assertTrue((destination / 'foreign.cpp').exists())
        self.assertFalse((destination / 'old.cpp').exists())

    def test_modified_stale_file_blocks_removal_before_copy(self):
        self.generate()
        destination = self.root / 'runner'
        state = self.root / 'sync.json'
        source = self.output / 'register_functions.cpp'
        pipeline.sync_owned({'old.cpp': source}, destination, state)
        (destination / 'old.cpp').write_text('edited', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'modified generated'):
            pipeline.sync_owned({'new.cpp': source}, destination, state)
        self.assertFalse((destination / 'new.cpp').exists())

    def test_manifest_cannot_delete_outside_destination(self):
        destination = self.root / 'runner'
        destination.mkdir()
        state = self.root / 'sync.json'
        pipeline.atomic_json(state, {'destination': str(destination), 'files': {'../game.elf': 'bad'}})
        with self.assertRaises(ValueError):
            pipeline.sync_owned({}, destination, state)
        self.assertTrue((self.root / 'game.elf').exists())

    def test_sync_rejects_modified_output(self):
        self.generate()
        (self.output / 'register_functions.cpp').unlink()
        with self.assertRaisesRegex(RuntimeError, 'modified'):
            pipeline.synchronize(self.root, 'demo')


class WindowsReplacementTests(unittest.TestCase):
    def test_transient_windows_denial_retries_without_losing_previous_file(self):
        with tempfile.TemporaryDirectory(prefix='gow-replace-') as folder:
            source, target = Path(folder) / 'pending', Path(folder) / 'current'
            source.write_text('new')
            target.write_text('previous')
            replace = Path.replace
            calls = 0

            def temporarily_locked(path, destination):
                nonlocal calls
                calls += 1
                if calls <= 2:
                    self.assertEqual(target.read_text(), 'previous')
                    error = PermissionError('temporary Windows replacement denial')
                    error.winerror = 5 if calls == 1 else 32
                    raise error
                return replace(path, destination)

            with patch.object(Path, 'replace', temporarily_locked), patch.object(pipeline.time, 'sleep') as sleep:
                pipeline.replace_file(source, target)
            self.assertEqual(calls, 3)
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.05, 0.1])
            self.assertEqual(target.read_text(), 'new')
            self.assertFalse(source.exists())

    def test_persistent_denial_is_bounded_and_preserves_both_files(self):
        with tempfile.TemporaryDirectory(prefix='gow-replace-') as folder:
            source, target = Path(folder) / 'pending', Path(folder) / 'current'
            source.write_text('new')
            target.write_text('previous')
            error = PermissionError('persistent Windows replacement denial')
            error.winerror = 5
            with patch.object(Path, 'replace', side_effect=error) as replace, patch.object(pipeline.time, 'sleep') as sleep:
                with self.assertRaises(PermissionError):
                    pipeline.replace_file(source, target)
            self.assertEqual(replace.call_count, 6)
            self.assertEqual(sleep.call_count, 5)
            self.assertEqual(target.read_text(), 'previous')
            self.assertEqual(source.read_text(), 'new')

    def test_other_permission_errors_fail_immediately(self):
        with patch.object(Path, 'replace', side_effect=PermissionError('access denied')) as replace, patch.object(pipeline.time, 'sleep') as sleep:
            with self.assertRaises(PermissionError):
                pipeline.replace_file('pending', 'current')
        self.assertEqual(replace.call_count, 1)
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
