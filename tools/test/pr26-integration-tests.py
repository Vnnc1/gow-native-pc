"""Behavioral regressions for PR 26 integration; synthetic files only."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


mods = module('mods_integration', ROOT / 'tools/mods/gow_mods_cli.py')
frames = module('frames_integration', ROOT / 'tools/test/frame-equivalence.py')
sys.path.insert(0, str(ROOT / 'tools/disc'))
from import_test import elf
from discfs import text_sha1, pcsx2_crc


class Integration(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.ctx = mods.Context(self.root, self.root / 'mods')
        self.payload = elf()
        profile = self.root / 'games/gow1/game.toml'
        profile.parent.mkdir(parents=True)
        profile.write_text('id="gow1"\n[executable]\nname="USA.ELF"\nserial="USA"\n'
                           f'text_sha1="{text_sha1(self.payload)}"\n[[editions]]\nid="usa"\n')
        self.registry = self.root / 'data/gow1/regional-builds.json'
        self.registry.parent.mkdir(parents=True)
        self.registry.write_text(json.dumps({'builds': [{'region': 'japan', 'code': 'japan'}]}))

    def test_registration_order_is_not_selection(self):
        self.assertEqual(mods.gather_fingerprint(self.ctx)['region'], 'usa')

    def test_selected_runner_and_elf_bind_identity(self):
        game = self.root / 'USA.ELF'
        game.write_bytes(self.payload)
        runner = self.root / 'build/ps2xRuntime/runner.exe'
        runner.parent.mkdir(parents=True)
        runner.write_bytes(b'synthetic runner')
        cache = runner.parent.parent / 'CMakeCache.txt'
        cache.write_text(f'CMAKE_HOME_DIRECTORY:INTERNAL={self.root}/engine/runtime/PS2Recomp\n')
        ctx = mods.Context(self.root, self.root / 'mods', game, runner)
        first = mods.gather_fingerprint(ctx)
        self.assertEqual(first['elfCrc'], pcsx2_crc(self.payload))
        runner.write_bytes(b'changed runner')
        self.assertNotEqual(first['fingerprintId'], mods.gather_fingerprint(ctx)['fingerprintId'])
        cache.write_text('CMAKE_HOME_DIRECTORY:INTERNAL=C:/another-copy\n')
        with self.assertRaises(mods.ManagerError):
            mods.gather_fingerprint(ctx)

    def test_selected_regional_build_is_validated(self):
        game = self.root / 'JAPAN.ELF'
        game.write_bytes(self.payload)
        runner = self.root / 'regional/ps2xRuntime/runner.exe'
        runner.parent.mkdir(parents=True)
        runner.write_bytes(b'regional runner')
        source = self.root / 'regional-source'
        (runner.parent.parent / 'CMakeCache.txt').write_text(f'CMAKE_HOME_DIRECTORY:INTERNAL={source}\n')
        self.registry.write_text(json.dumps({'builds': [{
            'region': 'japan', 'elf': str(game), 'runner': str(runner), 'source': str(source),
            'elf_sha256': mods.sha256_file(game), 'runner_sha256': mods.sha256_file(runner),
            'elf_crc': pcsx2_crc(self.payload), 'text_sha1': text_sha1(self.payload)}]}))
        ctx = mods.Context(self.root, self.root / 'mods', game, runner)
        self.assertEqual(mods.gather_fingerprint(ctx)['region'], 'japan')
        runner.write_bytes(b'changed')
        with self.assertRaises(mods.ManagerError):
            mods.gather_fingerprint(ctx)

    def test_conflict_removes_transitive_dependents(self):
        for name, extra in [('provider', ''), ('dependent', '[requires]\nmods=["provider"]\n'),
                            ('transitive', '[requires]\nmods=["dependent"]\n'),
                            ('winner', 'priority=100\n[conflicts]\nmods=["provider"]\n')]:
            folder = self.ctx.packages_dir / (name + '@1.0.0')
            folder.mkdir()
            (folder / 'mod.toml').write_text(f'spec=1\nid="{name}"\nname="{name}"\nversion="1.0.0"\n'
                                            + extra + '[target]\ngame_id="gow1"\n[env]\nGOW_SCALER="1"\n')
        mods.write_profile(self.ctx, 'test', ['provider', 'dependent', 'transitive', 'winner'])
        plan = mods.build_plan(self.ctx, 'test', mods.scan_packages(self.ctx))
        self.assertEqual([item['id'] for item in plan['mods']], ['winner'])
        self.assertEqual(len(plan['excluded']), 3)

    def test_frame_self_check_runs_twice_and_requires_all_frames(self):
        capture = self.root / 'capture.ppm'
        capture.write_bytes(b'P6\n1 1\n255\n\0\0\0')
        argv = ['frames', '--base-runner', 'runner.exe', '--disc', str(self.root),
                '--out', str(self.root / 'out')]
        with patch.object(sys, 'argv', argv), patch.object(frames, 'run_one', return_value=([capture], 1, 0)) as run:
            self.assertEqual(frames.main(), 1)
            self.assertEqual(run.call_count, 2)


if __name__ == '__main__':
    unittest.main()
