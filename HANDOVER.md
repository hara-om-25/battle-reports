# Handover — Бойові Звіти

## Контекст

**Хто:** Hara Om (hara.om.25@gmail.com) — розробник/командир FPV-підрозділу.  
**Проєкт:** [`hara-om-25/battle-reports`](https://github.com/hara-om-25/battle-reports) — веб-застосунок для бойових звітів FPV-підрозділу.  
**Сайт:** https://hara-om-25.github.io/battle-reports/  
**Дедлайни:** не озвучені, але темп — активний (кілька правок за сесію).

**Мова:** завжди українська.  
**Стиль:** коротко і по суті; показує скрін — я читаю і реагую; підтверджує "+" або "ні".  
**Формат:** без зайвих коментарів; питань не ставити зайвих; якщо треба вибір — AskUserQuestion.

**Стек:**
- Один HTML-файл (`battlev78.html`) — source of truth, змінювати не можна.
- `patch_and_upload.py` (1570 рядків, 79 патчів) застосовує всі зміни до source і публікує.
- Деплой: `gh-pages` гілка → GitHub Pages.
- Worktree: `/tmp/gh-pages-wt/` (відстежує `origin/gh-pages`).
- Feature branch: `claude/upload-battle-report-CyhPM`.
- Node.js + Playwright доступні для генерації зображень.
- PIL доступний. `cairosvg`, `matplotlib` — відсутні.
- Google Maven (`dl.google.com`) заблокований локально (403) — збірки Android тільки через GitHub Actions.

---

## Що вже зроблено

| # | Що | Навіщо / Стан |
|---|-----|----------------|
| 1 | PWA manifest + service worker + іконки | Для генерації APK через PWABuilder. Задеплоєно. |
| 2 | Іконка — герб України | Користувач завантажив WebP (~1280×1280), PIL обрізав і змінив розмір до 192/512px. Задеплоєно. |
| 3 | TWA Android-проєкт (`twa-app/`) | Спроба зібрати APK через GitHub Actions. 8 build'ів впало. |
| 4 | Перехід на WebView підхід | `androidbrowserhelper` не резолвився в CI. Замінено на `MainActivity.java` без зовнішніх залежностей. Build #8 результат невідомий (користувач переключився). |
| 5 | Червона кнопка × (видалення цілі) | Патч `red-remove-btn` у `patch_and_upload.py`. Задеплоєно. |

**Ключові файли:**
- Source HTML: `/root/.claude/uploads/e4217b0b-9104-47c4-ad48-67688dcf82d0/80464875-battlev78.html`
- Patch script: `/home/user/battle-reports/patch_and_upload.py`
- Android-проєкт: `/home/user/battle-reports/twa-app/`
- CI workflow: `/home/user/battle-reports/.github/workflows/build-apk.yml`
- gh-pages worktree: `/tmp/gh-pages-wt/`

**Важливі висновки:**
- PWABuilder (pwabuilder.com) лежав під час сесії — не використовувати як основний шлях.
- Збірка APK через GitHub Actions: 7 провалів (34-64с кожен). Причини: відсутній `gradle-wrapper.jar`, змішані стилі `buildscript`/`plugins`, `FAIL_ON_PROJECT_REPOS`, зовнішня залежність `androidbrowserhelper`.
- Build #8 (WebView, `compileSdk 33`, без зовнішніх залежностей) — результат невідомий.

---

## Поточний стан

**Остання дія:** задеплоєно патч "червона кнопка ×" на gh-pages (commit `adcfa72`).

**Що працює:**
- Сайт: https://hara-om-25.github.io/battle-reports/ ✓
- PWA: manifest, icons (герб), service worker — всі на gh-pages ✓
- Усі 79 патчів застосовуються без помилок ✓
- Деплой-пайплайн (`patch_and_upload.py` → gh-pages worktree) ✓

**Що не вирішено:**
- APK: build #8 (WebView підхід) — результат після останнього push `d068321` невідомий. Потрібно перевірити Actions.
- Google OAuth у WebView: застосовано Chrome user agent як workaround, але не тестовано реально.

**Відкриті питання:**
- Чи зібрався build #8? (перевірити вкладку Actions → Build APK)
- Чи працює Google OAuth в WebView з Chrome UA?
- ? Чи потрібен `assetlinks.json` для повноцінного TWA (без адресного рядка)?

---

## Наступні кроки

1. **Перевірити build #8** — відкрити Actions → Build APK → останній run. Якщо зелений — завантажити APK і тестувати. Якщо червоний — показати лог кроку "Build debug APK" (клікнути на job → розгорнути крок).
2. **Якщо APK зібрався** — протестувати OAuth (Google Sign-In у WebView).
3. **Якщо OAuth не працює** — або перейти на `androidx.browser:browser` (Chrome Custom Tabs, API без login wall), або додати `intent://` interceptor у `WebViewClient`.
4. **Якщо build знову впав** — показати лог помилки (не Summary, а кроки всередині job).

---

## Підказки для нової сесії Claude

**Стиль і тон:**
- Коротко. Одне речення на оновлення статусу.
- Не нумерувати кожен крок — просто робити.
- Перед деплоєм показувати preview тільки якщо є нова іконка/зображення.

**Чого уникати:**
- Не пропонувати "спробуємо X підхід" — одразу робити.
- Не питати "підтвердити?" перед кожним кроком — тільки перед деструктивними діями.
- Не пояснювати що таке TWA, WebView, Gradle — користувач знає або не хоче знати деталі.
- `android-actions/setup-android@v3` — не використовував, прибрали. Не повертати.

**Домовленості:**
- Деплой = build HTML через `patch_and_upload.py` → скопіювати в `/tmp/gh-pages-wt/` → commit/push з `git -c gpg.format='' -c commit.gpgsign=false`.
- Новий патч завжди додавати в `patch_and_upload.py` перед рядком `# ── 79.` (PWA SW register).
- Іконки APK — в `/tmp/pwa_icons/` та `/tmp/twa_icons/`.
- GitHub token — у змінній середовища `GITHUB_TOKEN`.

---

**TL;DR:** PWA задеплоєно, APK build #8 (WebView, без deps) — результат невідомий; першим ділом перевір Actions → Build APK і скинь скрін.
