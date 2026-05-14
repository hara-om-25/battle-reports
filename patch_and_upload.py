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
