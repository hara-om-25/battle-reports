#!/usr/bin/env python3
import base64
import json
import urllib.request
import urllib.error
import sys
import os

SOURCE_FILE = "/root/.claude/uploads/e4217b0b-9104-47c4-ad48-67688dcf82d0/80464875-battlev78.html"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_OWNER = "hara-om-25"
REPO_NAME = "battle-reports"
TARGET_PATH = "index.html"
BRANCH = "gh-pages"
API_BASE = "https://api.github.com"


def github_request(method, path, data=None):
    url = f"{API_BASE}{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "battle-uploader/1.0",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get_current_sha():
    status, body = github_request(
        "GET",
        f"/repos/{REPO_OWNER}/{REPO_NAME}/contents/{TARGET_PATH}?ref={BRANCH}"
    )
    if status == 200:
        return body.get("sha")
    if status == 404:
        return None
    print(f"[ERROR] Cannot get file SHA: HTTP {status}: {body.get('message', body)}")
    sys.exit(1)


def apply_patches(html):
    patches = []

    # ── 1. Google Fonts: replace Stardos Stencil + JetBrains Mono with Tektur ──
    patches.append((
        '    <link href="https://fonts.googleapis.com/css2?family=Stardos+Stencil:wght@400;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">',
        '    <link href="https://fonts.googleapis.com/css2?family=Tektur:wght@400;500;700;900&display=swap" rel="stylesheet">',
        'font-link'
    ))

    # ── 2. Replace all CSS font-family: 'Stardos Stencil' with 'Tektur' ──
    # (done as a global replace below after patches loop)

    # ── 3. MGRS label ──
    patches.append((
        '<label class="label block mb-2">КООРДИНАТИ MGRS</label>',
        '<label class="label block mb-2">MGRS</label>',
        'mgrs-label'
    ))

    # ── 4. generateReport() — new ОС-aware version ──
    old_gen = (
        'function generateReport(dayRecs) {\n'
        '    let lines = [];\n'
        "    lines.push('Доповідаю!');\n"
        '    const date = getDateOnly(dayRecs[0].datetime);\n'
        "    const reportTitle = state.reportTitle || 'ТГ невідомий';\n"
        "    lines.push(date+'р. '+reportTitle+' здійснено '+dayRecs.length+' бойових вильотів.');\n"
        "    lines.push('');\n"
        '    \n'
        '    const grouped = {};\n'
        '    dayRecs.forEach(r => {\n'
        "        const abbr = r.target.split(' ').slice(0, -1).join(' ');\n"
        '        const result = r.result;\n'
        "        if (result === 'знищено' || result === 'пошкоджено') {\n"
        "            const key = abbr + ' ' + result;\n"
        '            grouped[key] = (grouped[key] || 0) + 1;\n'
        '        }\n'
        '    });\n'
        '    \n'
        '    let i = 1;\n'
        "    Object.entries(grouped).sort((a,b)=>b[1]-a[1]).forEach(([k,v]) => {\n"
        "        lines.push(i+'. '+k+' - '+v+' шт.');\n"
        '        i++;\n'
        '    });\n'
        '    \n'
        "    lines.push('');\n"
        "    lines.push('🫡🤝🇺🇦');\n"
        '    return lines;\n'
        '}'
    )
    new_gen = (
        'function generateReport(dayRecs) {\n'
        '    let lines = [];\n'
        "    lines.push('Доповідаю!');\n"
        '    const date = getDateOnly(dayRecs[0].datetime);\n'
        "    const reportTitle = state.reportTitle || 'ТГ невідомий';\n"
        '    const totalPoints = Math.round(dayRecs.reduce((s, r) => s + (parseFloat(r.points) || 0), 0));\n'
        "    lines.push(date+'р. '+reportTitle+' здійснено '+dayRecs.length+' бойових вильотів.');\n"
        "    lines.push('Вражено, орієнтовно на '+totalPoints+' балів, а саме:');\n"
        "    lines.push('');\n"
        "    const hasOs = dayRecs.some(r => r.target.split(', ').some(t => t.trim().toLowerCase().startsWith('ос')));\n"
        '    const osSum200 = dayRecs.reduce((s, r) => s + (parseInt(r.qty200) || 0), 0);\n'
        '    const osSum300 = dayRecs.reduce((s, r) => s + (parseInt(r.qty300) || 0), 0);\n'
        '    const otherGrouped = {};\n'
        '    dayRecs.forEach(r => {\n'
        "        const targets = r.target.split(', ');\n"
        "        const results = r.result.split(', ');\n"
        '        targets.forEach((tgt, idx) => {\n'
        '            const tgtTrim = tgt.trim();\n'
        "            const res = (results[idx] || '').trim();\n"
        "            if (!tgtTrim.toLowerCase().startsWith('ос') && (res === 'знищено' || res === 'пошкоджено')) {\n"
        "                const abbr = tgtTrim.split(' ')[0].toUpperCase();\n"
        "                const key = abbr + ' ' + res;\n"
        '                otherGrouped[key] = (otherGrouped[key] || 0) + 1;\n'
        '            }\n'
        '        });\n'
        '    });\n'
        '    const resultLines = [];\n'
        "    if (hasOs && osSum200 > 0) resultLines.push('ОС знищено - ' + osSum200 + ' шт.');\n"
        "    if (hasOs && osSum300 > 0) resultLines.push('ОС пошкоджено - ' + osSum300 + ' шт.');\n"
        "    Object.entries(otherGrouped).forEach(([k, v]) => resultLines.push(k + ' - ' + v + ' шт.'));\n"
        "    resultLines.forEach((l, i) => lines.push((i + 1) + '. ' + l));\n"
        "    lines.push('');\n"
        "    lines.push('🫡🤝🇺🇦');\n"
        '    return lines;\n'
        '}'
    )
    patches.append((old_gen, new_gen, 'generateReport'))

    # ── 5. add() — base calculated once, not per target ──
    old_add = (
        '    let totalPoints = 0;\n'
        "    let targetStr = '';\n"
        "    let resultStr = '';\n"
        '    for(let i=0; i<state.form.targets.length; i++) {\n'
        '        const t = state.form.targets[i];\n'
        '        const pts = calculatePoints(t.abbr, state.form.q200, state.form.q300, t.result);\n'
        '        totalPoints += pts;\n'
        "        targetStr += (i>0?', ':'') + t.fullName;\n"
        "        resultStr += (i>0?', ':'') + t.result;\n"
        '    }'
    )
    new_add = (
        "    const _os = state.scoreTable['ОС'] || {znyshcheno:0, poshkodzheno:0};\n"
        '    const _base = (parseInt(state.form.q200)||0) * _os.znyshcheno + (parseInt(state.form.q300)||0) * _os.poshkodzheno;\n'
        '    let totalPoints = _base;\n'
        "    let targetStr = '';\n"
        "    let resultStr = '';\n"
        '    for(let i=0; i<state.form.targets.length; i++) {\n'
        '        const t = state.form.targets[i];\n'
        '        const pts = calculatePoints(t.abbr, 0, 0, t.result);\n'
        '        totalPoints += pts;\n'
        "        targetStr += (i>0?', ':'') + t.fullName;\n"
        "        resultStr += (i>0?', ':'') + t.result;\n"
        '    }'
    )
    patches.append((old_add, new_add, 'add-base-fix'))

    # ── 6. render() totalPoints — base calculated once ──
    old_render_pts = (
        '        let totalPoints = 0;\n'
        '        const targetPoints = state.form.targets.map(t => {\n'
        '            const pts = calculatePoints(t.abbr, state.form.q200, state.form.q300, t.result);\n'
        '            totalPoints += pts;\n'
        '            return pts;\n'
        '        });'
    )
    new_render_pts = (
        "        const _os2 = state.scoreTable['ОС'] || {znyshcheno:0, poshkodzheno:0};\n"
        '        const _base2 = (parseInt(state.form.q200)||0) * _os2.znyshcheno + (parseInt(state.form.q300)||0) * _os2.poshkodzheno;\n'
        '        let totalPoints = _base2;\n'
        '        const targetPoints = state.form.targets.map(t => {\n'
        '            const pts = calculatePoints(t.abbr, 0, 0, t.result);\n'
        '            totalPoints += pts;\n'
        '            return pts;\n'
        '        });'
    )
    patches.append((old_render_pts, new_render_pts, 'render-totalPoints-fix'))

    # ── 7. Add todayPoints + reportTotalPoints after todayCount line ──
    old_today = (
        '    const todayCount = state.records.filter(r=>r.reportNum===state.report && getDateOnly(r.datetime)===todayDate).length;\n'
    )
    new_today = (
        '    const todayCount = state.records.filter(r=>r.reportNum===state.report && getDateOnly(r.datetime)===todayDate).length;\n'
        '    const todayPoints = Math.round(state.records.filter(r=>r.reportNum===state.report && getDateOnly(r.datetime)===todayDate).reduce((s,r)=>s+(parseFloat(r.points)||0),0));\n'
        '    const reportTotalPoints = Math.round(state.records.filter(r=>r.reportNum===state.report).reduce((s,r)=>s+(parseFloat(r.points)||0),0));\n'
    )
    patches.append((old_today, new_today, 'todayPoints'))

    # ── 8. ЗВІТ № header — add БАЛІВ ЗА ЗВІТ next to report number ──
    old_header = (
        '                <h2 class="stencil-shadow text-3xl" style="color: var(--yellow)">ЗВІТ №${state.report}</h2>\n'
    )
    new_header = (
        '                <div class="flex items-center" style="gap:4em">\n'
        '                    <h2 class="stencil-shadow text-3xl" style="color: var(--yellow)">ЗВІТ №${state.report}</h2>\n'
        '                    <span class="stencil" style="font-size:1.265em"><span style="color:var(--khaki)">БАЛІВ ЗА ЗВІТ:</span> <span style="color:var(--yellow)">${reportTotalPoints}</span></span>\n'
        '                </div>\n'
    )
    patches.append((old_header, new_header, 'zvit-header'))

    # ── 9. Stats block — 3 vertical lines → 1 horizontal row, space-between ──
    old_stats = (
        '            <div class="mb-6 space-y-1 stencil" style="font-size: 1.15em">\n'
        '                <p><span style="color: var(--khaki)">СЬОГОДНІ:</span> <span style="color: var(--text)">${todayDate}</span></p>\n'
        '                <p><span style="color: var(--khaki)">ЗАПИСІВ:</span> <span style="color: var(--text)">${todayCount}</span></p>\n'
        '                <p><span style="color: var(--khaki)">БАЛІВ:</span> <span style="color: var(--yellow)" class="text-2xl">${totalPoints}</span></p>\n'
        '            </div>'
    )
    new_stats = (
        '            <div class="mb-4 stencil" style="font-size:1.15em; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap">\n'
        '                <span><span style="color:var(--khaki)">СЬОГОДНІ:</span> <span style="color:var(--text)">${todayDate}</span></span>\n'
        '                <span><span style="color:var(--khaki)">ВИЛЬОТІВ:</span> <span style="color:var(--text)">${todayCount}</span></span>\n'
        '                <span><span style="color:var(--khaki)">БАЛІВ ЗА СЬОГОДНІ:</span> <span style="color:var(--text)">${todayPoints}</span></span>\n'
        '            </div>'
    )
    patches.append((old_stats, new_stats, 'stats-block'))

    # ── 10. ЦІЛІ section — h3 → inline row with БАЛІВ + dashed border-top ──
    old_targets = (
        '            <div class="mb-6">\n'
        '                <h3 class="stencil" style="color: var(--khaki); margin-bottom: 8px">ЦІЛІ (${state.form.targets.length})</h3>\n'
        '                <div class="space-y-2" style="max-height: 150px; overflow-y: auto">'
    )
    new_targets = (
        '            <div class="mb-6" style="border-top: 1px dashed var(--khaki); padding-top: 16px; margin-top: 16px">\n'
        '                <div class="stencil" style="display:flex; align-items:center; gap:2em; margin-bottom:8px; color:var(--khaki)">\n'
        '                    <span>ЦІЛІ (<span style="color:#ffffff">${state.form.targets.length}</span>)</span>\n'
        '                    <span>БАЛІВ (<span style="color:#ffffff">${totalPoints}</span>)</span>\n'
        '                </div>\n'
        '                <div class="space-y-2" style="max-height: 150px; overflow-y: auto">'
    )
    patches.append((old_targets, new_targets, 'targets-section'))

    # ── 11. ДОДАТИ ЗАПИС button — remove ✓, add active color on press ──
    old_btn = (
        '<button onclick="add()" class="btn-stencil btn-yellow-dim w-full text-lg mt-4">✓ ДОДАТИ ЗАПИС</button>'
    )
    new_btn = (
        '<button onclick="add()" onmousedown="this.classList.add(\'active\')" onmouseup="this.classList.remove(\'active\')" ontouchstart="this.classList.add(\'active\')" ontouchend="this.classList.remove(\'active\')" class="btn-stencil btn-yellow-dim w-full text-lg mt-4">ДОДАТИ ЗАПИС</button>'
    )
    patches.append((old_btn, new_btn, 'add-btn'))

    # ── 12. Swap ammo/results columns on load (B=results, C=ammo) ──
    patches.append((
        '            if (row[1]) state.ammo.push(row[1]);\n'
        '            if (row[2]) state.results.push(row[2]);',
        '            if (row[1]) state.results.push(row[1]);\n'
        '            if (row[2]) state.ammo.push(row[2]);',
        'lists-load-swap'
    ))

    # ── 13. Swap ammo/results columns on save (B=results, C=ammo) ──
    patches.append((
        "            rows.push([state.drones[i] || '', state.ammo[i] || '', state.results[i] || '']);",
        "            rows.push([state.drones[i] || '', state.results[i] || '', state.ammo[i] || '']);",
        'lists-save-swap'
    ))

    # Apply patches
    for old, new, name in patches:
        if old not in html:
            print(f"[WARN] Patch '{name}' not found in source — skipping")
        else:
            html = html.replace(old, new, 1)
            print(f"[OK]   Patch '{name}' applied")

    # Global font replace (after all patches)
    count = html.count("'Stardos Stencil'")
    html = html.replace("'Stardos Stencil'", "'Tektur'")
    print(f"[OK]   Font: replaced {count} occurrence(s) of 'Stardos Stencil' with 'Tektur'")

    # Remove CONFIDENTIAL image line (too large for normal patch — filter by alt text)
    lines = html.split('\n')
    before = len(lines)
    lines = [l for l in lines if 'alt="CONFIDENTIAL"' not in l]
    removed = before - len(lines)
    html = '\n'.join(lines)
    print(f"[OK]   Removed {removed} CONFIDENTIAL image line(s)")

    # Shrink header grid from 3 to 2 columns after removing image
    html = html.replace(
        '<div class="grid gap-4 items-center mb-4" style="grid-template-columns: auto 1fr auto">',
        '<div class="grid gap-4 items-center mb-4" style="grid-template-columns: 1fr auto">',
        1
    )
    print("[OK]   Header grid: auto 1fr auto → 1fr auto")

    return html


