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
        "    lines.push('Уражено орієнтовно на '+totalPoints+' балів');\n"
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
        "                const _tP=tgtTrim.split(' '),_tL=_tP[_tP.length-1];\n"
        "                const abbrDisp=/^\\d+$/.test(_tL)?_tP.slice(0,-1).join(' '):tgtTrim;\n"
        "                const key=abbrDisp.toUpperCase()+' '+res;\n"
        "                if(!otherGrouped[key])otherGrouped[key]={d:abbrDisp,r:res,n:0};\n"
        "                otherGrouped[key].n++;\n"
        '            }\n'
        '        });\n'
        '    });\n'
        '    const resultLines = [];\n'
        "    if (hasOs && osSum200 > 0) resultLines.push('ОС знищено - ' + osSum200 + ' шт.');\n"
        "    if (hasOs && osSum300 > 0) resultLines.push('ОС пошкоджено - ' + osSum300 + ' шт.');\n"
        "    Object.entries(otherGrouped).forEach(([k, v]) => resultLines.push(v.d + ' ' + v.r + ' - ' + v.n + ' шт.'));\n"
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
        '                <h2 class="stencil-shadow text-3xl" style="color: var(--yellow)">ЗВІТ №${state.report}</h2>\n'
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
        '            <div class="mb-4 stencil" style="font-size:calc(1.15em - 1px); display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap">\n'
        '                <span style="color:var(--khaki)">ЗА ЗВІТНІЙ ПЕРІОД ЗДІЙСНЕНО <span style="color:var(--yellow)">${state.records.filter(r=>r.reportNum===state.report).length}</span> ВИЛЬОТІВ, ОРІЄНТОВНО НА <span style="color:var(--yellow)">${Math.round(state.records.filter(r=>r.reportNum===state.report).reduce((s,r)=>s+r.points,0))}</span> БАЛІВ</span>\n'
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
        '                <div class="stencil" style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; color:var(--khaki)">\n'
        '                    <div style="display:flex;gap:2em">\n'
        '                        <span>ЦІЛІ (<span style="color:#ffffff">${state.form.targets.length}</span>)</span>\n'
        '                        <span>БАЛІВ (<span style="color:#ffffff">${totalPoints}</span>)</span>\n'
        '                    </div>\n'
        '                    <span>СЬОГОДНІ: <span style="color:#ffffff">${todayDate}</span></span>\n'
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

    # ── 14. nav-btn: add box-shadow + transition + active press ──
    patches.append((
        '    .nav-btn {\n'
        "      font-family: 'Stardos Stencil', serif;\n"
        '      letter-spacing: 0.1em;\n'
        '      padding: 8px 14px;\n'
        '      background: var(--surface);\n'
        '      border: 1px solid var(--olive);\n'
        '      color: var(--text-dim);\n'
        '      border-radius: 2px;\n'
        '      cursor: pointer;\n'
        '    }',
        '    .nav-btn {\n'
        "      font-family: 'Stardos Stencil', serif;\n"
        '      letter-spacing: 0.1em;\n'
        '      padding: 0 14px;\n'
        '      height: 40px;\n'
        '      box-sizing: border-box;\n'
        '      display: inline-flex;\n'
        '      align-items: center;\n'
        '      justify-content: center;\n'
        '      background: var(--surface);\n'
        '      border: 1px solid var(--olive);\n'
        '      color: var(--text-dim);\n'
        '      border-radius: 2px;\n'
        '      cursor: pointer;\n'
        '      box-shadow: 0 4px 0 #2d3818, 0 6px 12px rgba(0,0,0,0.4);\n'
        '      transition: all 0.1s;\n'
        '    }\n'
        '    .nav-btn:active, .nav-btn.pressing {\n'
        '      transform: translateY(2px);\n'
        '      box-shadow: 0 2px 0 #2d3818, 0 4px 8px rgba(0,0,0,0.4);\n'
        '      background: var(--olive-dark);\n'
        '      color: var(--text);\n'
        '    }',
        'nav-btn-shadow'
    ))

    # ── 15. Target list: "б." → "балів" ──
    patches.append((
        '(${targetPoints[i]} б.)',
        '(${targetPoints[i]} балів)',
        'target-points-label'
    ))

    # ── 16. btn-stencil: extend :active selector to include .active class ──
    patches.append((
        '    .btn-stencil:active {\n'
        '      transform: translateY(2px);\n'
        '      box-shadow: 0 2px 0 #2d3818, 0 4px 8px rgba(0,0,0,0.4);\n'
        '    }',
        '    .btn-stencil:active, .btn-stencil.active {\n'
        '      transform: translateY(2px);\n'
        '      box-shadow: 0 2px 0 #2d3818, 0 4px 8px rgba(0,0,0,0.4);\n'
        '    }',
        'btn-stencil-active'
    ))

    # ── 17. Видаляємо кнопки XLSX та PDF (залишаємо тільки КОПІЮВАТИ) ──
    patches.append((
        '<button onclick="exportXLSX()" class="btn-stencil btn-green">XLSX</button>\n'
        '                        <button onclick="exportPDF()" class="btn-stencil btn-blue">PDF</button>\n'
        '                        <button onclick="copyReport()" class="btn-stencil btn-black">КОПІЮВАТИ</button>',
        '<button onclick="copyReport()" class="btn-stencil btn-black">КОПІЮВАТИ</button>',
        'remove-xlsx-pdf'
    ))

    # ── 19. КОПІЮВАТИ button — add JS press handlers ──
    patches.append((
        '<button onclick="copyReport()" class="btn-stencil btn-black">КОПІЮВАТИ</button>',
        '<button onclick="copyReport()" onmousedown="this.classList.add(\'active\')" onmouseup="this.classList.remove(\'active\')" ontouchstart="this.classList.add(\'active\')" ontouchend="this.classList.remove(\'active\')" class="btn-stencil btn-black">КОПІЮВАТИ</button>',
        'copy-press'
    ))

    # ── 20. Nav buttons — add JS press handlers (.pressing class, .active is reserved) ──
    patches.append((
        "<button onclick=\"state.page='form';render()\" class=\"nav-btn ${state.page==='form'?'active':''}\">ФОРМА</button>",
        "<button onclick=\"state.page='form';render()\" onmousedown=\"this.classList.add('pressing')\" onmouseup=\"this.classList.remove('pressing')\" ontouchstart=\"this.classList.add('pressing')\" ontouchend=\"this.classList.remove('pressing')\" class=\"nav-btn ${state.page==='form'?'active':''}\">ФОРМА</button>",
        'nav-form-press'
    ))
    patches.append((
        "<button onclick=\"state.page='reports';render()\" class=\"nav-btn ${state.page==='reports'?'active':''}\">ЗВІТИ</button>",
        "<button onclick=\"state.page='reports';render()\" onmousedown=\"this.classList.add('pressing')\" onmouseup=\"this.classList.remove('pressing')\" ontouchstart=\"this.classList.add('pressing')\" ontouchend=\"this.classList.remove('pressing')\" class=\"nav-btn ${state.page==='reports'?'active':''}\">ЗВІТИ</button>",
        'nav-reports-press'
    ))
    patches.append((
        "<button onclick=\"state.page='lists';render()\" class=\"nav-btn ${state.page==='lists'?'active':''}\">СПИСКИ</button>",
        "<button onclick=\"state.page='lists';render()\" onmousedown=\"this.classList.add('pressing')\" onmouseup=\"this.classList.remove('pressing')\" ontouchstart=\"this.classList.add('pressing')\" ontouchend=\"this.classList.remove('pressing')\" class=\"nav-btn ${state.page==='lists'?'active':''}\">СПИСКИ</button>",
        'nav-lists-press'
    ))
    patches.append((
        '<button onclick="logout()" class="nav-btn logout">ВИЙТИ</button>',
        '<button onclick="loadDataFromAPI()" onmousedown="this.classList.add(\'active\')" onmouseup="this.classList.remove(\'active\')" ontouchstart="this.classList.add(\'active\')" ontouchend="this.classList.remove(\'active\')" class="btn-stencil btn-yellow-dim" style="font-size:1.5em;letter-spacing:0;line-height:1;display:inline-flex;align-items:center;justify-content:center;height:40px;min-width:40px;padding:0 8px;box-sizing:border-box" title="Синхронізація">↻</button><button onclick="logout()" onmousedown="this.classList.add(\'pressing\')" onmouseup="this.classList.remove(\'pressing\')" ontouchstart="this.classList.add(\'pressing\')" ontouchend="this.classList.remove(\'pressing\')" class="nav-btn logout">ВИЙТИ</button>',
        'nav-logout-press'
    ))

    # ── 21. Rename "ЗАПИСИ" → "ВИЛЬОТИ" in ЗВІТИ page ──
    patches.append((
        '<h3 class="stencil-shadow mb-3" style="color: var(--yellow)">ЗАПИСИ</h3>\n'
        '                <div class="space-y-2 max-h-96 overflow-y-auto">${dayRecs.length > 0 ? dayRecs.map(r=>formatRecord(r)).join(\'\') : \'<p class="stencil text-center py-2" style="color: var(--text-dim)">Немає записів</p>\'}</div>',
        '<h3 class="stencil-shadow mb-3" style="color: var(--yellow)">ВИЛЬОТИ</h3>\n'
        '                <div class="space-y-2">${dayRecs.length > 0 ? dayRecs.map((r,i)=>formatRecord(r,i+1)).join(\'\') : \'<p class="stencil text-center py-2" style="color: var(--text-dim)">Немає вильотів</p>\'}</div>',
        'rename-zapysy-to-vyloty'
    ))

    # ── 22. formatRecord — цілі+200/300 в першому рядку, тіре жовте ──
    patches.append((
        'function formatRecord(r) {\n    const abbr = r.target.split(\' \').slice(0, -1).join(\' \');\n    const num = r.target.split(\' \').slice(-1)[0];\n    const fullName = state.scoreTable[abbr] ? state.scoreTable[abbr].fullName : abbr;\n    return `<div class="record-card text-sm">\n<p class="stencil" style="color: var(--text)">${esc(abbr)} ${esc(num)}</p>\n<p class="stencil" style="color: var(--text)">${esc(fullName)} — ${esc(r.result)} | 200: ${r.qty200} | 300: ${r.qty300}</p>\n<p class="stencil" style="color: var(--text)">${esc(r.coordinates)} | ${esc(r.drone)} | ${esc(r.ammo)}</p>\n<p class="stencil" style="color: var(--yellow)">${r.points} балів</p>\n</div>`;\n}',
        'function formatRecord(r, num) {\n    const idx = state.records.indexOf(r);\n    const tgts = r.target ? r.target.split(\', \') : [];\n    const ress = r.result ? r.result.split(\', \') : [];\n    const sep = \'<span style="color:var(--yellow)">, </span>\';\n    const dash = \'<span style="color:var(--yellow)"> \\u2014 </span>\';\n    const allParts = [\n        ...Array.from({length:Math.max(tgts.length,ress.length)},(_,i)=>{ const name=esc(tgts[i]||\'\'); const rtxt=esc(ress[i]||\'\'); return name ? name+dash+`<span style="color:var(--khaki)">${rtxt}</span>` : rtxt; }),\n        r.qty200>0 ? `<span style="color:#e05050">200</span>${dash}<span style="color:#fff">${r.qty200}</span>` : \'\',\n        r.qty300>0 ? `<span style="color:#5599dd">300</span>${dash}<span style="color:#fff">${r.qty300}</span>` : \'\'\n    ].filter(Boolean);\n    const tgtLine = allParts.join(sep);\n    const ysep = \'<span style="color:var(--yellow)"> | </span>\';\n    const meta = [esc(r.coordinates),esc(r.drone),esc(r.ammo)].filter(Boolean).join(ysep);\n    return `<div class="record-card text-sm" style="position:relative;padding-left:62px;padding-right:46px;font-size:calc(0.875rem + 1px)">\n<div style="position:absolute;left:4px;top:50%;transform:translateY(-50%);width:54px;height:54px;display:flex;align-items:center;justify-content:center;background:transparent"><span class="stencil" style="color:var(--yellow);font-size:1.6em;line-height:1">${num}</span></div>\n<p class="stencil" style="color:var(--text)">${tgtLine}</p>\n${meta?`<p class="stencil" style="color:var(--text-dim);font-size:0.92em;margin-top:4px">${meta}</p>`:\'\'}\n<p class="stencil" style="color:var(--yellow)">${r.points} балів</p>\n<div style="position:absolute;top:6px;right:6px;display:flex;flex-direction:column;gap:4px">\n  <button onclick="showDeleteRecordModal(${idx})" class="btn-stencil btn-danger" style="padding:3px 7px;font-size:0.85em">&#10005;</button>\n  <button onclick="showEditRecordModal(${idx})" class="btn-stencil" style="padding:3px 7px;font-size:0.85em">&#9998;</button>\n</div></div>`;\n}',
        'formatRecord-with-actions'
    ))

    # ── 23. syncRecordsToAPI + delete/edit вильотів (edit через дропдауни) ──
    patches.append((
        "function closeModal() { document.getElementById('modal').innerHTML = ''; }",
        "function closeModal() { document.getElementById('modal').innerHTML = ''; }\n"
        '\nasync function syncRecordsToAPI() {\n    await apiClear(\'ГОЛОВНА!A2:J\');\n    if (state.records.length > 0) {\n        const rows = state.records.map(r => [\n            r.reportNum, r.datetime, r.target,\n            r.qty200, r.qty300,\n            r.coordinates, r.drone, r.ammo, r.result,\n            r.points\n        ]);\n        await apiUpdate(`ГОЛОВНА!A2:J${state.records.length + 1}`, rows);\n    }\n}\n\nfunction showDeleteRecordModal(idx) {\n    const r = state.records[idx];\n    if (!r) return;\n    state.pendingRecordIdx = idx;\n    const tgts = r.target ? r.target.split(\', \') : [];\n    const ress = r.result ? r.result.split(\', \') : [];\n    const lines = tgts.map((t,i)=>`<p class=\'stencil\' style=\'color:var(--text)\'>${esc(t)} — ${esc(ress[i]||\'\')}</p>`).join(\'\');\n    document.getElementById(\'modal\').innerHTML = `<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal-box"><h2 class="stencil-shadow text-xl mb-4" style="color: var(--yellow)">ВИДАЛЕННЯ ВИЛЬОТУ</h2><div class="mb-4 p-3 rounded" style="background: rgba(0,0,0,0.4); border: 1px dashed var(--khaki)">${lines}<p class="stencil mt-1" style="color:var(--text-dim);font-size:0.85em">${esc(r.datetime)}</p></div><div class="space-y-2"><button onclick="confirmDeleteRecord()" class="btn-stencil btn-danger w-full">ВИДАЛИТИ</button><button onclick="closeModal()" class="btn-stencil w-full">СКАСУВАТИ</button></div></div></div>`;\n}\n\nasync function confirmDeleteRecord() {\n    const idx = state.pendingRecordIdx;\n    if (idx === null || idx === undefined) return;\n    state.records.splice(idx, 1);\n    state.pendingRecordIdx = null;\n    try { await syncRecordsToAPI(); } catch(e) { alert(\'Помилка: \' + e.message); }\n    closeModal(); render();\n}\n\nfunction saveEditModalState() {\n    const er = state.editRecord;\n    if (!er) return;\n    const f = document.getElementById(\'er_coord\');\n    if (f) er.coordinates = f.value;\n}\n\nfunction showEditRecordModal(idx) {\n    const r = state.records[idx];\n    if (!r) return;\n    const tNames = r.target ? r.target.split(\', \') : [];\n    const tResults = r.result ? r.result.split(\', \') : [];\n    state.editRecord = {\n        idx,\n        targets: tNames.map((name, i) => ({name, result: tResults[i] || \'\'})),\n        coordinates: r.coordinates || \'\',\n        qty200: r.qty200 || 0,\n        qty300: r.qty300 || 0,\n        drone: r.drone || \'\',\n        ammo: r.ammo || \'\',\n        newTarget: \'\',\n        newResult: \'\',\n        _orig: JSON.stringify({targets:tNames.map((n,i)=>({name:n,result:tResults[i]||\'\'})),coordinates:r.coordinates||\'\',qty200:r.qty200||0,qty300:r.qty300||0,drone:r.drone||\'\',ammo:r.ammo||\'\'})\n    };\n    renderEditRecordModal();\n}\n\nfunction renderEditRecordModal() {\n    const er = state.editRecord;\n    if (!er) return;\n    const _dirty = !er._orig || JSON.stringify({targets:er.targets,coordinates:er.coordinates,qty200:er.qty200,qty300:er.qty300,drone:er.drone,ammo:er.ammo})!==er._orig;\n    const _dim = _dirty ? \'\'  : \'opacity:0.35;filter:saturate(0.25)\';\n    const tgtList = er.targets.length > 0\n        ? er.targets.map((t,i)=>`<div class="list-item" style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px"><span class="stencil text-sm">${esc(t.name)} — <span style="color:var(--khaki)">${esc(t.result)}</span></span><button onclick="removeEditTarget(${i})" class="btn-stencil btn-danger" style="padding:2px 8px;font-size:12px">&#10005;</button></div>`).join(\'\')\n        : \'<p class="stencil text-sm" style="color:var(--text-dim)">Немає цілей</p>\';\n    const scoreOpts = Object.keys(state.scoreTable).map(x=>`<option value="${esc(x)}" ${er.newTarget===x?\'selected\':\'\'}>${esc(x)}</option>`).join(\'\');\n    const resOpts = state.results.map(r=>`<option value="${esc(r)}" ${er.newResult===r?\'selected\':\'\'}>${esc(r)}</option>`).join(\'\');\n    const droneOpts = state.drones.map(d=>`<option value="${esc(d)}" ${er.drone===d?\'selected\':\'\'}>${esc(d)}</option>`).join(\'\');\n    const ammoOpts = state.ammo.map(a=>`<option value="${esc(a)}" ${er.ammo===a?\'selected\':\'\'}>${esc(a)}</option>`).join(\'\');\n    const q200opts = [0,1,2,3,4,5,6,7,8,9].map(n=>`<option value="${n}" ${er.qty200===n?\'selected\':\'\'}>${n}</option>`).join(\'\');\n    const q300opts = [0,1,2,3,4,5,6,7,8,9].map(n=>`<option value="${n}" ${er.qty300===n?\'selected\':\'\'}>${n}</option>`).join(\'\');\n    document.getElementById(\'modal\').innerHTML = `<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal-box" style="max-height:90vh;overflow-y:auto"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px"><h2 class="stencil-shadow text-xl" style="color: var(--yellow)">РЕДАГУВАННЯ</h2><div style="display:flex;gap:6px"><button id="edit-save-top" onclick="saveEditRecord()" class="btn-stencil btn-green" style="padding:6px 14px;font-size:0.9em;${_dim}">&#10003;</button><button onclick="closeModal()" class="btn-stencil" style="padding:6px 14px;font-size:0.9em;opacity:0.6">&#10005;</button></div></div><div class="space-y-3"><div><label class="label block mb-1">ЦІЛІ</label><div class="space-y-1 mb-2">${tgtList}</div><div class="grid gap-2" style="grid-template-columns:1fr 1fr auto"><select onchange="state.editRecord.newTarget=this.value" class="field"><option value="">Ціль...</option>${scoreOpts}</select><select onchange="state.editRecord.newResult=this.value" class="field"><option value="">Результат...</option>${resOpts}</select><button onclick="addEditTarget()" class="btn-stencil btn-green" style="padding:0;font-size:22px;height:42px;min-width:42px">+</button></div></div><div><label class="label block mb-1">MGRS</label><input id="er_coord" oninput="saveEditModalState();checkEditDirty()" class="field" value="${esc(er.coordinates)}" placeholder="36U UA 24232 91610"/></div><div class="grid grid-cols-2 gap-2"><div><label class="label block mb-1">200</label><select onchange="state.editRecord.qty200=parseInt(this.value);checkEditDirty()" class="field">${q200opts}</select></div><div><label class="label block mb-1">300</label><select onchange="state.editRecord.qty300=parseInt(this.value);checkEditDirty()" class="field">${q300opts}</select></div></div><div><label class="label block mb-1">ДРОН</label><select onchange="state.editRecord.drone=this.value;checkEditDirty()" class="field"><option value="">Виберіть...</option>${droneOpts}</select></div><div><label class="label block mb-1">БОЄПРИПАС</label><select onchange="state.editRecord.ammo=this.value;checkEditDirty()" class="field"><option value="">Виберіть...</option>${ammoOpts}</select></div></div><div class="space-y-2 mt-4"><button id="edit-save-bottom" onclick="saveEditRecord()" class="btn-stencil btn-green w-full" style="${_dim}">ЗБЕРЕГТИ</button></div></div></div>`;\n}\n\nfunction checkEditDirty() {\n    saveEditModalState();\n    const er = state.editRecord;\n    if (!er || !er._orig) return;\n    const dirty = JSON.stringify({targets:er.targets,coordinates:er.coordinates,qty200:er.qty200,qty300:er.qty300,drone:er.drone,ammo:er.ammo})!==er._orig;\n    const btn = document.getElementById(\'edit-save-top\');\n    if (btn) { btn.style.opacity = dirty ? \'\'  : \'0.35\'; btn.style.filter = dirty ? \'\'  : \'saturate(0.25)\'; }\n    const btn2 = document.getElementById(\'edit-save-bottom\'); if (btn2) { btn2.style.opacity = dirty ? \'\'  : \'0.35\'; btn2.style.filter = dirty ? \'\'  : \'saturate(0.25)\'; }\n}\n\nfunction addEditTarget() {\n    const er = state.editRecord;\n    if (!er || !er.newResult) return;\n    saveEditModalState();\n    const fullName = er.newTarget ? ((state.scoreTable[er.newTarget] && state.scoreTable[er.newTarget].fullName) || er.newTarget) : \'\';\n    er.targets.push({name: fullName, result: er.newResult});\n    er.newTarget = \'\'; er.newResult = \'\';\n    renderEditRecordModal();\n}\n\nfunction removeEditTarget(i) {\n    if (!state.editRecord) return;\n    saveEditModalState();\n    state.editRecord.targets.splice(i, 1);\n    renderEditRecordModal();\n}\n\nasync function saveEditRecord() {\n    const er = state.editRecord;\n    if (!er) return;\n    saveEditModalState();\n    const r = state.records[er.idx];\n    r.target = er.targets.map(t => t.name).join(\', \');\n    r.result = er.targets.map(t => t.result).join(\', \');\n    r.coordinates = er.coordinates;\n    r.qty200 = er.qty200;\n    r.qty300 = er.qty300;\n    r.drone = er.drone;\n    r.ammo = er.ammo;\n    state.editRecord = null;\n    try { await syncRecordsToAPI(); } catch(e) { alert(\'Помилка: \' + e.message); }\n    closeModal(); render();\n}',
        'record-delete-edit-fns'
    ))

    # ── 14. Shield logo before БОЙОВІ ЗВІТИ ──
    shield_b64 = "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"
    patches.append((
        '                <h1 class="stencil-shadow text-xl" style="color: var(--yellow)">БОЙОВІ ЗВІТИ</h1>',
        f'                <img onclick="syncOnShieldClick()" src="data:image/png;base64,{shield_b64}" style="height:52px;width:auto;filter:drop-shadow(0 4px 6px rgba(0,0,0,0.6));cursor:pointer;opacity:${{state.shieldHide?0:1}};transition:opacity 0.3s" alt=""/>\n                <h1 class="stencil-shadow text-xl" style="color: var(--yellow)">БОЙОВІ ЗВІТИ</h1>',
        'shield-logo'
    ))

    # ── 26. addTargetToForm — ціль необов'язкова ──
    patches.append((
        "    if(!state.form.newTarget || !state.form.newResult) {\n"
        "        alert('Виберіть ціль і результат!');\n"
        "        return;\n"
        "    }\n"
        "    const abbr = state.form.newTarget;\n"
        "    if(!state.counts[abbr]) state.counts[abbr]=0;\n"
        "    state.counts[abbr]++;\n"
        "    const fullName = abbr + ' ' + state.counts[abbr];\n"
        "    state.form.targets.push({abbr, fullName, result: state.form.newResult});",

        "    if(!state.form.newResult) {\n"
        "        alert('Виберіть результат!');\n"
        "        return;\n"
        "    }\n"
        "    const abbr = state.form.newTarget;\n"
        "    let fullName = '';\n"
        "    if(abbr) {\n"
        "        if(!state.counts[abbr]) state.counts[abbr]=0;\n"
        "        state.counts[abbr]++;\n"
        "        fullName = abbr + ' ' + state.counts[abbr];\n"
        "    }\n"
        "    state.form.targets.push({abbr, fullName, result: state.form.newResult});",

        'addTargetToForm-optional-target'
    ))

    # ── 27. add() — вильот без цілей дозволений ──
    patches.append((
        "    if(state.form.targets.length === 0 || !state.form.drone || !state.form.ammo) {\n"
        "        alert('Додайте хоча б одну ціль, виберіть дрон та боєприпас!');\n"
        "        return;\n"
        "    }",

        "    if(state.form.targets.length === 0) {\n"
        "        alert('Додайте результат вильоту, навіть якщо ціль не було уражено');\n"
        "        return;\n"
        "    }\n"
        "    if(!state.form.drone || !state.form.ammo) {\n"
        "        alert('Виберіть дрон та боєприпас!');\n"
        "        return;\n"
        "    }",

        'add-target-optional'
    ))

    # ── 28. report-box font +1px ──
    patches.append((
        '      font-size: 0.9em;\n    }\n    .modal-overlay {',
        '      font-size: calc(0.9em + 1px);\n    }\n    .modal-overlay {',
        'report-box-font'
    ))

    # ── 30. ЗВІТИ page: max-width 80% ──
    patches.append((
        'h += `<div class="p-4 space-y-4">\n'
        '            <h1 class="stencil-shadow text-3xl px-2" style="color: var(--yellow)">ЗВІТИ</h1>',
        'h += `<div class="p-4 space-y-4 zvity-wrap">\n'
        '            <h1 class="stencil-shadow text-3xl px-2" style="color: var(--yellow)">ЗВІТИ</h1>',
        'zvity-max-width'
    ))


    # ── 31. Lists page modals: click-outside-to-close ──
    patches.append((
        'modal.innerHTML = `<div class="modal-overlay"><div class="modal-box"><h2 class="stencil-shadow text-xl mb-4" style="color: var(--yellow)">В ЯКИЙ СПИСОК ДОДАТИ?',
        'modal.innerHTML = `<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal-box"><h2 class="stencil-shadow text-xl mb-4" style="color: var(--yellow)">В ЯКИЙ СПИСОК ДОДАТИ?',
        'lists-modal-add-click-outside'
    ))
    patches.append((
        'modal.innerHTML = `<div class="modal-overlay"><div class="modal-box"><h2 class="stencil-shadow text-xl mb-4" style="color: var(--yellow)">РЕДАГУВАННЯ</h2>',
        'modal.innerHTML = `<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal-box"><h2 class="stencil-shadow text-xl mb-4" style="color: var(--yellow)">РЕДАГУВАННЯ</h2>',
        'lists-modal-edit-click-outside'
    ))
    patches.append((
        'modal.innerHTML = `<div class="modal-overlay"><div class="modal-box"><h2 class="stencil-shadow text-xl mb-4" style="color: var(--yellow)">ВИДАЛЕННЯ</h2>',
        'modal.innerHTML = `<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal-box"><h2 class="stencil-shadow text-xl mb-4" style="color: var(--yellow)">ВИДАЛЕННЯ</h2>',
        'lists-modal-delete-click-outside'
    ))

    # ── 32. Header: tab before user email ──
    patches.append((
        '<span style="color: var(--khaki); font-size: 1.15em">${esc(state.user)}</span>',
        '<span style="color: var(--khaki); font-size: 1.15em;margin-left:0.5em">${esc(state.user)}</span>',
        'header-user-tab'
    ))

    # ── 33. btn-danger active state ──
    patches.append((
        '    .btn-danger {\n'
        '      background: var(--danger);\n'
        '      border-color: var(--danger-bright);\n'
        '      box-shadow: 0 4px 0 #3d1810, 0 6px 12px rgba(0,0,0,0.4);\n'
        '    }',
        '    .btn-danger {\n'
        '      background: var(--danger);\n'
        '      border-color: var(--danger-bright);\n'
        '      box-shadow: 0 4px 0 #3d1810, 0 6px 12px rgba(0,0,0,0.4);\n'
        '    }\n'
        '    .btn-danger.active {\n'
        '      background: #c43a20;\n'
        '      border-color: #e05535;\n'
        '      box-shadow: 0 2px 0 #3d1810, 0 4px 8px rgba(0,0,0,0.4);\n'
        '    }',
        'btn-danger-active'
    ))

    # ── 34. НОВИЙ ЗВІТ button press effect ──
    patches.append((
        '<button onclick="newReport()" class="btn-stencil btn-danger">🚩 НОВИЙ ЗВІТ</button>',
        '<button onclick="newReport()" onmousedown="this.classList.add(\'active\')" onmouseup="this.classList.remove(\'active\')" ontouchstart="this.classList.add(\'active\')" ontouchend="this.classList.remove(\'active\')" class="btn-stencil btn-danger">🚩 НОВИЙ ЗВІТ</button>',
        'new-report-press'
    ))

    # ── 35. ЗВІТИ panel label ──
    patches.append((
        '<h3 class="stencil-shadow mb-3" style="color: var(--yellow)">ЗВІТИ</h3>',
        '<h3 class="stencil-shadow mb-3" style="color: var(--yellow)">ЗВІТИ В TRINITY</h3>',
        'zvity-panel-label'
    ))

    # ── 36. zvity-wrap responsive class ──
    patches.append((
        '    .modal-overlay {',
        '    .zvity-wrap { max-width: 80%; margin: 0 auto; }\n'
        '    @media (max-width: 640px) { .zvity-wrap { max-width: 100%; } }\n'
        '    .modal-overlay {',
        'zvity-wrap-css'
    ))

    # ── 39. syncOnShieldClick — click shield to sync ──
    patches.append((
        'async function loadDataFromAPI() {',
        'async function syncOnShieldClick() {\n'
        '    state.shieldHide = true;\n'
        '    render();\n'
        '    try {\n'
        '        await loadDataFromAPI();\n'
        '    } finally {\n'
        '        state.shieldHide = false;\n'
        '        render();\n'
        '    }\n'
        '}\n'
        '\nasync function loadDataFromAPI() {',
        'sync-on-shield-click'
    ))

    # ── 40. state.counts init — properly parse multi-target records ──
    patches.append((
        '            state.counts = {};\n'
        '            reportRecs.forEach(r => {\n'
        '                const abbr = r.target.split(\' \').slice(0, -1).join(\' \');\n'
        '                state.counts[abbr] = (state.counts[abbr] || 0) + 1;\n'
        '            });',

        '            state.counts = {};\n'
        '            reportRecs.forEach(r => {\n'
        '                (r.target||\'\').split(\', \').forEach(t => {\n'
        '                    const _p=t.trim().split(\' \'),_l=_p[_p.length-1];\n'
        '                    const _n=/^\\d+$/.test(_l)?parseInt(_l):0;\n'
        '                    const _a=/^\\d+$/.test(_l)?_p.slice(0,-1).join(\' \'):t.trim();\n'
        '                    if(!_a)return;\n'
        '                    const _u=_a.toUpperCase();\n'
        '                    const _k=Object.keys(state.scoreTable).find(k=>k.toUpperCase()===_u)||(()=>{const _lo=_a.toLowerCase();for(const[_ka,_d]of Object.entries(state.scoreTable))if(_d.fullName&&_d.fullName.toLowerCase()===_lo)return _ka;return _a;})();\n'
        '                    if(_k)state.counts[_k]=Math.max(state.counts[_k]||0,_n);\n'
        '                });\n'
        '            });',

        'counts-init-multi-target'
    ))

    # ── 41. removeTargetFromForm — don't decrement (prevent number reuse) ──
    patches.append((
        'function removeTargetFromForm(idx) {\n'
        '    const t = state.form.targets[idx];\n'
        '    if(t && state.counts[t.abbr]) state.counts[t.abbr]--;\n'
        '    state.form.targets.splice(idx, 1);\n'
        '    render();\n'
        '}',

        'function removeTargetFromForm(idx) {\n'
        '    state.form.targets.splice(idx, 1);\n'
        '    render();\n'
        '}',

        'remove-target-no-decrement'
    ))

    # ── 42. addEditTarget — assign next unique number per report ──
    patches.append((
        'function addEditTarget() {\n'
        '    const er = state.editRecord;\n'
        '    if (!er || !er.newResult) return;\n'
        '    saveEditModalState();\n'
        "    const fullName = er.newTarget ? ((state.scoreTable[er.newTarget] && state.scoreTable[er.newTarget].fullName) || er.newTarget) : '';\n"
        '    er.targets.push({name: fullName, result: er.newResult});\n'
        "    er.newTarget = ''; er.newResult = '';\n"
        '    renderEditRecordModal();\n'
        '}',

        'function addEditTarget() {\n'
        '    const er = state.editRecord;\n'
        '    if (!er || !er.newResult) return;\n'
        '    saveEditModalState();\n'
        '    const abbr = er.newTarget;\n'
        "    let name = '';\n"
        '    if (abbr) {\n'
        '        let maxN = 0;\n'
        "        const _gA = s => { const _p=s.split(' '),_l=_p[_p.length-1],_r=/^\\d+$/.test(_l)?_p.slice(0,-1).join(' '):s,_u=_r.toUpperCase(); return (Object.keys(state.scoreTable).find(k=>k.toUpperCase()===_u)||(()=>{const _lo=_r.toLowerCase();for(const[_a,_d]of Object.entries(state.scoreTable))if(_d.fullName&&_d.fullName.toLowerCase()===_lo)return _a;return _r;})()).toUpperCase(); };\n"
        "        const _gN = s => { const _p=s.split(' '),_l=_p[_p.length-1]; return /^\\d+$/.test(_l)?parseInt(_l):0; };\n"
        '        state.records.filter((r,i)=>r.reportNum===state.report&&i!==er.idx).forEach(r=>{\n'
        "            (r.target||'').split(', ').forEach(t=>{ if(_gA(t.trim())===abbr.toUpperCase())maxN=Math.max(maxN,_gN(t.trim())); });\n"
        '        });\n'
        "        er.targets.forEach(t=>{ if(_gA(t.name.trim())===abbr.toUpperCase())maxN=Math.max(maxN,_gN(t.name.trim())); });\n"
        "        name = abbr + ' ' + (maxN + 1);\n"
        '    }\n'
        '    er.targets.push({name, result: er.newResult});\n'
        "    er.newTarget = ''; er.newResult = '';\n"
        '    renderEditRecordModal();\n'
        '}',

        'add-edit-target-numbering'
    ))

    # ── 43. Edit modal: inline dropdowns per target row ──
    _tgtlist_old = (
        'const tgtList = er.targets.length > 0\n'
        '        ? er.targets.map((t,i)=>`<div class="list-item" style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px"><span class="stencil text-sm">${esc(t.name)} \u2014 <span style=\"color:var(--khaki)\">${esc(t.result)}</span></span><button onclick=\"removeEditTarget(${i})\" class=\"btn-stencil btn-danger\" style=\"padding:2px 8px;font-size:12px\">&#10005;</button></div>`).join(\'\')\n'
        "        : '<p class=\"stencil text-sm\" style=\"color:var(--text-dim)\">Немає цілей</p>';"
    )
    _tgtlist_new = (
        'const _getEA = (nm) => { const _p=nm.trim().split(\' \'),_l=_p[_p.length-1],_r=/^\\d+$/.test(_l)?_p.slice(0,-1).join(\' \'):nm.trim(),_u=_r.toUpperCase(); return Object.keys(state.scoreTable).find(k=>k.toUpperCase()===_u)||(()=>{const _lo=_r.toLowerCase();for(const[_a,_d]of Object.entries(state.scoreTable))if(_d.fullName&&_d.fullName.toLowerCase()===_lo)return _a;return _r;})(); };\n'
        'const tgtList = er.targets.length > 0\n'
        '        ? er.targets.map((t,i)=>{ const _ca=_getEA(t.name); const _so=Object.keys(state.scoreTable).map(x=>`<option value=\"${esc(x)}\" ${_ca===x?\'selected\':\'\'}>${esc(x)}</option>`).join(\'\'); const _ro=state.results.map(r=>`<option value=\"${esc(r)}\" ${t.result===r?\'selected\':\'\'}>${esc(r)}</option>`).join(\'\'); return `<div class=\"list-item\" style=\"display:flex;gap:4px;align-items:center;padding:4px 6px\"><select onchange=\"changeEditTargetCil(${i},this.value)\" class=\"field\" style=\"flex:1;min-width:0;font-size:0.82em;padding:3px 6px\"><option value=\"\">Ціль...</option>${_so}</select><select onchange=\"changeEditTargetResult(${i},this.value)\" class=\"field\" style=\"flex:1;min-width:0;font-size:0.82em;padding:3px 6px\"><option value=\"\">Результат...</option>${_ro}</select><button onclick=\"removeEditTarget(${i})\" class=\"btn-stencil btn-danger\" style=\"padding:2px 8px;font-size:12px\">&#10005;</button></div>`; }).join(\'\')\n'
        "        : '<p class=\"stencil text-sm\" style=\"color:var(--text-dim)\">Немає цілей</p>';"
    )
    patches.append((_tgtlist_old, _tgtlist_new, 'edit-target-inline-dropdowns'))

    # ── 44. Add changeEditTargetCil + changeEditTargetResult functions ──
    patches.append((
        'function removeEditTarget(i) {',
        'function changeEditTargetCil(i, newAbbr) {\n'
        '    const er = state.editRecord;\n'
        '    if (!er || !newAbbr) return;\n'
        "    const _gA = s => { const _p=s.trim().split(' '),_l=_p[_p.length-1],_r=/^\\d+$/.test(_l)?_p.slice(0,-1).join(' '):s.trim(),_u=_r.toUpperCase(); return (Object.keys(state.scoreTable).find(k=>k.toUpperCase()===_u)||(()=>{const _lo=_r.toLowerCase();for(const[_a,_d]of Object.entries(state.scoreTable))if(_d.fullName&&_d.fullName.toLowerCase()===_lo)return _a;return _r;})()).toUpperCase(); };\n"
        "    const _gN = s => { const _p=s.trim().split(' '),_l=_p[_p.length-1]; return /^\\d+$/.test(_l)?parseInt(_l):0; };\n"
        '    let maxN = 0;\n'
        "    state.records.filter((r,ri)=>r.reportNum===state.report&&ri!==er.idx).forEach(r=>{\n"
        "        (r.target||'').split(', ').forEach(t=>{if(_gA(t)===newAbbr.toUpperCase())maxN=Math.max(maxN,_gN(t));});\n"
        '    });\n'
        "    er.targets.filter((_,ti)=>ti!==i).forEach(t=>{if(_gA(t.name)===newAbbr.toUpperCase())maxN=Math.max(maxN,_gN(t.name));});\n"
        "    er.targets[i].name = newAbbr + ' ' + (maxN + 1);\n"
        '    checkEditDirty();\n'
        '    renderEditRecordModal();\n'
        '}\n'
        '\n'
        'function changeEditTargetResult(i, newResult) {\n'
        '    const er = state.editRecord;\n'
        '    if (!er || !newResult) return;\n'
        '    er.targets[i].result = newResult;\n'
        '    checkEditDirty();\n'
        '}\n'
        '\n'
        'function removeEditTarget(i) {',
        'change-edit-target-cil-result'
    ))

    # ── 45. saveEditRecord: recalculate points ──
    patches.append((
        "    r.ammo = er.ammo;\n"
        "    state.editRecord = null;\n"
        "    try { await syncRecordsToAPI(); }",

        "    r.ammo = er.ammo;\n"
        "    const _osE=state.scoreTable['\u041e\u0421']||{znyshcheno:0,poshkodzheno:0};\n"
        "    let _ptsE=(parseInt(er.qty200)||0)*_osE.znyshcheno+(parseInt(er.qty300)||0)*_osE.poshkodzheno;\n"
        "    er.targets.forEach(t=>{const _p=t.name.trim().split(' '),_l=_p[_p.length-1],_r=/^\\d+$/.test(_l)?_p.slice(0,-1).join(' '):t.name.trim(),_u=_r.toUpperCase();const _ab=Object.keys(state.scoreTable).find(k=>k.toUpperCase()===_u)||(()=>{const _lo=_r.toLowerCase();for(const[_a,_d]of Object.entries(state.scoreTable))if(_d.fullName&&_d.fullName.toLowerCase()===_lo)return _a;return _r;})();const _sc=state.scoreTable[_ab];if(_sc)_ptsE+=t.result===\'\u0437\u043d\u0438\u0449\u0435\u043d\u043e\'?_sc.znyshcheno:t.result===\'\u043f\u043e\u0448\u043a\u043e\u0434\u0436\u0435\u043d\u043e\'?_sc.poshkodzheno:0;});\n"
        "    r.points=Math.round(_ptsE*100)/100;\n"
        "    state.editRecord = null;\n"
        "    try { await syncRecordsToAPI(); }",

        'save-edit-recalc-points'
    ))

    # ── 46. Trim drone/ammo/results when loading from СПИСКИ ──
    patches.append((
        '        if (row[0]) state.drones.push(row[0]);\n'
        '            if (row[1]) state.results.push(row[1]);\n'
        '            if (row[2]) state.ammo.push(row[2]);',

        '        if (row[0]) state.drones.push(row[0].trim());\n'
        '            if (row[1]) state.results.push(row[1].trim());\n'
        '            if (row[2]) state.ammo.push(row[2].trim());',

        'lists-load-trim'
    ))

    # ── 47. Trim drone/ammo when loading from ГОЛОВНА ──
    patches.append((
        "                    drone: row[6] || '',\n"
        "                    ammo: row[7] || '',",

        "                    drone: (row[6] || '').trim(),\n"
        "                    ammo: (row[7] || '').trim(),",

        'records-load-trim'
    ))

    # ── 48. Edit modal: show stored drone/ammo even if not in list ──
    patches.append((
        "    const droneOpts = state.drones.map(d=>`<option value=\"${esc(d)}\" ${er.drone===d?'selected':''}>${esc(d)}</option>`).join('');\n"
        "    const ammoOpts = state.ammo.map(a=>`<option value=\"${esc(a)}\" ${er.ammo===a?'selected':''}>${esc(a)}</option>`).join('');",

        "    const _droneInList=state.drones.some(d=>d===er.drone);\n"
        "    const droneOpts=(er.drone&&!_droneInList?[`<option value=\"${esc(er.drone)}\" selected>${esc(er.drone)}</option>`]:[]).concat(state.drones.map(d=>`<option value=\"${esc(d)}\" ${er.drone===d?'selected':''}>${esc(d)}</option>`)).join('');\n"
        "    const _ammoInList=state.ammo.some(a=>a===er.ammo);\n"
        "    const ammoOpts=(er.ammo&&!_ammoInList?[`<option value=\"${esc(er.ammo)}\" selected>${esc(er.ammo)}</option>`]:[]).concat(state.ammo.map(a=>`<option value=\"${esc(a)}\" ${er.ammo===a?'selected':''}>${esc(a)}</option>`)).join('');",

        'edit-drone-ammo-fallback'
    ))

    # ── 49. state: add selVylotyDate field ──
    patches.append((
        "    selReport: null, selDate: null,",
        "    selReport: null, selDate: null, selVylotyDate: null,",
        'state-selvyloty'
    ))

    # ── 50. nav: add ВИЛЬОТИ button between ФОРМА and ЗВІТИ ──
    patches.append((
        "class=\"nav-btn ${state.page==='form'?'active':''}\">"
        "ФОРМА</button>\n"
        "                <button onclick=\"state.page='reports';render()\"",

        "class=\"nav-btn ${state.page==='form'?'active':''}\">"
        "ФОРМА</button>\n"
        "                <button onclick=\"state.page='vyloty';render()\""
        " onmousedown=\"this.classList.add('pressing')\""
        " onmouseup=\"this.classList.remove('pressing')\""
        " ontouchstart=\"this.classList.add('pressing')\""
        " ontouchend=\"this.classList.remove('pressing')\""
        " class=\"nav-btn ${state.page==='vyloty'?'active':''}\">ВИЛЬОТИ</button>\n"
        "                <button onclick=\"state.page='reports';render()\"",

        'nav-vyloty-btn'
    ))

    # ── 51. render: page 'vyloty' ──
    patches.append((
        "    if(state.page==='reports') {",

        "    if(state.page==='vyloty') {\n"
        "        const _vyRecs=state.records.filter(r=>r.reportNum===state.report);\n"
        "        const _vyDates=[...new Set(_vyRecs.map(r=>getDateOnly(r.datetime)))].sort();\n"
        "        const _vyTotal=Math.round(_vyRecs.reduce((s,r)=>s+(parseFloat(r.points)||0),0));\n"
        "        let _vyNum=0;\n"
        "        const _vyGroups=_vyDates.map(d=>{\n"
        "            const dayR=_vyRecs.filter(r=>getDateOnly(r.datetime)===d);\n"
        "            const cards=dayR.map(r=>formatRecord(r,++_vyNum)).join('');\n"
        "            const dayPts=Math.round(dayR.reduce((s,r)=>s+(parseFloat(r.points)||0),0));\n"
        "            return `<div class=\"crate p-4\"><div style=\"display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap;gap:6px\"><h3 class=\"stencil-shadow\" style=\"color:var(--yellow)\">${d}</h3><span class=\"stencil\" style=\"color:var(--khaki)\">Вильотів: <span style=\"color:var(--text)\">${dayR.length}</span>&nbsp;|&nbsp;Балів: <span style=\"color:var(--text)\">${dayPts}</span></span></div><div class=\"space-y-2\">${cards}</div></div>`;\n"
        "        }).join('');\n"
        "        h+=`<div class=\"p-4 space-y-4 zvity-wrap\">\n"
        "            <div style=\"display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;padding:0 8px 4px\">\n"
        "                <h1 class=\"stencil-shadow text-3xl\" style=\"color:var(--yellow)\">ВИЛЬОТИ</h1>\n"
        "                ${_vyRecs.length>0?`<div class=\"stencil\" style=\"font-size:calc(1.15em - 1px);margin-top:6px;display:flex;flex-wrap:wrap;gap:2px 20px\"><span style=\"color:var(--khaki);white-space:nowrap\">ВИЛЬОТІВ ЗА ЗВІТ:&nbsp;<span style=\"color:var(--yellow)\">${_vyRecs.length}</span></span><span style=\"color:var(--khaki);white-space:nowrap\">БАЛІВ ЗА ЗВІТ:&nbsp;<span style=\"color:var(--yellow)\">${_vyTotal}</span></span></div>`:''}\n"
        "            </div>\n"
        "            ${_vyGroups||'<div class=\"crate p-4\"><p class=\"stencil text-center py-2\" style=\"color:var(--text-dim)\">Немає вильотів у поточному звіті</p></div>'}\n"
        "        </div>`;\n"
        "    }\n"
        "\n"
        "    if(state.page==='reports') {",

        'vyloty-page-render'
    ))

    # ── 52. Archive CSS classes ──
    patches.append((
        '    .btn-yellow-dim.active {\n'
        '      background: var(--yellow);\n'
        '      border-color: #f4d942;\n'
        '      box-shadow: 0 4px 0 var(--yellow-dim), 0 6px 12px rgba(0,0,0,0.4);\n'
        '    }',

        '    .btn-yellow-dim.active {\n'
        '      background: var(--yellow);\n'
        '      border-color: #f4d942;\n'
        '      box-shadow: 0 4px 0 var(--yellow-dim), 0 6px 12px rgba(0,0,0,0.4);\n'
        '    }\n'
        '    .nav-btn-archive {\n'
        "      font-family: 'Tektur', serif;\n"
        '      letter-spacing: 0.1em;\n'
        '      padding: 0 14px;\n'
        '      height: 40px;\n'
        '      box-sizing: border-box;\n'
        '      display: inline-flex;\n'
        '      align-items: center;\n'
        '      justify-content: center;\n'
        '      background: #3a3a3a;\n'
        '      border: 1px solid #4e4e4e;\n'
        '      color: #b0b0a0;\n'
        '      border-radius: 2px;\n'
        '      cursor: pointer;\n'
        '      box-shadow: 0 4px 0 #2d3818, 0 6px 12px rgba(0,0,0,0.4);\n'
        '      transition: all 0.1s;\n'
        '    }\n'
        '    .nav-btn-archive.pressing {\n'
        '      transform: translateY(2px);\n'
        '      background: #555;\n'
        '      border-color: #666;\n'
        '      color: #d9d6c4;\n'
        '      box-shadow: 0 2px 0 #2d3818, 0 4px 8px rgba(0,0,0,0.4);\n'
        '    }\n'
        '    .nav-btn-archive.active {\n'
        '      background: #555;\n'
        '      border-color: #666;\n'
        '      color: #d9d6c4;\n'
        '    }\n'
        '    .btn-archive {\n'
        '      background: #2a2a2a;\n'
        '      border-color: #444;\n'
        '      color: var(--text-dim);\n'
        '      box-shadow: 0 4px 0 #111, 0 6px 8px rgba(0,0,0,0.4);\n'
        '      text-shadow: none;\n'
        '    }\n'
        '    .btn-archive:active, .btn-archive.pressing {\n'
        '      background: #555;\n'
        '      border-color: #666;\n'
        '      color: var(--text);\n'
        '      transform: translateY(2px);\n'
        '      box-shadow: 0 2px 0 #111, 0 4px 6px rgba(0,0,0,0.4);\n'
        '    }\n'
        '    .btn-archive.active {\n'
        '      background: #555;\n'
        '      border-color: #666;\n'
        '      color: var(--text);\n'
        '    }',

        'archive-css'
    ))

    # ── 53. nav: АРХІВ button before ВИЙТИ ──
    patches.append((
        '<button onclick="logout()" '
        "onmousedown=\"this.classList.add('pressing')\" "
        "onmouseup=\"this.classList.remove('pressing')\" "
        "ontouchstart=\"this.classList.add('pressing')\" "
        "ontouchend=\"this.classList.remove('pressing')\" "
        'class="nav-btn logout">ВИЙТИ</button>',

        '<button onclick="goToArchive()" '
        "onmousedown=\"this.classList.add('pressing')\" "
        "onmouseup=\"this.classList.remove('pressing')\" "
        "ontouchstart=\"this.classList.add('pressing')\" "
        "ontouchend=\"this.classList.remove('pressing')\" "
        "class=\"nav-btn-archive ${state.page==='archive'?'active':''}\">АРХІВ</button>"
        '<button onclick="logout()" '
        "onmousedown=\"this.classList.add('pressing')\" "
        "onmouseup=\"this.classList.remove('pressing')\" "
        "ontouchstart=\"this.classList.add('pressing')\" "
        "ontouchend=\"this.classList.remove('pressing')\" "
        'class="nav-btn logout">ВИЙТИ</button>',

        'nav-archive-btn'
    ))

    # ── 54. state: add archive fields ──
    patches.append((
        'selReport: null, selDate: null, selVylotyDate: null,',
        'selReport: null, selDate: null, selVylotyDate: null,'
        ' archiveSheets: [], selArchive: null, archiveRecs: [], archiveLoading: false, pvr: [],',
        'state-archive'
    ))

    # ── 55. logout: reset archive state ──
    patches.append((
        "state.scoreTable = {}; state.drones = []; state.ammo = []; state.results = [];  state.records = [];\n"
        "    state.loaded = false; state.page = 'login';",

        "state.scoreTable = {}; state.drones = []; state.ammo = []; state.results = [];  state.records = [];\n"
        "    state.archiveSheets = []; state.selArchive = null; state.archiveRecs = []; state.archiveLoading = false; state.pvr = [];\n"
        "    state.loaded = false; state.page = 'login';",

        'logout-archive-reset'
    ))

    # ── 56. archive functions: goToArchive, loadArchiveSheet ──
    patches.append((
        'async function loadDataFromAPI() {',

        'async function goToArchive() {\n'
        '    state.page = \'archive\';\n'
        '    if (!state.archiveSheets.length) {\n'
        '        state.archiveLoading = true;\n'
        '        render();\n'
        '        try {\n'
        '            const _ar = await fetch(\n'
        '                `https://sheets.googleapis.com/v4/spreadsheets/${SHEET_ID}?fields=sheets.properties.title`,\n'
        '                { headers: { \'Authorization\': `Bearer ${state.token}` } }\n'
        '            ).then(r => r.json());\n'
        '            state.archiveSheets = (_ar.sheets||[]).map(s=>s.properties.title).filter(t=>/^\\d/.test(t));\n'
        '            const _pvRows = await apiGet(\'СПИСКИ\');\n'
        '            const _pvHdr = _pvRows[0] || [];\n'
        '            state.pvr = [3,4,5,6].map(ci=>{\n'
        '                const name=(_pvHdr[ci]||\'\'  ).trim();\n'
        '                if(!name) return null;\n'
        '                const map={};\n'
        '                for(let i=1;i<_pvRows.length;i++){\n'
        '                    const row=_pvRows[i]||[];\n'
        '                    const ammo=(row[2]||\'\'  ).trim();\n'
        '                    const val=(row[ci]||\'\'  ).toString().trim().replace(\',\',\'.\');\n'
        '                    if(ammo&&val&&val!==\'0\'){const c=parseFloat(val);if(c)map[ammo]=c;}\n'
        '                }\n'
        '                return Object.keys(map).length?{name,map}:null;\n'
        '            }).filter(Boolean);\n'
        '        } catch(e) {\n'
        '            alert(\'Помилка завантаження архіву: \' + e.message);\n'
        '        } finally {\n'
        '            state.archiveLoading = false;\n'
        '        }\n'
        '    }\n'
        '    render();\n'
        '}\n'
        '\n'
        'async function loadArchiveSheet(name) {\n'
        '    state.selArchive = name;\n'
        '    state.archiveLoading = true;\n'
        '    render();\n'
        '    try {\n'
        '        const rows = await apiGet(name);\n'
        '        state.archiveRecs = [];\n'
        '        for (let i = 1; i < rows.length; i++) {\n'
        '            const row = rows[i] || [];\n'
        '            if (row[0] || row[2]) {\n'
        '                state.archiveRecs.push({\n'
        '                    reportNum: parseInt(row[0])||0,\n'
        '                    datetime: row[1]||\'\'  ,\n'
        '                    target: row[2]||\'\'  ,\n'
        '                    qty200: parseInt(row[3])||0,\n'
        '                    qty300: parseInt(row[4])||0,\n'
        '                    coordinates: row[5]||\'\'  ,\n'
        '                    drone: (row[6]||\'\'  ).trim(),\n'
        '                    ammo: (row[7]||\'\'  ).trim(),\n'
        '                    result: row[8]||\'\'  ,\n'
        '                    points: parseFloat(row[9])||0\n'
        '                });\n'
        '            }\n'
        '        }\n'
        '    } catch(e) {\n'
        '        alert(\'Помилка: \' + e.message);\n'
        '    } finally {\n'
        '        state.archiveLoading = false;\n'
        '        render();\n'
        '    }\n'
        '}\n'
        '\n'
        'async function loadDataFromAPI() {',

        'archive-functions'
    ))

    # ── 57. render: archive page ──
    patches.append((
        "    if(state.page==='vyloty') {",

        "    if(state.page==='archive') {\n"
        "        const _arBtns=state.archiveSheets.map(s=>{const _dl=/^\\d/.test(s)?s:(s.match(/\\d{1,2}[-.\\/]\\d{1,2}[-.\\/]\\d{2,4}/)||[s])[0];const _act=state.selArchive===s?'active':'';return `<button onclick=\"loadArchiveSheet('${esc(s)}')\" onmousedown=\"this.classList.add('pressing')\" onmouseup=\"this.classList.remove('pressing')\" ontouchstart=\"this.classList.add('pressing')\" ontouchend=\"this.classList.remove('pressing')\" class=\"btn-stencil btn-archive ${_act}\">${esc(_dl)}</button>`;}).join('')||'<p class=\"stencil text-center py-2\" style=\"color:var(--text-dim)\">Немає архівних звітів</p>';\n"
        "        let _arContent='';\n"
        "        if(state.selArchive){\n"
        "            if(state.archiveLoading){\n"
        "                _arContent='<div class=\"crate p-4\"><p class=\"stencil text-center py-4\" style=\"color:var(--text-dim)\">Завантаження...</p></div>';\n"
        "            } else {\n"
        "                const _arDates=[...new Set(state.archiveRecs.map(r=>getDateOnly(r.datetime)))].sort();\n"
        "                const _arTotal=Math.round(state.archiveRecs.reduce((s,r)=>s+(parseFloat(r.points)||0),0));\n"
        "                const _sep='<span style=\"color:var(--yellow)\">, </span>';\n"
        "                const _dash='<span style=\"color:var(--yellow)\"> \\u2014 </span>';\n"
        "                const _ysep='<span style=\"color:var(--yellow)\"> | </span>';\n"
        "                let _arNum=0;\n"
        "                const _arGroups=_arDates.map(d=>{\n"
        "                    const dayR=state.archiveRecs.filter(r=>getDateOnly(r.datetime)===d);\n"
        "                    const dayPts=Math.round(dayR.reduce((s,r)=>s+(parseFloat(r.points)||0),0));\n"
        "                    const cards=dayR.map(r=>{\n"
        "                        const n=++_arNum;\n"
        "                        const tgts=r.target?r.target.split(', '):[];\n"
        "                        const ress=r.result?r.result.split(', '):[];\n"
        "                        const parts=[...Array.from({length:Math.max(tgts.length,ress.length)},(_,j)=>{const tn=esc(tgts[j]||'');const rv=esc(ress[j]||'');return tn?tn+_dash+`<span style=\"color:var(--khaki)\">${rv}</span>`:rv;}),r.qty200>0?`<span style=\"color:#e05050\">200</span>${_dash}<span style=\"color:#fff\">${r.qty200}</span>`:'',r.qty300>0?`<span style=\"color:#5599dd\">300</span>${_dash}<span style=\"color:#fff\">${r.qty300}</span>`:''].filter(Boolean);\n"
        "                        const meta=[esc(r.coordinates),esc(r.drone),esc(r.ammo)].filter(Boolean).join(_ysep);\n"
        "                        return `<div class=\"record-card text-sm\" style=\"position:relative;padding-left:62px;font-size:calc(0.875rem + 1px)\"><div style=\"position:absolute;left:4px;top:50%;transform:translateY(-50%);width:54px;height:54px;display:flex;align-items:center;justify-content:center\"><span class=\"stencil\" style=\"color:var(--yellow);font-size:1.6em;line-height:1\">${n}</span></div><p class=\"stencil\" style=\"color:var(--text)\">${parts.join(_sep)}</p>${meta?`<p class=\"stencil\" style=\"color:var(--text-dim);font-size:0.92em;margin-top:4px\">${meta}</p>`:''}<p class=\"stencil\" style=\"color:var(--yellow)\">${r.points} балів</p></div>`;\n"
        "                    }).join('');\n"
        "                    return `<div class=\"crate p-4\"><div style=\"display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap;gap:6px\"><h3 class=\"stencil-shadow\" style=\"color:var(--yellow)\">${d}</h3><span class=\"stencil\" style=\"color:var(--khaki)\">Вильотів: <span style=\"color:var(--text)\">${dayR.length}</span>&nbsp;|&nbsp;Балів: <span style=\"color:var(--text)\">${dayPts}</span></span></div><div class=\"space-y-2\">${cards}</div></div>`;\n"
        "                }).join('');\n"
        "                const _arHeader=state.archiveRecs.length>0?`<div class=\"stencil\" style=\"font-size:calc(1.15em - 1px);margin-top:6px;display:flex;flex-wrap:wrap;gap:2px 20px\"><span style=\"color:var(--khaki);white-space:nowrap\">ВИЛЬОТІВ ЗА ЗВІТ:&nbsp;<span style=\"color:var(--yellow)\">${state.archiveRecs.length}</span></span><span style=\"color:var(--khaki);white-space:nowrap\">БАЛІВ ЗА ЗВІТ:&nbsp;<span style=\"color:var(--yellow)\">${_arTotal}</span></span></div>`:'';\n"
        "                const _drnCnt={};state.archiveRecs.forEach(r=>{if(r.drone)_drnCnt[r.drone]=(_drnCnt[r.drone]||0)+1;});\n"
        "                const _ammoCnt={};state.archiveRecs.forEach(r=>{if(r.ammo)_ammoCnt[r.ammo]=(_ammoCnt[r.ammo]||0)+1;});\n"
        "                const _resCnt={};state.archiveRecs.forEach(r=>{if(r.result)r.result.split(', ').forEach(x=>{x=x.trim();if(x)_resCnt[x]=(_resCnt[x]||0)+1;});});\n"
        "                const _row=(label,val,suf='')=>`<p class=\"stencil\" style=\"color:var(--text);margin:1px 0\">${label} <span style=\"color:var(--yellow)\">— ${val}${suf}</span></p>`;\n"
        "                const _sec=(title,rows)=>rows?`<div><p class=\"stencil\" style=\"color:var(--khaki);font-size:calc(0.85em + 2px);letter-spacing:0.08em;margin-bottom:4px\">${title}</p>${rows}</div>`:'';\n"
        "                const _drnRows=Object.entries(_drnCnt).sort((a,b)=>b[1]-a[1]).map(([d,c])=>_row(esc(d),c,' шт')).join('');\n"
        "                const _ammoRows=Object.entries(_ammoCnt).sort((a,b)=>b[1]-a[1]).map(([a,c])=>_row(esc(a),c,' шт')).join('');\n"
        "                const _pvrRows=state.pvr.map(pvr=>{const tot=Object.entries(pvr.map).reduce((s,[am,cf])=>s+(_ammoCnt[am]||0)*cf,0);return tot?_row(esc(pvr.name),tot+' кг'):'';}).filter(Boolean).join('');\n"
        "                const _resRows=Object.entries(_resCnt).sort((a,b)=>b[1]-a[1]).map(([r,c])=>_row(esc(r),c,' разів')).join('');\n"
        "                const _statsBlock=state.archiveRecs.length>0?`<div class=\"crate p-4\"><div class=\"flex flex-wrap gap-4\"><div class=\"space-y-3\" style=\"flex:2 1 220px\">${_sec('ДРОНИ',_drnRows)}${_sec('БОЄПРИПАСИ',_ammoRows)}${_sec('ПВР',_pvrRows)}</div><div style=\"flex:3 1 280px\">${_sec('РЕЗУЛЬТАТИ',_resRows)}</div></div></div>`:'';\n"
        "                _arContent=`<div style=\"display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;padding:0 8px 4px\"><h1 class=\"stencil-shadow text-3xl\" style=\"color:var(--yellow)\">${esc(state.selArchive)}</h1>${_arHeader}</div><h2 class=\"stencil-shadow text-xl px-2\" style=\"color:var(--yellow)\">СТАТИСТИКА</h2>${_statsBlock}<h2 class=\"stencil-shadow text-xl px-2\" style=\"color:var(--yellow)\">ВИЛЬОТИ</h2>${_arGroups||'<div class=\"crate p-4\"><p class=\"stencil text-center py-2\" style=\"color:var(--text-dim)\">Немає записів</p></div>'}`;\n"
        "            }\n"
        "        }\n"
        "        h+=`<div class=\"p-4 space-y-4 zvity-wrap\">\n"
        "            <h1 class=\"stencil-shadow text-3xl px-2\" style=\"color:var(--yellow)\">АРХІВ</h1>\n"
        "            <div class=\"crate p-4\"><div class=\"flex flex-wrap gap-2\">${state.archiveLoading&&!state.selArchive?'<p class=\"stencil text-center py-2\" style=\"color:var(--text-dim)\">Завантаження...</p>':_arBtns}</div></div>\n"
        "            ${state.selArchive?_arContent:''}\n"
        "        </div>`;\n"
        "    }\n"
        "\n"
        "    if(state.page==='vyloty') {",

        'archive-page-render'
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

    # Remove large inline images by alt text (too big for normal patch)
    lines = html.split('\n')
    before = len(lines)
    lines = [l for l in lines if 'alt="CONFIDENTIAL"' not in l and 'alt="Тризуб"' not in l]
    removed = before - len(lines)
    html = '\n'.join(lines)
    print(f"[OK]   Removed {removed} large image line(s) (CONFIDENTIAL + Тризуб)")

    # Shrink header grid from 3 to 2 columns after removing image
    html = html.replace(
        '<div class="grid gap-4 items-center mb-4" style="grid-template-columns: auto 1fr auto">',
        '<div class="grid gap-4 items-center mb-4" style="grid-template-columns: 1fr auto">',
        1
    )
    print("[OK]   Header grid: auto 1fr auto → 1fr auto")

    # ── ЗВІТ НА header: Уражено... зліва від заголовку ──
    _btn = (
        '<button onclick="copyReport()" '
        'onmousedown="this.classList.add(\'active\')" '
        'onmouseup="this.classList.remove(\'active\')" '
        'ontouchstart="this.classList.add(\'active\')" '
        'ontouchend="this.classList.remove(\'active\')" '
        'class="btn-stencil btn-black">КОПІЮВАТИ</button>'
    )
    _old_zvit = (
        '<h3 class="stencil-shadow" style="color: var(--yellow)">ЗВІТ НА ${state.selDate}</h3>\n'
        '                    <div class="flex gap-2 flex-wrap">\n'
        '                        ' + _btn + '\n'
        '                    </div>\n'
        '                </div>\n'
        '                <div class="report-box">${reportLines.join(\'\\n\')}</div>'
    )
    _new_zvit = (
        '<div style="display:flex;align-items:center;gap:1.5em;flex-wrap:wrap">\n'
        '                        <h3 class="stencil-shadow" style="color: var(--yellow)">ДОПОВІДЬ НА ${state.selDate}</h3>\n'
        '                        <span class="stencil" style="color:var(--khaki)">'
        'Уражено орієнтовно на <span style="color:var(--text)">'
        '${Math.round(dayRecs.reduce((s,r)=>s+(parseFloat(r.points)||0),0))}</span> балів'
        '</span>\n'
        '                    </div>\n'
        '                    <div class="flex gap-2 flex-wrap">\n'
        '                        ' + _btn + '\n'
        '                    </div>\n'
        '                </div>\n'
        '                <div class="report-box">'
        "${reportLines.filter(l=>!l.startsWith('Уражено')).join('\\n')}</div>"
    )
    if _old_zvit in html:
        html = html.replace(_old_zvit, _new_zvit, 1)
        print("[OK]   ЗВІТ НА header: Уражено... зліва")
    else:
        print("[FAIL] ЗВІТ НА header: old string not found")

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
