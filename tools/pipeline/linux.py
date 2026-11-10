"""Experimental native Linux pipeline. Python 3.12+, Clang, CMake, Ninja and Qt 6.5+.

Keeps the launcher output protocol and the existing profile/recompiler ownership
contracts. No Windows SDK, downloaded Windows tools, or Windows PGO data is used.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[2]
STAGES = ('tools', 'fetch', 'discs', 'vu1disc', 'configure', 'recomp', 'sync',
          'build', 'native', 'launcher', 'runtime-check', 'xdelta')


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def output(args, **kwargs):
    return run(args, stdout=subprocess.PIPE, text=True, **kwargs).stdout.strip()


def step(text):
    print(f'=== {text} ===', flush=True)


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


@contextmanager
def checkout_lock(root):
    import fcntl
    (root / 'data').mkdir(exist_ok=True)
    with (root / 'data/pipeline.lock').open('a+b') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another pipeline is writing this checkout') from None
        yield


def jobs():
    # Same RAM reserve as Windows; MemAvailable also respects other running apps.
    values = dict(re.findall(r'^(MemTotal|MemAvailable):\s+(\d+)',
                            Path('/proc/meminfo').read_text(), re.M))
    gib = min(int(v) for v in values.values()) / 1024**2
    return max(1, min((os.cpu_count() or 2) - 1, int(gib - 4)))


def fetch(root):
    config = tomllib.loads((root / 'engine/runtime.toml').read_text(encoding='utf-8'))
    runtime = root / 'engine/runtime'
    if not runtime.exists():
        run(['git', 'clone', config['repository'], runtime])
    git = ['git', '-C', runtime]
    if output(git + ['rev-parse', 'HEAD']) != config['commit']:
        if output(git + ['status', '--porcelain']):
            raise RuntimeError('Runtime has local changes at another commit; preserve them before fetching')
        run(git + ['fetch', 'origin'])
        run(git + ['checkout', '--detach', config['commit']])
    patches = sorted((root / 'engine/patches').glob('*.patch'), key=lambda p: p.name)
    # Match the whole prefix, including overlapping patches and newly added files.
    # The temporary index leaves the user's index and working files untouched.
    with tempfile.TemporaryDirectory(prefix='gow-patches-') as tmp:
        env = os.environ | {'GIT_INDEX_FILE': str(Path(tmp) / 'index')}
        run(git + ['read-tree', 'HEAD'], env=env)
        trees = [output(git + ['write-tree'], env=env)]
        for patch in patches:
            # Retired patches may contain documentation only, as in the Windows chain.
            run(git + ['apply', '--cached', '--allow-empty', patch], env=env)
            trees.append(output(git + ['write-tree'], env=env))
        touched = output(git + ['diff', '--name-only', 'HEAD', trees[-1]], env=env).splitlines()
        run(git + ['read-tree', 'HEAD'], env=env)
        run(git + ['add', '-u'], env=env)
        present = [p for p in touched if (runtime / p).exists()]
        if present:
            run(git + ['add', '-A', '--', *present], env=env)
        current = output(git + ['write-tree'], env=env)
        if current not in trees:
            raise RuntimeError('Runtime differs from the patch chain; preserve local work before retrying')
        for patch in patches[trees.index(current):]:
            run(git + ['apply', '--allow-empty', patch])


class Pipeline:
    def __init__(self, args):
        self.args = args
        self.root = ROOT
        self.runtime = ROOT / 'engine/runtime'
        self.source = self.runtime / 'PS2Recomp'
        self.data = ROOT / 'data' / args.game
        self.build = ROOT / 'data/build-linux' / args.game
        self.profile = tomllib.loads((ROOT / 'games' / args.game / 'game.toml').read_text(encoding='utf-8'))
        self.count = args.jobs or jobs()

    def python(self, script, *args):
        run([sys.executable, '-I', ROOT / script, *args])

    def elf(self):
        return Path(json.loads((self.data / 'languages.json').read_text(encoding='utf-8'))['recompile_elf'])

    def configure(self):
        brand = self.profile['runtime'].get('branding_image')
        extra = [f'-DGOW_BRAND_IMAGE={self.root / "games" / self.args.game / brand if brand else ""}']
        captures = self.data / 'vu1_capture'
        if any(captures.glob('*.bin')):
            sources = [captures / 'vu1n_heads_seen.txt']
            profile_heads = self.profile['runtime'].get('vu1_native_heads')
            if profile_heads:
                sources.append(self.runtime / profile_heads)
            heads = {line.strip().lower() for p in sources if p.exists()
                     for line in p.read_text(encoding='utf-8').splitlines() if re.fullmatch('[0-9a-fA-F]+', line.strip())}
            text = '\n'.join(sorted(heads)) + '\n'
            target = self.data / 'vu1n_heads.txt'
            if not target.exists() or target.read_text(encoding='utf-8') != text:
                atomic_text(target, text)
            extra += [f'-DPS2X_VU1_MICROCODE_DIR={captures}',
                      f'-DPS2X_VU1_GENERATOR_SOURCE={self.runtime / self.profile["runtime"]["vu1_generator"]}',
                      f'-DPS2X_VU1N_GEN_OVERRIDE={self.runtime / self.profile["runtime"]["vu1_native_generator"]}']
        flags = '-fno-strict-aliasing -fwrapv -fno-math-errno -fno-trapping-math -ffp-contract=off'
        run(['cmake', '-S', self.source, '-B', self.build, '-G', 'Ninja',
             '-DCMAKE_C_COMPILER=clang', '-DCMAKE_CXX_COMPILER=clang++',
             f'-DCMAKE_BUILD_TYPE={self.args.config}', '-DPS2X_CPU_ARCH=x86-64-v2',
             f'-DCMAKE_C_FLAGS={flags}', f'-DCMAKE_CXX_FLAGS={flags}',
             '-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG', '-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG',
             '-DPS2X_RELEASE_LTCG=OFF', '-DPS2X_ENABLE_SCCACHE=OFF',
             '-DPS2X_BUILD_STUDIO=OFF', '-DPS2X_BUILD_ANALYZER=OFF', '-DPS2X_BUILD_TEST=OFF',
             '-DPS2X_ENABLE_RUNTIME_LOGS=OFF', '-DPS2X_ENABLE_AGRESSIVE_LOGS=OFF',
             '-DPS2X_ENABLE_IOP_RPC_TRACE=OFF', '-DPS2X_ENABLE_FFMPEG=OFF',
             '-DPS2X_RUNNER_UNITY_BUILD_BATCH_SIZE=8', f'-DPython3_EXECUTABLE={sys.executable}',
             f'-DFETCHCONTENT_UPDATES_DISCONNECTED={"OFF" if "fetch" in self.args.stages else "ON"}', *extra])

    def compile(self, target):
        run(['cmake', '--build', self.build, '--parallel', self.count, '--target', target])
        print('@@progress 1 1', flush=True)

    def execute(self, stage):
        if stage == 'tools':
            step('tools (Linux system dependencies)')
            missing = [p for p in ('git', 'cmake', 'ninja', 'clang', 'clang++', 'pkg-config') if not shutil.which(p)]
            if missing:
                raise RuntimeError('Missing tools: ' + ', '.join(missing) + '; see docs/linux.md')
        elif stage == 'fetch':
            step('runtime (PS2Recomp + Tobiichi)')
            fetch(ROOT)
        elif stage == 'discs':
            step('discs')
            if not self.args.discs:
                raise RuntimeError('No discs supplied (--discs <ISO>)')
            self.python('tools/disc/prepare.py', '--game', self.args.game, '--data', ROOT / 'data', *self.args.discs)
        elif stage == 'configure':
            step('configure (Linux, Clang)')
            self.configure()
        elif stage == 'recomp':
            step('recompile the executable')
            self.compile('ps2_recomp')
            self.python('tools/pipeline/recompile.py', 'recomp', '--root', ROOT, '--game', self.args.game,
                        '--build', self.build, '--codegen', self.args.codegen)
        elif stage == 'sync':
            step('generated code into the runner')
            self.python('tools/pipeline/recompile.py', 'sync', '--root', ROOT, '--game', self.args.game)
            self.python('tools/disc/save_slots.py', '--prepare-data', self.data, '--game', self.args.game)
        elif stage in ('build', 'native'):
            step('build the game (Linux, Clang)' if stage == 'build' else 'native (Linux recorded VU1)')
            self.configure()
            self.compile('ps2EntryRunner')
            atomic_text(ROOT / 'data/build-root-linux.txt', str(self.build) + '\n')
            if stage == 'native':
                atomic_text(self.data / 'native.stamp', 'Linux VU1 build complete\n')
            if 'fetch' in self.args.stages:
                (ROOT / 'data/needs-rebuild.txt').unlink(missing_ok=True)
        elif stage == 'runtime-check':
            step('build the runtime library (no disc)')
            self.configure()
            self.compile('ps2_runtime')
        elif stage == 'launcher':
            step('launcher (Linux, Qt)')
            folder = ROOT / 'data/build-linux/launcher'
            run(['cmake', '-S', ROOT / 'launcher', '-B', folder, '-G', 'Ninja',
                 '-DCMAKE_CXX_COMPILER=clang++', f'-DCMAKE_BUILD_TYPE={self.args.config}'])
            run(['cmake', '--build', folder, '--parallel', self.count])
        elif stage == 'vu1disc':
            step('VU1 microcode from the disc')
            self.python('tools/disc/vu1_from_disc.py', '--game', self.args.game, '--gen',
                        self.runtime / self.profile['runtime']['vu1_native_generator'], self.elf().parent,
                        self.data / 'vu1_capture')
        elif stage == 'xdelta':
            step('apply the ISO patch (xdelta)')
            if not self.args.xdelta or len(self.args.discs) != 1:
                raise RuntimeError('xdelta needs --xdelta <patch> and exactly one base ISO')
            target = ROOT / 'data/mods/isos' / (Path(self.args.xdelta).stem + '.iso')
            target.parent.mkdir(parents=True, exist_ok=True)
            pending = target.with_suffix('.iso.partial')
            try:
                self.python('tools/disc/vcdiff.py', 'apply', self.args.xdelta, self.args.discs[0], pending)
                pending.replace(target)
            finally:
                pending.unlink(missing_ok=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stages', default='tools,fetch,discs,configure,recomp,sync,build,launcher')
    parser.add_argument('--game', default='gow1')
    parser.add_argument('--discs', nargs='+', default=[])
    parser.add_argument('--xdelta')
    parser.add_argument('--config', choices=('Release', 'RelWithDebInfo'), default='Release')
    parser.add_argument('--codegen', choices=('classic', 'locals'), default='locals')
    parser.add_argument('--jobs', type=int)
    args = parser.parse_args(argv)
    args.stages = args.stages.split(',')
    if any(s not in STAGES for s in args.stages):
        parser.error('Supported Linux stages: ' + ','.join(STAGES))
    if not re.fullmatch('[a-zA-Z0-9_-]+', args.game):
        parser.error('Invalid game identifier')
    if args.jobs is not None and args.jobs < 1:
        parser.error('--jobs must be positive')
    return args


def main():
    args = parse_args()
    if sys.platform != 'linux' or platform.machine() not in ('x86_64', 'AMD64'):
        raise RuntimeError('This entry point requires native x86-64 Linux; use build.cmd on Windows')
    if sys.version_info < (3, 12):
        raise RuntimeError('Python 3.12 or newer is required')
    # Private process group: cancellation cannot terminate another checkout's build.
    if os.getpgrp() != os.getpid():
        os.setsid()
    def cancel(signum, frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        os.killpg(os.getpgrp(), signal.SIGTERM)
        raise RuntimeError('Build cancelled')
    signal.signal(signal.SIGTERM, cancel)
    with checkout_lock(ROOT):
        pipeline = Pipeline(args)
        for stage in args.stages:
            pipeline.execute(stage)


if __name__ == '__main__':
    try:
        main()
    except SystemExit as error:
        if error.code:
            print('ERROR: Invalid Linux pipeline arguments; see --help', flush=True)
            sys.exit(1)
        raise
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', flush=True)
        sys.exit(1)
