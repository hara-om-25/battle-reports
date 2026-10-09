#!/usr/bin/env python3
"""Signal-бот черги.

Слухає чат-джерело, шукає в повідомленнях ключові слова і пересилає знайдені
повідомлення в чат черги. Кожне переслане повідомлення адресується (через
@-згадку і голосове повідомлення) наступному користувачу з черги.

Відповідальний відповідає реакцією: ➕ — беру, ➖ — не можу. На ➖ або якщо
ніхто не відреагував за заданий час, повідомлення переходить до наступного.

Працює поверх signal-cli-rest-api (https://github.com/bbernhard/signal-cli-rest-api).
Для голосових повідомлень потрібен пакет gTTS (необов'язково).
"""

import argparse
import base64
import io
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
    # Скільки хвилин чекати на ➕/➖, перш ніж передати наступному (0 — не чекати).
    "response_timeout_minutes": 5,
    # Що робити з тим, хто поставив ➖ або не відповів:
    #   "end"  — перемістити в кінець черги;
    #   "next" — він отримає наступне нове повідомлення.
    "pass_mode": "end",
    "accept_reactions": ["➕", "👍", "✅", "+"],
    "decline_reactions": ["➖", "👎", "❌", "-"],
    "voice": True,
    "voice_lang": "uk",
    "voice_template": "Прийшла черга {name}, {pos} з {total}",
}

# Налаштування, які адміністратор може змінювати командами в чаті.
RUNTIME_SETTINGS = ("response_timeout_minutes", "pass_mode", "voice")
PASS_MODES = {"end": "в кінець черги", "next": "отримає наступне повідомлення"}

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
        with open(path, encoding="utf-8-sig") as f:
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


def normalize_emoji(text):
    return (text or "").replace("️", "").strip()


def parse_duration(text):
    """'5', '5m', '30s', '1h', '1.5' -> хвилини (float). None, якщо не розібрано."""
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(s|с|m|м|хв|h|г|год)?", text.strip().lower())
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    unit = m.group(2) or "m"
    if unit in ("s", "с"):
        return value / 60
    if unit in ("h", "г", "год"):
        return value * 60
    return value


def format_minutes(minutes):
    if not minutes:
        return "вимкнено"
    if minutes < 1:
        return f"{round(minutes * 60)} с"
    return f"{minutes:g} хв"


# --------------------------------------------------------------------------- #
# Стан: черга, завдання, налаштування
# --------------------------------------------------------------------------- #