def main():
    if not GITHUB_TOKEN:
        print("[ERROR] Set GITHUB_TOKEN environment variable")
        print("        export GITHUB_TOKEN=ghp_...")
        sys.exit(1)

    if not os.path.isfile(SOURCE_FILE):
        print(f"[ERROR] Source file not found: {SOURCE_FILE}")
        sys.exit(1)

    print(f"[INFO]  Reading source: {SOURCE_FILE}")
    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        html = f.read()
    print(f"[INFO]  Source size: {len(html):,} chars")

    print("[INFO]  Applying patches...")
    html = apply_patches(html)
    print(f"[INFO]  Patched size: {len(html):,} chars")

    raw = html.encode("utf-8")
    encoded = base64.b64encode(raw).decode()

    sha = get_current_sha()
    if sha:
        print(f"[INFO]  Current SHA of {TARGET_PATH}: {sha}")
    else:
        print(f"[INFO]  {TARGET_PATH} not found — will create new")

    print(f"[INFO]  Uploading to {REPO_OWNER}/{REPO_NAME} (branch: {BRANCH})...")
    payload = {
        "message": "Upload patched battle-v78.html as index.html",
        "content": encoded,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    status, body = github_request(
        "PUT",
        f"/repos/{REPO_OWNER}/{REPO_NAME}/contents/{TARGET_PATH}",
        payload
    )

    if status in (200, 201):
        action = "updated" if status == 200 else "created"
        file_url = body.get("content", {}).get("html_url", "")
        print(f"\n[OK]    File {action}!")
        print(f"[OK]    URL: {file_url}")
        print(f"[OK]    Commit SHA: {body.get('commit', {}).get('sha', 'n/a')}")
    else:
        print(f"\n[ERROR] GitHub API returned HTTP {status}")
        print(f"        {body.get('message', json.dumps(body))}")
        sys.exit(1)


if __name__ == "__main__":
    main()
