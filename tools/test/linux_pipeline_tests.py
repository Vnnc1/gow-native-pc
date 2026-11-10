"""Linux orchestration tests without an ISO or native compiler."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('linux_pipeline', ROOT / 'tools/pipeline/linux.py')
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


class LinuxPipelineTests(unittest.TestCase):
    def test_rejects_unsupported_stages_before_work(self):
        for stage in ('pgo', 'tune', 'optimize', 'build,unknown'):
            with self.subTest(stage=stage), self.assertRaises(SystemExit):
                pipeline.parse_args(['--stages', stage])

    def test_rejects_traversal_and_invalid_parallelism(self):
        for args in (['--game', '../gow1'], ['--jobs', '0'], ['--jobs', '-1']):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                pipeline.parse_args(args)

    def test_iso_paths_are_distinct_arguments(self):
        args = pipeline.parse_args(['--stages', 'discs', '--jobs', '1', '--discs', '/a b/game.iso', '/c/game.iso'])
        work = pipeline.Pipeline(args)
        with patch.object(work, 'python') as invoke:
            work.execute('discs')
        self.assertEqual(invoke.call_args.args[-2:], ('/a b/game.iso', '/c/game.iso'))

    def test_configure_preserves_portable_flags_without_windows_pgo(self):
        args = pipeline.parse_args(['--stages', 'configure', '--jobs', '1'])
        work = pipeline.Pipeline(args)
        with tempfile.TemporaryDirectory() as temporary, patch.object(pipeline, 'run') as invoke:
            work.data = Path(temporary)
            work.configure()
        command = invoke.call_args.args[0]
        self.assertIn('-DPS2X_CPU_ARCH=x86-64-v2', command)
        self.assertIn('-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG', command)
        self.assertIn('-DPS2X_ENABLE_FFMPEG=OFF', command)
        self.assertIn(f'-DGOW_BRAND_IMAGE={work.root / "games" / args.game / work.profile["runtime"]["branding_image"]}', command)
        text = ' '.join(map(str, command))
        self.assertNotIn('-static', text)
        self.assertNotIn('profile-instr-use', text)
        self.assertNotIn('-march=native', text)

    def test_failed_build_does_not_publish_runner(self):
        args = pipeline.parse_args(['--stages', 'build', '--jobs', '1'])
        work = pipeline.Pipeline(args)
        with patch.object(work, 'configure'), patch.object(work, 'compile', side_effect=RuntimeError('build failed')):
            with patch.object(pipeline, 'atomic_text') as write, self.assertRaises(RuntimeError):
                work.execute('build')
            write.assert_not_called()

    def test_patch_prefix_resume_and_local_edits_preserved(self):
        with tempfile.TemporaryDirectory(prefix='gow-linux-test-') as temporary:
            root = Path(temporary)
            runtime = root / 'engine/runtime'
            runtime.mkdir(parents=True)
            patches = root / 'engine/patches'
            patches.mkdir()
            git = ['git', '-C', str(runtime)]
            def command(*args):
                return subprocess.run(git + list(args), check=True, capture_output=True, text=True).stdout.strip()
            command('init')
            command('config', 'user.email', 'test@example.invalid')
            command('config', 'user.name', 'Test')
            command('config', 'core.autocrlf', 'false')
            source = runtime / 'code.txt'
            source.write_text('one\n', encoding='utf-8')
            command('add', 'code.txt')
            command('commit', '-m', 'base')
            commit = command('rev-parse', 'HEAD')
            (root / 'engine/runtime.toml').write_text(f'repository="unused"\ncommit="{commit}"\n')
            for name, before, after in [('29-fix.patch', 'one', 'two'), ('29a-next.patch', 'two', 'three')]:
                (patches / name).write_text(f'diff --git a/code.txt b/code.txt\n--- a/code.txt\n+++ b/code.txt\n@@ -1 +1 @@\n-{before}\n+{after}\n', encoding='utf-8')
            # Retired patches remain as notes in the ordinal chain (for example patch 85).
            (patches / '29-note.patch').write_text('Already included by earlier patches.\n', encoding='utf-8')
            (patches / '30-empty.patch').write_text('', encoding='utf-8')
            command('apply', str(patches / '29-fix.patch'))
            pipeline.fetch(root)
            self.assertEqual(source.read_text(), 'three\n')
            pipeline.fetch(root)
            self.assertEqual(command('diff', '--cached'), '')
            source.write_text('local work\n')
            with self.assertRaisesRegex(RuntimeError, 'differs from the patch chain'):
                pipeline.fetch(root)
            self.assertEqual(source.read_text(), 'local work\n')
            source.write_text('three\n', encoding='utf-8')
            (patches / '31-invalid.patch').write_text(
                'diff --git a/code.txt b/code.txt\n--- a/code.txt\n+++ b/code.txt\n'
                '@@ -1 +1 @@\n-not the current source\n+four\n', encoding='utf-8')
            with self.assertRaises(subprocess.CalledProcessError):
                pipeline.fetch(root)
            self.assertEqual(source.read_text(), 'three\n')
            self.assertEqual(command('diff', '--cached'), '')

    @unittest.skipUnless(os.name == 'posix', 'requires flock')
    def test_lock_excludes_second_writer_and_releases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with pipeline.checkout_lock(root):
                with self.assertRaisesRegex(RuntimeError, 'Another pipeline'):
                    with pipeline.checkout_lock(root):
                        self.fail('second writer acquired lock')
            with pipeline.checkout_lock(root):
                pass


if __name__ == '__main__':
    unittest.main()
