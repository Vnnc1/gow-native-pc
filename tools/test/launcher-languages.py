"""Checks the launcher's per-language text files (launcher/qml/idiomas/*.js) against Textos.js.

Every key of a language file must exist in Textos.js, every key of Textos.js should be translated (missing ones fall
back to English: reported, not an error), and a translation must keep the English text's %1/%2 placeholders.
Run: python -I tools/test/launcher-languages.py   (exit code 1 on an error)
"""
import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parents[2]
qml = root / "launcher" / "qml"
string = r'"((?:[^"\\]|\\.)*)"'
table = (qml / "Textos.js").read_text(encoding="utf-8")
table = table[table.index("var tabla = {"):table.index("function texto")]
english = {}
for line in table.splitlines():
    m = re.match(r'^\s*([A-Za-z0-9_]+):\s*\{(.*)\},?\s*$', line)
    if m:
        en = re.search(r'"?en"?:\s*' + string, m.group(2))
        english[m.group(1)] = en.group(1) if en else ""

errors = 0
files = sorted((qml / "idiomas").glob("*.js"))
for path in files:
    text = path.read_text(encoding="utf-8")
    if not text.startswith(".pragma library") or "var textos = {" not in text:
        print(f"ERROR {path.name}: expected '.pragma library' and 'var textos = {{'")
        errors += 1
        continue
    found = {}
    for line in text.splitlines():
        m = re.match(r'^\s*([A-Za-z0-9_]+):\s*' + string + r',?\s*$', line)
        if m:
            if m.group(1) in found:
                print(f"ERROR {path.name}: duplicate key {m.group(1)}")
                errors += 1
            found[m.group(1)] = m.group(2)
        elif re.match(r'^\s*[A-Za-z0-9_]+:', line):
            print(f"ERROR {path.name}: unparsed line: {line.strip()[:80]}")
            errors += 1
    for key, value in found.items():
        if key not in english:
            print(f"ERROR {path.name}: unknown key {key}")
            errors += 1
        elif sorted(re.findall(r"%\d", value)) != sorted(re.findall(r"%\d", english[key])):
            print(f"ERROR {path.name}: {key} placeholders {re.findall(r'%[0-9]', value)} != English")
            errors += 1
    missing = [k for k in english if k not in found]
    print(f"{path.name}: {len(found)} of {len(english)} texts" + (f", missing (English shown): {', '.join(missing)}" if missing else ""))
print("FAIL" if errors else "PASS: launcher language files")
sys.exit(1 if errors else 0)
