#!/usr/bin/env python3
"""Signal-бот черги.

Слухає чат-джерело, шукає в повідомленнях ключові слова і пересилає знайдені
повідомлення в чат черги. Кожне переслане повідомлення адресується (через
@-згадку) наступному користувачу з черги по колу.

Працює поверх signal-cli-rest-api (https://github.com/bbernhard/signal-cli-rest-api).
Залежностей, крім стандартної бібліотеки Python, немає.
"""

import argparse
import base64
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("signal-queue-bot")


# --------------------------------------------------------------------------- #
# Конфігурація
# --------------------------------------------------------------------------- #

DEFAULT_CONFIG = {
    "api_url": "http://localhost:8080",
    "bot_number": "",
    "source_group": "",
    "queue_group": "",
    "keywords": [],
    "case_sensitive": False,
    "whole_word": False,
    "admins": [],
    "state_file": "state.json",
    "poll_interval": 2,
    "command_prefix": "/",
}

ENV_MAP = {
    "SIGNAL_API_URL": "api_url",
    "BOT_NUMBER": "bot_number",
    "SOURCE_GROUP": "source_group",
    "QUEUE_GROUP": "queue_group",
    "KEYWORDS": "keywords",
    "ADMINS": "admins",
    "STATE_FILE": "state_file",
}


def load_config(path):
    cfg = dict(DEFAULT_CONFIG)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    for env, key in ENV_MAP.items():
        value = os.environ.get(env)
        if value:
            if key in ("keywords", "admins"):
                value = [v.strip() for v in value.split(",") if v.strip()]
            cfg[key] = value
    return cfg


def group_send_id(group):
    """Повертає id групи у форматі для відправки: `group.<base64>`."""
    if not group:
        return ""
    if group.startswith("group."):
        return group
    return "group." + base64.b64encode(group.encode()).decode()


def group_internal_id(group):
    """Повертає внутрішній id групи (той, що приходить у вхідних повідомленнях)."""
    if not group:
        return ""
    if group.startswith("group."):
        return base64.b64decode(group[len("group."):]).decode()
    return group