class State:
    """Черга користувачів, активні завдання і налаштування; зберігається в JSON.

    members — список учасників у порядку додавання (номер у списку = N у "N/M").
    order   — порядок отримання повідомлень: перший отримає наступне.
    tasks   — повідомлення, які чекають на ➕/➖.
    """

    def __init__(self, path):
        self.path = path
        self.members = []   # [{"id": uuid або номер, "number": "+380…", "name": "…"}]
        self.order = []     # [id, …]
        self.tasks = []     # [{"id", "text", "assignee", "tried", "deadline", "messages"}]
        self.settings = {}
        self.next_task_id = 1
        self.lock = threading.RLock()
        self._load()

    def _load(self):
        if self.path and os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.members = data.get("members", [])
            self.order = data.get("order")
            if self.order is None:  # формат попередньої версії: members + position
                pos = data.get("position", 0)
                ids = [m["id"] for m in self.members]
                self.order = ids[pos:] + ids[:pos]
            self.tasks = data.get("tasks", [])
            self.settings = data.get("settings", {})
            self.next_task_id = data.get("next_task_id", 1)
        ids = {m["id"] for m in self.members}
        self.order = [i for i in self.order if i in ids]
        self.order += [m["id"] for m in self.members if m["id"] not in self.order]

    def save(self):
        if not self.path:
            return
        with self.lock:
            data = {"members": self.members, "order": self.order, "tasks": self.tasks,
                    "settings": self.settings, "next_task_id": self.next_task_id}
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    # ---- учасники --------------------------------------------------------- #

    def member(self, member_id):
        for m in self.members:
            if m["id"] == member_id:
                return m
        return None

    def find(self, *ids):
        """Шукає учасника за uuid або номером телефону."""
        ids = {i for i in ids if i}
        for m in self.members:
            if m["id"] in ids or m.get("number") in ids:
                return m
        return None

    def number(self, member_id):
        for i, m in enumerate(self.members, 1):
            if m["id"] == member_id:
                return i
        return 0

    def add(self, member_id, name, number=None):
        with self.lock:
            if self.find(member_id, number):
                return False
            self.members.append({"id": member_id, "number": number, "name": name or member_id})
            self.order.append(member_id)
            self.save()
            return True

    def remove(self, member_id):
        with self.lock:
            m = self.member(member_id)
            if not m:
                return False
            self.members.remove(m)
            self.order.remove(member_id)
            self.save()
            return True

    def clear(self):
        with self.lock:
            self.members, self.order = [], []
            self.save()

    def ordered(self):
        with self.lock:
            return [self.member(i) for i in self.order]

    def head(self, exclude=()):
        with self.lock:
            for i in self.order:
                if i not in exclude:
                    return self.member(i)
            return None

    def take(self, exclude=()):
        """Бере першого з черги (крім exclude) і переміщує його в кінець."""
        with self.lock:
            m = self.head(exclude)
            if m:
                self.move_to_end(m["id"])
            return m

    def move_to_end(self, member_id):
        with self.lock:
            if member_id in self.order:
                self.order.remove(member_id)
                self.order.append(member_id)
                self.save()

    def move_to_front(self, member_id):
        with self.lock:
            if member_id in self.order:
                self.order.remove(member_id)
                self.order.insert(0, member_id)
                self.save()

    def skip(self):
        with self.lock:
            if not self.order:
                return None
            self.move_to_end(self.order[0])
            return self.member(self.order[0])

    # ---- завдання --------------------------------------------------------- #

    def new_task(self, text):
        with self.lock:
            task = {"id": self.next_task_id, "text": text, "assignee": None,
                    "tried": [], "deadline": None, "messages": []}
            self.next_task_id += 1
            self.tasks.append(task)
            return task

    def task_by_message(self, timestamp):
        with self.lock:
            for t in self.tasks:
                if timestamp in t["messages"]:
                    return t
            return None

    def close_task(self, task):
        with self.lock:
            if task in self.tasks:
                self.tasks.remove(task)
            self.save()


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
# Голосові повідомлення
# --------------------------------------------------------------------------- #

def synthesize_voice(text, lang="uk"):
    """Повертає MP3 (bytes) з озвученим текстом або None, якщо не вдалося."""
    try:
        from gtts import gTTS
    except ImportError:
        log.warning("gTTS не встановлено — голосові повідомлення вимкнено (pip install gTTS)")
        return None
    try:
        buf = io.BytesIO()
        gTTS(text, lang=lang).write_to_fp(buf)
        return buf.getvalue()
    except Exception as e:
        log.warning("Не вдалося озвучити текст: %s", e)
        return None


def voice_attachment(mp3):
    return "data:audio/mpeg;filename=cherga.mp3;base64," + base64.b64encode(mp3).decode()


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

    def send(self, recipient, text, mentions=None, attachments=None):
        """Надсилає повідомлення; повертає його timestamp (int) або None."""
        payload = {"number": self.number, "recipients": [recipient], "message": text}
        if mentions:
            payload["mentions"] = mentions
        if attachments:
            payload["base64_attachments"] = attachments
        result = self._request("POST", "/v2/send", payload, timeout=60) or {}
        ts = result.get("timestamp")
        return int(ts) if ts else None


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
/timeout 5 — час на відповідь у хвилинах (30s, 1h; 0 — не чекати)
/mode end | next — куди переносити того, хто не взяв: у кінець черги / на наступне повідомлення
/voice on | off — голосові повідомлення
/settings — поточні налаштування
/tasks — повідомлення, що чекають відповіді
/help — ця довідка

