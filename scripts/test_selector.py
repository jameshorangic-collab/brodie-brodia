"""Dependency-free check for the P05 selector page (web/index.html).

Checks that the radio options and the JS enums match the shared selection contract,
that the start hook never claims a connection, and (if `node` is installed) runs
validateSelection() against valid and invalid inputs.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / 'web' / 'index.html'

CONTRACT = {
    'scenario': ['barista', 'street', 'park'],
    'receptivity': ['interested', 'neutral', 'uninterested'],
}


def js_list(html, const):
    m = re.search(rf"const {const} = \[([^\]]*)\];", html)
    assert m, f'{const} not found'
    return re.findall(r"'([a-z]+)'", m.group(1))


def main():
    html = PAGE.read_text()

    for name, values in CONTRACT.items():
        radios = re.findall(rf'<input type="radio" name="{name}" value="([a-z]+)">', html)
        assert radios == values, f'{name} radios {radios} != {values}'
    assert js_list(html, 'SCENARIOS') == CONTRACT['scenario']
    assert js_list(html, 'RECEPTIVITIES') == CONTRACT['receptivity']
    assert '<button id="start" type="submit" disabled>Start Practice</button>' in html

    hook = re.search(r'async function startPractice\(selection\) \{(.*?)\n\}', html, re.S)
    assert hook and 'connected: false' in hook.group(1) and 'TODO(P06/P07)' in html
    assert 'connected: true' not in html
    assert 'localStorage' not in html and 'sessionStorage' not in html
    print('selector enums, disabled start and honest not-connected hook: PASS')

    node = shutil.which('node')
    if not node:
        print('node not found; skipped validateSelection runtime check')
        return
    core = re.search(r'// BEGIN selection-core.*?\n(.*?)// END selection-core', html, re.S).group(1)
    cases = [
        ({'scenario': s, 'receptivity': r}, True) for s in CONTRACT['scenario'] for r in CONTRACT['receptivity']
    ] + [
        ({}, False), (None, False), ({'scenario': 'park'}, False),
        ({'scenario': 'cafe', 'receptivity': 'neutral'}, False),
        ({'scenario': 'Park', 'receptivity': 'neutral'}, False),
        ({'scenario': 'park', 'receptivity': 'hostile'}, False),
        ({'scenario': 'park', 'receptivity': 'neutral', 'extra': 'x'}, True),
    ]
    script = core + f"""
const cases = {json.dumps(cases)};
const out = cases.map(([inp]) => validateSelection(inp));
console.log(JSON.stringify(out));
"""
    res = subprocess.run([node, '-e', script], capture_output=True, text=True, check=True)
    out = json.loads(res.stdout)
    for (inp, expected), got in zip(cases, out):
        assert got['ok'] is expected, (inp, got)
        if expected:
            # Output carries exactly the contract keys, extras dropped.
            assert got['selection'] == {'scenario': inp['scenario'], 'receptivity': inp['receptivity']}, got
    print(f'validateSelection: {len(cases)} cases PASS')


if __name__ == '__main__':
    main()
