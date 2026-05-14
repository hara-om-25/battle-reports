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

    # ── 14. Trident logo before БОЙОВІ ЗВІТИ ──
    trident_b64 = "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"
    patches.append((
        '                <h1 class="stencil-shadow text-xl" style="color: var(--yellow)">БОЙОВІ ЗВІТИ</h1>',
        f'                <img src="data:image/png;base64,{trident_b64}" style="height:32px;width:auto" alt=""/>\n                <h1 class="stencil-shadow text-xl" style="color: var(--yellow)">БОЙОВІ ЗВІТИ</h1>',
        'trident-logo'
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