def utf16_len(text):
    """Signal рахує позиції згадок в UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


# --------------------------------------------------------------------------- #
# Черга
# --------------------------------------------------------------------------- #

class Queue:
    """Кругова черга користувачів, яка зберігається у JSON-файлі."""

    def __init__(self, path):
        self.path = path
        self.members = []  # [{"id": uuid або номер, "name": "..."}]
        self.position = 0  # індекс того, хто отримає наступне повідомлення
        self.lock = threading.Lock()
        self._load()

    def _load(self):
        if self.path and os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.members = data.get("members", [])
            self.position = data.get("position", 0)
        self._normalize()

    def _save(self):
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"members": self.members, "position": self.position},
                      f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _normalize(self):
        if not self.members:
            self.position = 0
        else:
            self.position %= len(self.members)

    def _find(self, member_id):
        for i, m in enumerate(self.members):
            if m["id"] == member_id:
                return i
        return -1

    def add(self, member_id, name):
        with self.lock:
            if self._find(member_id) >= 0:
                return False
            self.members.append({"id": member_id, "name": name or member_id})
            self._save()
            return True

    def remove(self, member_id):
        with self.lock:
            i = self._find(member_id)
            if i < 0:
                return False
            self.members.pop(i)
            if i < self.position:
                self.position -= 1
            self._normalize()
            self._save()
            return True

    def peek(self):
        with self.lock:
            return self.members[self.position] if self.members else None

    def next(self):
        """Повертає поточного користувача і зсуває чергу на одного вперед."""
        with self.lock:
            if not self.members:
                return None
            member = self.members[self.position]
            self.position = (self.position + 1) % len(self.members)
            self._save()
            return member

    def skip(self):
        with self.lock:
            if not self.members:
                return None
            self.position = (self.position + 1) % len(self.members)
            self._save()
            return self.members[self.position]

    def clear(self):
        with self.lock:
            self.members = []
            self.position = 0
            self._save()

    def ordered(self):
        """Учасники в порядку, в якому вони отримуватимуть повідомлення."""
        with self.lock:
            return self.members[self.position:] + self.members[:self.position]


# --------------------------------------------------------------------------- #
# Аналіз повідомлень
# --------------------------------------------------------------------------- #

class KeywordMatcher:
    def __init__(self, keywords, case_sensitive=False, whole_word=False):
        self.keywords = [k for k in keywords if k]
        flags = 0 if case_sensitive else re.IGNORECASE
        parts = [re.escape(k) for k in sorted(self.keywords, key=len, reverse=True)]
        if not parts:
            self.regex = None
        elif whole_word:
            self.regex = re.compile(r"(?<!\w)(?:%s)(?!\w)" % "|".join(parts), flags)
        else:
            self.regex = re.compile("|".join(parts), flags)

    def find(self, text):
        """Повертає список унікальних знайдених ключових слів (як у тексті)."""
        if not self.regex or not text:
            return []
        found = []
        seen = set()
        for m in self.regex.finditer(text):
            key = m.group(0).lower()
            if key not in seen:
                seen.add(key)
                found.append(m.group(0))
        return found


def analyze(text, matcher):
    """Аналізує повідомлення. Повертає dict з результатом або None."""
    hits = matcher.find(text)
    if not hits:
        return None
    return {
        "keywords": hits,
        "text": text.strip(),
        "phones": re.findall(r"\+?\d[\d\-\s()]{8,}\d", text),
        "links": re.findall(r"https?://\S+", text),
    }


# --------------------------------------------------------------------------- #
# Клієнт signal-cli-rest-api
# --------------------------------------------------------------------------- #

class SignalAPI:
    def __init__(self, base_url, number):
        self.base_url = base_url.rstrip("/")
        self.number = number

    def _request(self, method, path, payload=None, timeout=30):
        url = self.base_url + path
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode() or "null"
        return json.loads(body)

    def receive(self):
        number = urllib.parse.quote(self.number)
        return self._request("GET", f"/v1/receive/{number}", timeout=90) or []

    def groups(self):
        number = urllib.parse.quote(self.number)
        return self._request("GET", f"/v1/groups/{number}") or []

    def send(self, recipient, text, mentions=None):
        payload = {
            "number": self.number,
            "recipients": [recipient],
            "message": text,
        }
        if mentions:
            payload["mentions"] = mentions
        return self._request("POST", "/v2/send", payload)


# --------------------------------------------------------------------------- #
# Бот
# --------------------------------------------------------------------------- #

HELP_TEXT = """Команди бота черги:
/add @користувач … — додати в чергу (можна кількох, або номер +380…)
/remove @користувач — прибрати з черги
/join — додати себе
/leave — прибрати себе
/queue — показати чергу
/next — хто наступний
/skip — пропустити поточного
/clear — очистити чергу
/help — ця довідка"""


class Bot:
    def __init__(self, cfg, api=None, queue=None):
        self.cfg = cfg
        self.api = api or SignalAPI(cfg["api_url"], cfg["bot_number"])
        self.queue = queue or Queue(cfg["state_file"])
        self.matcher = KeywordMatcher(cfg["keywords"], cfg.get("case_sensitive", False),
                                      cfg.get("whole_word", False))
        self.source_id = group_internal_id(cfg["source_group"])
        self.queue_id = group_internal_id(cfg["queue_group"])
        self.queue_send = group_send_id(cfg["queue_group"])
        self.prefix = cfg.get("command_prefix", "/")
        self.admins = set(cfg.get("admins") or [])

    # ---- вхідні повідомлення ---------------------------------------------- #

    def handle_envelope(self, item):
        env = item.get("envelope", item)
        dm = env.get("dataMessage")
        if not dm:
            return
        text = dm.get("message") or ""
        group = (dm.get("groupInfo") or {}).get("groupId", "")
        sender = {
            "id": env.get("sourceUuid") or env.get("sourceNumber") or env.get("source"),
            "number": env.get("sourceNumber") or env.get("source"),
            "name": env.get("sourceName") or env.get("sourceNumber") or "невідомий",
        }
        if sender["number"] == self.cfg["bot_number"]:
            return

        if group and group == self.queue_id and text.startswith(self.prefix):
            self.handle_command(text, dm.get("mentions") or [], sender)
        elif group and group == self.source_id:
            self.handle_source(text, dm, sender)

    def handle_source(self, text, dm, sender):
        result = analyze(text, self.matcher)
        if not result:
            return
        log.info("Ключові слова %s у повідомленні від %s", result["keywords"], sender["name"])
        self.forward(result, sender, attachments=len(dm.get("attachments") or []))

    def forward(self, result, sender, attachments=0):
        member = self.queue.next()
        header = "📨 Нове повідомлення\n"
        header += f"Від: {sender['name']}\n"
        header += f"Ключові слова: {', '.join(result['keywords'])}\n"
        if result["phones"]:
            header += f"Телефони: {', '.join(p.strip() for p in result['phones'])}\n"
        if result["links"]:
            header += f"Посилання: {', '.join(result['links'])}\n"
        if attachments:
            header += f"Вкладень: {attachments} (дивіться в чаті-джерелі)\n"
        body = f"\n{result['text']}\n\n"

        if member:
            prefix = header + body + "👉 Відповідальний: "
            tag = "@" + member["name"]
            text = prefix + tag
            mentions = [{"author": member["id"], "start": utf16_len(prefix),
                         "length": utf16_len(tag)}]
        else:
            text = header + body + "⚠️ Черга порожня — додайте людей командою /add"
            mentions = None
        self.send(text, mentions)

    # ---- команди ---------------------------------------------------------- #

    def is_admin(self, sender):
        return not self.admins or sender["number"] in self.admins or sender["id"] in self.admins

    def handle_command(self, text, mentions, sender):
        parts = text[len(self.prefix):].split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd == "help":
            return self.send(HELP_TEXT)
        if cmd == "queue":
            return self.send(self.format_queue())
        if cmd == "next":
            member = self.queue.peek()
            return self.send(f"Наступний: {member['name']}" if member else "Черга порожня")
        if cmd == "join":
            ok = self.queue.add(sender["id"], sender["name"])
            return self.send(f"{sender['name']} у черзі" if ok else "Ви вже в черзі")
        if cmd == "leave":
            ok = self.queue.remove(sender["id"])
            return self.send(f"{sender['name']} вийшов(-ла) з черги" if ok else "Вас немає в черзі")

        if cmd not in ("add", "remove", "skip", "clear"):
            return self.send(f"Невідома команда. {self.prefix}help — список команд")
        if not self.is_admin(sender):
            return self.send("Ця команда доступна лише адміністраторам")

        if cmd == "skip":
            member = self.queue.skip()
            return self.send(f"Пропущено. Наступний: {member['name']}" if member else "Черга порожня")
        if cmd == "clear":
            self.queue.clear()
            return self.send("Чергу очищено")

        targets = self.parse_targets(text, mentions, args)
        if not targets:
            return self.send(f"Вкажіть користувача: {self.prefix}{cmd} @ім'я або номер")
        done = []
        for member_id, name in targets:
            if cmd == "add" and self.queue.add(member_id, name):
                done.append(name)
            elif cmd == "remove" and self.queue.remove(member_id):
                done.append(name)
        verb = "Додано" if cmd == "add" else "Видалено"
        self.send(f"{verb}: {', '.join(done)}" if done else "Нічого не змінено")

    def parse_targets(self, text, mentions, args):
        targets = []
        for m in mentions:
            member_id = m.get("uuid") or m.get("number")
            name = m.get("name") or m.get("number") or member_id
            if member_id:
                targets.append((member_id, name))
        for arg in args:
            if re.fullmatch(r"\+\d{7,15}", arg):
                targets.append((arg, arg))
        return targets

    def format_queue(self):
        members = self.queue.ordered()
        if not members:
            return "Черга порожня"
        lines = ["Черга (першим отримає наступне повідомлення):"]
        lines += [f"{i}. {m['name']}" for i, m in enumerate(members, 1)]
        return "\n".join(lines)

    # ---- відправка / цикл ------------------------------------------------- #

    def send(self, text, mentions=None):
        try:
            self.api.send(self.queue_send, text, mentions)
        except (urllib.error.URLError, OSError) as e:
            log.error("Не вдалося надіслати повідомлення: %s", e)

    def run(self):
        log.info("Бот запущено. Джерело: %s, черга: %s, ключові слова: %s",
                 self.cfg["source_group"], self.cfg["queue_group"], self.cfg["keywords"])
        while True:
            try:
                for item in self.api.receive():
                    try:
                        self.handle_envelope(item)
                    except Exception:
                        log.exception("Помилка обробки повідомлення")
            except (urllib.error.URLError, OSError, ValueError) as e:
                log.warning("Помилка отримання повідомлень: %s", e)
                time.sleep(5)
            time.sleep(self.cfg.get("poll_interval", 2))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None):
    parser = argparse.ArgumentParser(description="Signal-бот черги")
    parser.add_argument("-c", "--config", default="config.json", help="шлях до config.json")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "groups"],
                        help="run — запустити бота; groups — показати групи бота та їх id")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    if not cfg["bot_number"]:
        sys.exit("Не задано bot_number (config.json або змінна BOT_NUMBER)")

    api = SignalAPI(cfg["api_url"], cfg["bot_number"])
    if args.command == "groups":
        for g in api.groups():
            print(f"{g.get('name')!r}\n  id: {g.get('id')}\n  internal_id: {g.get('internal_id')}")
        return

    missing = [k for k in ("source_group", "queue_group", "keywords") if not cfg[k]]
    if missing:
        sys.exit("Не задано: " + ", ".join(missing))
    Bot(cfg, api=api).run()


if __name__ == "__main__":
    main()
