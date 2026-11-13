"""Turn one or more disc images of a game into runnable disc folders, one per language, and list them for the launcher.

usage: python -I tools/disc/prepare.py --game <id> --data <data dir> <iso or extracted folder> [...]

Output (under <data>/<game>/):
  discs/<edition>/        each compatible disc extracted (iso_extract.py --layout) and normalised so the port runs it
                          on its own: IOP_MOD/ copies of the IRX modules; with no PART2.PAK the TOC's part-1 entries
                          point at their part-0 copies; empty or profile-fingerprinted placeholder widescreen movies
                          (.PSW) point at the 4:3 ones (.PSS)
  discs/<edition>-full/   a translation on top of an original disc of the same game when both were given: hard links to
                          the original (all its movies, widescreen included), the translation's text files placed past
                          the end of the disc, and the original executable with the translation's data changes (the
                          code is checked to be identical; a change that hides the widescreen option is left out)
  mc0/                    the one memory card folder: every disc folder's mc0 is a junction to it
  languages.json          [{language, label, edition, elf, quality: "full"|"standalone"|"original"}], one per
                          language (the best folder), plus "recompile_elf" (the executable the pipeline recompiles).
                          Paths inside the repository are stored relative to its root (discfs.root_relative), so a moved
                          or copied installation still finds its discs; every reader resolves them against the root
A disc whose profile region declares `code = "<region id>"` carries that region's executable (the Asia SCAJ-97399
disc boots the Japanese copy byte for byte): it is extracted and normalised like any other, its executable is also
linked under the name that build keys on, and it is reported for register_region.py instead of entering
languages.json, because that manifest feeds the USA pipeline and the primary installation's Play list. Pass a
regional disc its own --data directory: regional cards and saves must not mix with the primary ones.
Discs whose executable is not the profile's game code are reported and skipped. Re-running is cheap: an already
extracted disc (same image size and time) is kept.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'pipeline'))
import discfs  # noqa: E402
import identify  # noqa: E402
import chd  # noqa: E402
import profile as profiles  # noqa: E402
import save_slots  # noqa: E402

SECTOR = discfs.SECTOR
ROOT = os.path.dirname(os.path.dirname(HERE))


def say(msg):
    print(msg, flush=True)


def junction(link, target):
    os.makedirs(target, exist_ok=True)
    if os.path.lexists(link):
        return
    try:
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', os.path.abspath(link), os.path.abspath(target)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.symlink(os.path.abspath(target), link)
    except (subprocess.CalledProcessError, OSError):
        # exFAT / FAT32 drives (USB disks) have no folder links: this disc keeps a memory card of its own
        os.makedirs(link, exist_ok=True)
        say(f'  {os.path.basename(os.path.dirname(link))}: this drive has no folder links (exFAT/FAT32?), '
            'so this language keeps its own memory card')


def extract(src, dst):
    """an ISO -> extracted folder (kept when the same image was extracted before); a folder is used as it is"""
    if os.path.isdir(src):
        return os.path.abspath(src)
    stamp = f'{os.path.getsize(src)} {int(os.path.getmtime(src))}'
    marker = os.path.join(dst, '.source')
    if os.path.isfile(marker):
        with open(marker, encoding='utf-8', errors='replace') as saved:
            previous = saved.read().splitlines()
        if previous[:2] == [stamp, os.path.abspath(src)]:
            say(f'  already extracted: {dst}')
            return dst
    os.makedirs(dst, exist_ok=True)
    say(f'  extracting {os.path.basename(src)} -> {dst}')
    subprocess.run([sys.executable, '-I', os.path.join(HERE, 'iso_extract.py'), src, dst, '--layout'], check=True)
    with open(marker, 'w', encoding='utf-8') as saved:
        saved.write(stamp + '\n' + os.path.abspath(src) + '\n')
    return dst


def expose_for_build(folder, elf_name, build_elf):
    """Give the disc's executable the name the build that runs it expects (same bytes, second name).

    The runtime registers its per-game overrides and gates the native integration on the executable name it is
    handed, so a disc that carries another edition's code (the Asia SCAJ-97399 image boots the Japanese copy)
    has to be presented under that edition's name. The image is untouched: `.disc_layout` keeps describing the
    disc as pressed, and the link is a second name for the same file.
    """
    source, link = os.path.join(folder, elf_name), os.path.join(folder, build_elf)
    if elf_name == build_elf or not os.path.isfile(source):
        return False
    if not os.path.exists(link):
        try:
            os.link(source, link)
        except OSError:
            shutil.copy2(source, link)
    return True


def normalise(folder, prof):
    """make an extracted disc self-sufficient for the port (see the module docstring)"""
    d = prof['disc']
    iop = os.path.join(folder, d.get('iop_modules_dir', 'IOP_MOD'))
    os.makedirs(iop, exist_ok=True)
    for n in os.listdir(folder):
        if n.upper().endswith('.IRX') and os.path.isfile(os.path.join(folder, n)):
            # The guest requests lowercase IRX names; ISO9660 names are uppercase.
            # Keep both on case-sensitive hosts, including already prepared discs.
            for name in (n, n.lower()):
                destination = os.path.join(iop, name)
                if not os.path.exists(destination):
                    shutil.copy2(os.path.join(folder, n), destination)
    toc_name = d.get('toc')
    if not toc_name or not os.path.isfile(os.path.join(folder, toc_name)):
        return []
    orig = os.path.join(folder, toc_name + '.orig')
    if not os.path.isfile(orig):
        shutil.copy2(os.path.join(folder, toc_name), orig)
    with open(orig, 'rb') as stream:
        raw = bytearray(stream.read())
    toc = discfs.parse_toc(bytes(raw))
    notes = []
    part0 = {}
    for _, name, part, size, sector in toc:
        if part == 0:
            part0.setdefault(name, (size, sector))
    paks = d.get('paks', [])
    if len(paks) > 1 and not os.path.isfile(os.path.join(folder, paks[1])):
        moved = 0
        for i, name, part, size, sector in toc:
            if part == 1 and name in part0:
                struct.pack_into('<III', raw, i + 12, 0, *part0[name])
                moved += 1
        notes.append(f'no {paks[1]}: {moved} TOC entries moved to their {paks[0]} copies')
    wide, movie = d.get('widescreen_movie_ext'), d.get('movie_ext')
    placeholders = d.get('widescreen_placeholders', [])

    def is_placeholder(part, size, sector):
        candidates = {item['sha256'] for item in placeholders if item['size'] == size}
        if not candidates or not 0 <= part < len(paks):
            return False
        path = os.path.join(folder, paks[part])
        if not os.path.isfile(path):
            return False
        with open(path, 'rb') as stream:
            stream.seek(sector * SECTOR)
            payload = stream.read(size)
        return len(payload) == size and hashlib.sha256(payload).hexdigest() in candidates

    if wide and movie:
        mapped = 0
        for i, name, part, size, sector in toc:
            # Missing-part remapping above may have changed the payload being inspected.
            part, size, sector = struct.unpack_from('<III', raw, i + 12)
            if name.endswith(wide) and (size <= SECTOR or is_placeholder(part, size, sector)):
                base = name[:-len(wide)] + movie
                if base in part0 and part0[base][0] > size:
                    struct.pack_into('<III', raw, i + 12, 0, *part0[base])
                    mapped += 1
        if mapped:
            notes.append(f'{mapped} empty/known-placeholder widescreen movies ({wide}) mapped to {movie}')
    with open(os.path.join(folder, toc_name), 'wb') as stream:
        stream.write(raw)
    return notes


def translated_elf(orig_elf, trans_elf):
    """the original executable with the translation's data changes (same code checked)"""
    sections = discfs.elf_sections(orig_elf)
    if len(orig_elf) != len(trans_elf) or discfs.elf_sections(trans_elf) != sections:
        raise ValueError('the translated executable has another layout')
    off, size, _ = sections['.text']
    if orig_elf[off:off + size] != trans_elf[off:off + size]:
        raise ValueError('the translation changes the game code')
    out, i, n, runs = bytearray(orig_elf), 0, len(orig_elf), 0
    while i < n:
        if orig_elf[i] == trans_elf[i]:
            i += 1
            continue
        j = i
        while j < n and orig_elf[j:j + 8] != trans_elf[j:j + 8]:
            j += 1
        if b'WideScreen' not in orig_elf[i - 16:j + 16]:
            if any(soff <= i and j <= soff + ssize and vaddr for soff, ssize, vaddr in sections.values()):
                out[i:j] = trans_elf[i:j]
                runs += 1
        i = j
    return bytes(out), runs


