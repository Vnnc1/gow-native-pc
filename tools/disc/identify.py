"""Identify a PS2 disc (ISO image or extracted folder) against the game profiles: which game, which edition, which
language, and whether the port can run it.

usage: python -I tools/disc/identify.py <iso or folder> [...]      prints one JSON object per disc (a JSON list)

Fields: path, game, title, edition, kind (original | translation | unknown), language, label, elf, elf_crc,
compatible (the executable has the profile's game code), has_widescreen_movies, has_part2, problems[].
Matching: SYSTEM.CNF's boot ELF name -> profile; ELF CRC -> known edition; else the ELF's .text SHA-1 decides
compatibility and the language is guessed from words in the profile's text files (language_hints).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'pipeline'))
import discfs  # noqa: E402
import chd  # noqa: E402
import profile as profiles  # noqa: E402


# launcher labels of guessed languages (a translation that is not a known edition)
LANGUAGE_NAMES = {'pt-BR': 'Português (Brasil)', 'es': 'Español', 'fr': 'Français', 'de': 'Deutsch',
                  'it': 'Italiano', 'en': 'English'}


def guess_language(disc, prof, toc):
    hints = prof.get('language_hints', {})
    text = b''
    for name in prof['disc'].get('text_files', []):
        try:
            text += disc.pak_entry(toc, name)
        except KeyError:
            pass
    best, score = None, 0
    for lang, words in hints.items():
        s = sum(text.count(w.encode('latin1', 'ignore')) for w in words)
        if s > score:
            best, score = lang, s
    return best


def identify(path, cache=None):
    original = os.path.abspath(path)
    resolved = chd.resolve(path, cache)
    disc = discfs.open_disc(resolved)
    try:
        result = identify_disc(disc, original)
        result['format'] = 'chd' if original.lower().endswith('.chd') else 'iso' if os.path.isfile(original) else 'folder'
        return result
    finally:
        if isinstance(disc, discfs.IsoDisc):
            disc.f.close()


def identify_disc(disc, path):
    out = {'path': os.path.abspath(path), 'game': None, 'compatible': False, 'problems': []}
    if not disc.has('SYSTEM.CNF'):
        out['problems'].append('no SYSTEM.CNF: not a PS2 game disc')
        return out
    elf_name = discfs.boot_elf_name(disc.read('SYSTEM.CNF'))
    out['elf'] = elf_name
    prof = next((p for p in profiles.all_profiles() if p['executable']['name'].upper() == elf_name.upper()
                 or any(r['elf'].upper() == elf_name.upper() for r in p.get('regions', []))), None)
    if prof is None:
        out['problems'].append(f'unknown game (boot ELF {elf_name}): no profile in games/')
        return out
    out.update(game=prof['id'], title=prof['title'])
    elf = disc.read(elf_name)
    out['elf_crc'] = discfs.pcsx2_crc(elf)
    region = next((r for r in prof.get('regions', []) if r['elf'].upper() == elf_name.upper()), None)
    if region:
        out.update(edition=region['id'], kind='demo' if region.get('demo') else 'original',
                   region=region['id'], language=region['language'], label=region['label'])
        out['text_sha1'] = discfs.text_sha1(elf)
        out['expected_text_sha1'] = prof['executable']['text_sha1']
        out['reason_code'] = 'demo_excluded' if region.get('demo') else 'region_not_ported'
        out['problems'].append('Demo editions are excluded.' if region.get('demo') else
                               'Recognized regional edition; its executable/runtime mapping is not supported yet. '
                               'Renaming the ISO or executable does not make it compatible.')
        return out
    try:
        code_ok = bool(prof['executable']['text_sha1']) and discfs.text_sha1(elf) == prof['executable']['text_sha1']
    except Exception:
        code_ok = False
    out['compatible'] = code_ok and prof.get('status') != 'planned'
    if not code_ok:
        out['problems'].append('the executable is not the game code the port was built for (other region or a '
                               'translation that changes code)')
    if prof.get('status') == 'planned':
        out['problems'].append(f'{prof["title"]} is not supported yet (status: planned)')
    edition = next((e for e in prof.get('editions', []) if e.get('elf_crc') and e['elf_crc'] == out['elf_crc']), None)
    toc = []
    if prof['disc'].get('toc') and disc.has(prof['disc']['toc']):
        toc = discfs.parse_toc(disc.read(prof['disc']['toc']))
    if edition:
        out.update(edition=edition['id'], kind=edition['kind'], language=edition['language'], label=edition['label'])
    else:
        lang = guess_language(disc, prof, toc) if toc else None
        if code_ok and lang:
            label = f'{LANGUAGE_NAMES.get(lang, lang)} — fan translation'
            edition_id = f'translation-{lang.lower()}-{out["elf_crc"].lower()}'
        else:
            label = f'{lang or "unknown language"} (unrecognised disc {out["elf_crc"]})'
            edition_id = 'unknown-' + out['elf_crc'].lower()
        out.update(edition=edition_id, kind='translation' if code_ok else 'unknown', language=lang or 'unknown',
                   label=label)
    wide = prof['disc'].get('widescreen_movie_ext')
    sizes = [e[3] for e in toc if wide and e[1].endswith(wide)]
    out['has_widescreen_movies'] = bool(sizes) and min(sizes) > 2048
    out['has_part2'] = len(prof['disc'].get('paks', [])) < 2 or disc.has(prof['disc']['paks'][1])
    return out


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    results = []
    for path in sys.argv[1:]:
        try:
            results.append(identify(path))
        except Exception as error:
            results.append({'path': os.path.abspath(path), 'game': None, 'compatible': False,
                            'reason_code': 'import_failed', 'problems': [str(error)]})
    json.dump(results, sys.stdout, ensure_ascii=False, indent=1)
    print()