Відповідь на повідомлення бота: реакція ➕ — беру, ➖ — не можу
(або відповідь на повідомлення текстом "+" / "-")."""

ADMIN_COMMANDS = {"add", "remove", "skip", "clear", "timeout", "mode", "voice"}


class Bot:
    def __init__(self, cfg, api=None, state=None, tts=synthesize_voice, clock=time.time):
        self.cfg = cfg
        self.api = api or SignalAPI(cfg["api_url"], cfg["bot_number"])
        self.state = state or State(cfg["state_file"])
        self.tts = tts
        self.clock = clock
        self.lock = self.state.lock
        self.matcher = KeywordMatcher(cfg["keywords"], cfg.get("case_sensitive", False),
                                      cfg.get("whole_word", False))
        self.source_id = group_internal_id(cfg["source_group"])
        self.queue_id = group_internal_id(cfg["queue_group"])
        self.queue_send = group_send_id(cfg["queue_group"])
        self.prefix = cfg.get("command_prefix", "/")
        self.admins = set(cfg.get("admins") or [])
        self.accept = {normalize_emoji(e) for e in cfg.get("accept_reactions", [])}
        self.decline = {normalize_emoji(e) for e in cfg.get("decline_reactions", [])}
        # Повідомлення, надіслані до запуску бота (накопичені, поки він був вимкнений),
        # не пересилаються і не виконуються як команди.
        self.started_ms = int(self.clock() * 1000)

    def setting(self, key):
        return self.state.settings.get(key, self.cfg.get(key, DEFAULT_CONFIG.get(key)))

    # ---- вхідні повідомлення ---------------------------------------------- #

    def handle_envelope(self, item):
        env = item.get("envelope", item)
        sender = {
            "id": env.get("sourceUuid") or env.get("sourceNumber") or env.get("source"),
            "number": env.get("sourceNumber") or env.get("source"),
            "name": env.get("sourceName") or env.get("sourceNumber") or "невідомий",
        }
        dm = env.get("dataMessage")
        if not dm:
            # Повідомлення, надіслані з основного телефона акаунта бота.
            dm = (env.get("syncMessage") or {}).get("sentMessage")
        if not dm:
            return
        group = (dm.get("groupInfo") or {}).get("groupId", "")
        text = dm.get("message") or ""
        old = self.is_old(env, dm)

        with self.lock:
            if group and group == self.queue_id:
                if dm.get("reaction"):
                    self.handle_reaction(dm["reaction"], sender)
                elif dm.get("quote") and normalize_emoji(text) in self.accept | self.decline:
                    self.handle_answer(dm["quote"].get("id"), normalize_emoji(text), sender)
                elif text.startswith(self.prefix) and not old:
                    self.handle_command(text, dm.get("mentions") or [], sender)
            elif group and group == self.source_id and not dm.get("reaction"):
                if old:
                    log.info("Пропущено повідомлення від %s, надіслане до запуску бота", sender["name"])
                else:
                    self.handle_source(text, dm, sender)

    def is_old(self, env, dm):
        """True, якщо повідомлення надіслане до запуску бота.

        Беремо час отримання сервером Signal (не залежить від годинника телефона
        відправника), а якщо його немає — час відправлення.
        """
        ts = env.get("serverReceivedTimestamp") or env.get("timestamp") or dm.get("timestamp")
        try:
            return bool(ts) and int(ts) < self.started_ms
        except (TypeError, ValueError):
            return False

    def handle_source(self, text, dm, sender):
        result = analyze(text, self.matcher)
        if not result:
            return
        log.info("Ключові слова %s у повідомленні від %s", result["keywords"], sender["name"])
        self.forward(result, sender, attachments=len(dm.get("attachments") or []))

    def handle_reaction(self, reaction, sender):
        if reaction.get("isRemove"):
            return
        target = reaction.get("targetSentTimestamp")
        self.handle_answer(int(target) if target else None, normalize_emoji(reaction.get("emoji")), sender)

    def handle_answer(self, timestamp, answer, sender):
        task = self.state.task_by_message(timestamp) if timestamp else None
        if not task:
            return
        member = self.state.find(sender["id"], sender["number"])
        if not member or member["id"] != task["assignee"]:
            return  # відповідати може лише той, на кого зараз покладено повідомлення
        if answer in self.accept:
            log.info("%s взяв(-ла) повідомлення #%s", member["name"], task["id"])
            self.state.close_task(task)
        elif answer in self.decline:
            self.reassign(task, f"{member['name']} не може")

    def check_timeouts(self):
        """Передає наступному повідомлення, на які не відповіли вчасно."""
        with self.lock:
            now = self.clock()
            for task in list(self.state.tasks):
                if task["deadline"] and task["deadline"] <= now:
                    m = self.state.member(task["assignee"])
                    name = m["name"] if m else "Відповідальний"
                    minutes = format_minutes(self.setting("response_timeout_minutes"))
                    self.reassign(task, f"{name} не відповів(-ла) за {minutes}")

    # ---- призначення ------------------------------------------------------ #

    def forward(self, result, sender, attachments=0):
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

        if not self.state.order:
            self.send(header + body + "⚠️ Черга порожня — додайте людей командою /add")
            return
        task = self.state.new_task(result["text"])
        self.assign(task, header + body)

    def reassign(self, task, reason):
        previous = task["assignee"]
        quoted = task["text"] if len(task["text"]) <= 300 else task["text"][:300] + "…"
        intro = f"↪️ {reason}.\n\n📨 {quoted}\n\n"
        if not self.assign(task, intro, previous=previous):
            return
        if previous and self.setting("pass_mode") == "next":
            self.state.move_to_front(previous)
        elif previous:
            self.state.move_to_end(previous)
        self.state.save()

    def assign(self, task, intro, previous=None):
        """Призначає завдання наступному з черги. False, якщо черга вичерпана."""
        member = self.state.take(exclude=task["tried"])
        if not member:
            self.send(intro + "⛔ Ніхто з черги не взяв це повідомлення. Потрібне рішення адміністратора.")
            self.state.close_task(task)
            return False

        pos, total = self.state.number(member["id"]), len(self.state.members)
        before = intro + "🔔 Прийшла черга "
        tag = "@" + member["name"]
        after = f" {pos}/{total}\nРеакція ➕ — беру, ➖ — не можу"
        minutes = self.setting("response_timeout_minutes")
        if minutes:
            after += f" (на відповідь {format_minutes(minutes)})"
        mentions = [{"author": member["id"], "start": utf16_len(before), "length": utf16_len(tag)}]

        attachments = None
        if self.setting("voice") and self.tts:
            phrase = self.setting("voice_template").format(name=member["name"], pos=pos, total=total)
            mp3 = self.tts(phrase, self.setting("voice_lang"))
            if mp3:
                attachments = [voice_attachment(mp3)]

        task["assignee"] = member["id"]
        task["tried"].append(member["id"])
        task["deadline"] = self.clock() + minutes * 60 if minutes else None
        ts = self.send(before + tag + after, mentions, attachments)
        if ts:
            task["messages"].append(ts)
        self.state.save()
        return True

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
            member = self.state.head()
            return self.send(f"Наступний: {member['name']}" if member else "Черга порожня")
        if cmd == "settings":
            return self.send(self.format_settings())
        if cmd == "tasks":
            return self.send(self.format_tasks())
        if cmd == "join":
            ok = self.state.add(sender["id"], sender["name"], sender["number"])
            return self.send(f"{sender['name']} у черзі" if ok else "Ви вже в черзі")
        if cmd == "leave":
            m = self.state.find(sender["id"], sender["number"])
            ok = bool(m) and self.state.remove(m["id"])
            return self.send(f"{sender['name']} вийшов(-ла) з черги" if ok else "Вас немає в черзі")

        if cmd not in ADMIN_COMMANDS:
            return self.send(f"Невідома команда. {self.prefix}help — список команд")
        if not self.is_admin(sender):
            return self.send("Ця команда доступна лише адміністраторам")

        if cmd == "skip":
            member = self.state.skip()
            return self.send(f"Пропущено. Наступний: {member['name']}" if member else "Черга порожня")
        if cmd == "clear":
            self.state.clear()
            return self.send("Чергу очищено")
        if cmd == "timeout":
            minutes = parse_duration(args[0]) if args else None
            if minutes is None:
                return self.send(f"Приклад: {self.prefix}timeout 5 (хвилин), 30s, 1h, 0 — не чекати")
            self.set_setting("response_timeout_minutes", minutes)
            return self.send(f"Час на відповідь: {format_minutes(minutes)}")
        if cmd == "mode":
            mode = args[0].lower() if args else ""
            if mode not in PASS_MODES:
                return self.send(f"Приклад: {self.prefix}mode end — в кінець черги, "
                                 f"{self.prefix}mode next — отримає наступне повідомлення")
            self.set_setting("pass_mode", mode)
            return self.send(f"Хто не взяв повідомлення — {PASS_MODES[mode]}")
        if cmd == "voice":
            value = args[0].lower() if args else ""
            if value not in ("on", "off"):
                return self.send(f"Приклад: {self.prefix}voice on або {self.prefix}voice off")
            self.set_setting("voice", value == "on")
            return self.send("Голосові повідомлення " + ("увімкнено" if value == "on" else "вимкнено"))

        targets = self.parse_targets(mentions, args)
        if not targets:
            return self.send(f"Вкажіть користувача: {self.prefix}{cmd} @ім'я або номер")
        done = []
        for member_id, name, number in targets:
            if cmd == "add" and self.state.add(member_id, name, number):
                done.append(name)
            elif cmd == "remove":
                m = self.state.find(member_id, number)
                if m and self.state.remove(m["id"]):
                    done.append(m["name"])
        verb = "Додано" if cmd == "add" else "Видалено"
        self.send(f"{verb}: {', '.join(done)}" if done else "Нічого не змінено")

    def set_setting(self, key, value):
        self.state.settings[key] = value
        if key == "response_timeout_minutes":
            # Нове значення діє і на повідомлення, які вже чекають відповіді.
            now = self.clock()
            for task in self.state.tasks:
                task["deadline"] = now + value * 60 if value else None
        self.state.save()

    def parse_targets(self, mentions, args):
        targets = []
        for m in mentions:
            member_id = m.get("uuid") or m.get("number")
            name = m.get("name") or m.get("number") or member_id
            if member_id:
                targets.append((member_id, name, m.get("number")))
        for arg in args:
            if re.fullmatch(r"\+\d{7,15}", arg):
                targets.append((arg, arg, arg))
        return targets

    def format_queue(self):
        members = self.state.ordered()
        if not members:
            return "Черга порожня"
        total = len(self.state.members)
        lines = ["Черга (першим отримає наступне повідомлення):"]
        lines += [f"{i}. {m['name']} ({self.state.number(m['id'])}/{total})"
                  for i, m in enumerate(members, 1)]
        return "\n".join(lines)

    def format_settings(self):
        return "\n".join([
            "Налаштування:",
            f"Час на відповідь: {format_minutes(self.setting('response_timeout_minutes'))}",
            f"Хто не взяв: {PASS_MODES.get(self.setting('pass_mode'), self.setting('pass_mode'))}",
            f"Голосові: {'увімкнено' if self.setting('voice') else 'вимкнено'}",
            f"Ключові слова: {', '.join(self.cfg['keywords'])}",
        ])

    def format_tasks(self):
        if not self.state.tasks:
            return "Немає повідомлень, що чекають відповіді"
        lines = ["Чекають відповіді:"]
        now = self.clock()
        for t in self.state.tasks:
            m = self.state.member(t["assignee"])
            left = f", залишилось {max(0, round((t['deadline'] - now) / 60))} хв" if t["deadline"] else ""
            preview = t["text"][:60] + ("…" if len(t["text"]) > 60 else "")
            lines.append(f"#{t['id']} → {m['name'] if m else '?'}{left}: {preview}")
        return "\n".join(lines)

    # ---- відправка / цикл ------------------------------------------------- #

    def send(self, text, mentions=None, attachments=None):
        try:
            return self.api.send(self.queue_send, text, mentions, attachments)
        except (urllib.error.URLError, OSError, ValueError) as e:
            log.error("Не вдалося надіслати повідомлення: %s", e)
            return None

    def timer_loop(self):
        while True:
            try:
                self.check_timeouts()
            except Exception:
                log.exception("Помилка перевірки таймаутів")
            time.sleep(5)

    def run(self):
        log.info("Бот запущено. Джерело: %s, черга: %s, ключові слова: %s",
                 self.cfg["source_group"], self.cfg["queue_group"], self.cfg["keywords"])
        threading.Thread(target=self.timer_loop, daemon=True).start()
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
    parser.add_argument("command", nargs="?", default="run", choices=["run", "groups", "voice-test"],
                        help="run — запустити бота; groups — показати групи бота та їх id; "
                             "voice-test — зберегти приклад голосового в voice-test.mp3")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)

    if args.command == "voice-test":
        phrase = cfg["voice_template"].format(name="Петро", pos=8, total=14)
        mp3 = synthesize_voice(phrase, cfg["voice_lang"])
        if not mp3:
            sys.exit("Не вдалося створити голосове повідомлення")
        with open("voice-test.mp3", "wb") as f:
            f.write(mp3)
        print(f"Збережено voice-test.mp3: «{phrase}»")
        return

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
