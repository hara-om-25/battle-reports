#!/usr/bin/env python3
import base64
import json
import urllib.request
import urllib.error
import sys
import os

SOURCE_FILE = "/mnt/user-data/outputs/battle-v70.html"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_OWNER = "hara-om-25"
REPO_NAME = "battle-reports"
TARGET_PATH = "index.html"
BRANCH = "main"
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
    status, body = github_request("GET", f"/repos/{REPO_OWNER}/{REPO_NAME}/contents/{TARGET_PATH}?ref={BRANCH}")
    if status == 200:
        return body.get("sha")
    if status == 404:
        return None
    print(f"[ERROR] Не вдалося отримати SHA файлу: HTTP {status}")
    print(f"        {body.get('message', body)}")
    sys.exit(1)


def main():
    # Перевірка токену
    if not GITHUB_TOKEN:
        print("[ERROR] Встановіть змінну середовища GITHUB_TOKEN")
        print("        export GITHUB_TOKEN=ghp_...")
        sys.exit(1)

    # 1. Читаємо файл
    if not os.path.isfile(SOURCE_FILE):
        print(f"[ERROR] Файл не знайдено: {SOURCE_FILE}")
        sys.exit(1)

    print(f"[INFO]  Читаємо файл: {SOURCE_FILE}")
    with open(SOURCE_FILE, "rb") as f:
        raw = f.read()
    print(f"[INFO]  Розмір файлу: {len(raw):,} байт")

    # 2. Конвертуємо в base64
    encoded = base64.b64encode(raw).decode()
    print(f"[INFO]  Base64 довжина: {len(encoded):,} символів")

    # 3. Отримуємо поточний SHA (потрібен для оновлення існуючого файлу)
    sha = get_current_sha()
    if sha:
        print(f"[INFO]  Поточний SHA {TARGET_PATH}: {sha}")
    else:
        print(f"[INFO]  Файл {TARGET_PATH} відсутній — буде створено новий")

    # 4. PUT запит до GitHub API
    print(f"[INFO]  Завантажуємо як {TARGET_PATH} до {REPO_OWNER}/{REPO_NAME} (гілка: {BRANCH})...")
    payload = {
        "message": f"Upload battle-v70.html as {TARGET_PATH}",
        "content": encoded,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    status, body = github_request("PUT", f"/repos/{REPO_OWNER}/{REPO_NAME}/contents/{TARGET_PATH}", payload)

    # 5. Результат
    if status in (200, 201):
        action = "оновлено" if status == 200 else "створено"
        file_url = body.get("content", {}).get("html_url", "")
        print(f"\n[OK]    Файл успішно {action}!")
        print(f"[OK]    URL: {file_url}")
        print(f"[OK]    SHA нового коміту: {body.get('commit', {}).get('sha', 'н/д')}")
    else:
        print(f"\n[ERROR] GitHub API повернув HTTP {status}")
        print(f"        {body.get('message', json.dumps(body))}")
        sys.exit(1)


if __name__ == "__main__":
    main()