def merge_translation(orig_dir, trans_dir, out, prof):
    """<edition>-full: the original disc + the translation's text and executable data (see the module docstring)"""
    d = prof['disc']
    elf_name = prof['executable']['name']
    orig, trans = discfs.FolderDisc(orig_dir), discfs.FolderDisc(trans_dir)
    toc_raw = open(os.path.join(orig_dir, d['toc'] + '.orig') if os.path.isfile(os.path.join(orig_dir, d['toc'] + '.orig'))
                   else os.path.join(orig_dir, d['toc']), 'rb').read()
    toc = discfs.parse_toc(toc_raw)
    trans_toc = discfs.parse_toc(open(os.path.join(trans_dir, d['toc'] + '.orig'), 'rb').read())
    own = {elf_name, d['toc'], '.disc_layout', '.source', d['toc'] + '.orig'}
    os.makedirs(out, exist_ok=True)
    for root, dirs, files in os.walk(orig_dir):
        dirs[:] = [x for x in dirs if x != 'mc0']
        rel = os.path.relpath(root, orig_dir)
        os.makedirs(os.path.join(out, rel), exist_ok=True)
        for f in files:
            if rel == '.' and f in own:
                continue
            s, t = os.path.join(root, f), os.path.join(out, rel, f)
            if os.path.exists(t):
                if os.path.samefile(s, t):
                    continue
                os.remove(t)
            try:
                os.link(s, t)
            except OSError:
                shutil.copy2(s, t)
    sectors = int(orig.head['sectors'])
    part2 = orig.lsn(d['paks'][1])
    patched, extra, lsn = bytearray(toc_raw), [], sectors
    for name in d.get('text_files', []):
        data = discfs.check_wad(trans.pak_entry(trans_toc, name))
        fname = 'TR_' + name
        open(os.path.join(out, fname), 'wb').write(data)
        for i, n, part, size, sector in toc:
            if n == name:
                struct.pack_into('<III', patched, i + 12, 1, len(data), lsn - part2)
        extra.append((lsn, len(data), fname))
        lsn += (len(data) + SECTOR - 1) // SECTOR
    open(os.path.join(out, d['toc']), 'wb').write(patched)
    elf, runs = translated_elf(orig.read(elf_name), trans.read(elf_name))
    open(os.path.join(out, elf_name), 'wb').write(elf)
    lines = [f'sectors {lsn}'] + [f'{k} {v}' for k, v in orig.head.items() if k != 'sectors']
    lines += [f'file {l} {s} {n}' for l, s, n in sorted(orig.layout + extra)]
    open(os.path.join(out, '.disc_layout'), 'w', newline='\n').write('\n'.join(lines) + '\n')
    return runs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--game', required=True)
    ap.add_argument('--data', required=True)
    ap.add_argument('discs', nargs='+')
    a = ap.parse_args()
    prof = profiles.load(a.game)
    base = os.path.join(a.data, a.game)
    card = os.path.join(base, 'mc0')
    found = []
    regional = []
    for src in a.discs:
        resolved = chd.resolve(src, os.path.join(a.data, 'imports', 'chd'))
        info = identify.identify(resolved)
        if info.get('game') != a.game:
            say(f'skipped {src}: {"; ".join(info["problems"]) or "another game"}')
            continue
        build = identify.region_by_id(prof, info.get('code'))
        if not (info.get('compatible') or build):
            say(f'skipped {src}: {"; ".join(info["problems"])}')
            continue
        say(f'{info["label"]} [{info["kind"]}] <- {src}')
        folder = extract(resolved, os.path.join(base, 'discs', info['edition']))
        notes = normalise(folder, prof)
        if build:
            if expose_for_build(folder, info['elf'], build['elf']):
                notes.append(f'{info["elf"]} is also {build["elf"]}: the {build["id"]} build keys on that name')
            for note in notes:
                say(f'  {note}')
            if os.path.abspath(base) == os.path.abspath(os.path.join(ROOT, 'data', a.game)):
                say('  this is the primary installation: a regional disc keeps its own cards and saves, '
                    'so prepare it with its own --data')
            junction(os.path.join(folder, 'mc0'), card)
            regional.append(dict(info, folder=folder, build=build['id'], runner_elf=os.path.join(folder, build['elf'])))
            continue
        for note in notes:
            say(f'  {note}')
        junction(os.path.join(folder, 'mc0'), card)
        found.append(dict(info, folder=folder))
    for f in regional:
        say(f'register {f["label"]}: python -I tools/pipeline/register_region.py --game {a.game} '
            f'--region {f["edition"]} --runner "<the {f["build"]} runner>" --elf "{f["runner_elf"]}" '
            '--data "<its own data directory>"')
    if not found:
        if regional:
            say('only regional discs were given: nothing to write in languages.json (they are registered instead)')
            return
        sys.exit('no compatible disc of ' + prof['title'])
    originals = [f for f in found if f['kind'] == 'original']
    languages = {}
    elf_name = prof['executable']['name']
    for f in found:
        quality = 'original' if f['kind'] == 'original' else 'standalone'
        folder = f['folder']
        if f['kind'] != 'original' and originals:
            folder = os.path.join(base, 'discs', f['edition'] + '-full')
            runs = merge_translation(originals[0]['folder'], f['folder'], folder, prof)
            junction(os.path.join(folder, 'mc0'), card)
            quality = 'full'
            say(f'  {f["label"]}: full version on the original disc ({runs} executable data changes)')
        try:
            save_slots.prepare_assets(folder, prof, f['language'])
        except (OSError, ValueError, KeyError) as error:
            say(f'  Save previews unavailable: {error}')
        entry = {'language': f['language'], 'label': f['label'], 'edition': f['edition'], 'quality': quality,
                 'elf': discfs.root_relative(os.path.join(folder, elf_name), ROOT)}
        rank = {'original': 3, 'full': 2, 'standalone': 1}
        if f['language'] not in languages or rank[quality] > rank[languages[f['language']]['quality']]:
            languages[f['language']] = entry
    recompile = discfs.root_relative(os.path.join((originals or found)[0]['folder'], elf_name), ROOT)
    manifest = {'game': a.game, 'title': prof['title'], 'recompile_elf': recompile,
                'languages': sorted(languages.values(), key=lambda e: e['language'])}
    json.dump(manifest, open(os.path.join(base, 'languages.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    say(f'{base}/languages.json: ' + ', '.join(f'{e["language"]} ({e["quality"]})' for e in manifest['languages']))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    main()
