"""
Signal-бот: на ключове слово ставить реакцію (емодзі) на повідомлення
і граває звук на цьому ПК (Windows).

Потрібно:
  1. Java 21+ і signal-cli (https://github.com/AsamK/signal-cli/releases)
  2. Прив'язати signal-cli до вашого акаунта:
       signal-cli link -n "ReactionBot"      (покаже tsdevice:// посилання -> QR)
     У телефоні: Signal -> Налаштування -> Прив'язані пристрої -> Додати.
  3. Встановити бібліотеки:  pip install gTTS pycaw comtypes
  4. Створити config.json поруч зі скриптом (див. config.example.json):
       {"account": "+380..."}
  5. Змінити налаштування нижче і запустити:
       python signal_reaction_bot.py
"""

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import winsound

# Момент запуску (мс): повідомлення, отримані раніше, ігноруються
START_MS = int(time.time() * 1000)

# ==================== НАЛАШТУВАННЯ ====================

# Ваш номер у форматі +380... береться з config.json поруч зі скриптом
# (файл не потрапляє в git) або зі змінної середовища SIGNAL_ACCOUNT
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_account():
    try:
        with open(CONFIG_FILE, encoding="utf-8-sig") as f:
            return json.load(f).get("account", "").strip()
    except FileNotFoundError:
        return os.environ.get("SIGNAL_ACCOUNT", "").strip()


ACCOUNT = load_account()

# Повний шлях до signal-cli.bat
SIGNAL_CLI = r"C:\signal-cli\bin\signal-cli.bat"

# ключове слово (нижній регістр) -> емодзі
KEYWORDS = {
    "ждун": "➕",
    "бпла": "➕",
    "тест": "👍",
}

# Слова, що працюють у ВСІХ чатах (навіть якщо ONLY_CHATS обмежує решту слів)
ALL_CHATS_WORDS = {"тест"}

# Що озвучувати українською (голос Google, потрібен інтернет лише
# при першому запуску: mp3 зберігається поруч зі скриптом)
SPEECH_TEXT = "З'явився ждун"

# Свій звуковий файл (.wav) замість голосу; None = використовувати голос
SOUND_FILE = None

# --- Гучність сповіщення ---
# Піднімати системну гучність до максимуму (і вмикати звук) на час сигналу
FORCE_MAX_VOLUME = True
# Скільки разів повторити озвучку
SPEECH_REPEATS = 2
# Короткі різкі гудки перед голосом (0 = без гудків)
BEEPS_BEFORE = 3

# Реагувати і на власні повідомлення? (надіслані з вашого телефону)
REACT_TO_OWN = True

# Обмежити певними чатами (номери +380... або groupId). Порожньо = усі.
# Не стосується слів з ALL_CHATS_WORDS.
ONLY_CHATS = set()

# ======================================================

write_lock = threading.Lock()
request_id = 0


SPEECH_MP3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zhdun_speech.mp3")


def prepare_speech():
    """Один раз генерує mp3 з українською озвучкою."""
    if SOUND_FILE or os.path.exists(SPEECH_MP3):
        return
    try:
        from gtts import gTTS
        gTTS(SPEECH_TEXT, lang="uk").save(SPEECH_MP3)
        print(f"[звук] створено {SPEECH_MP3}")
    except Exception as e:
        print(f"[звук] не вдалося створити озвучку ({e}), буде звичайний сигнал")


def set_max_volume():
    """Максимальна гучність + зняття Mute (потрібно: pip install pycaw comtypes)."""
    try:
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        dev = AudioUtilities.GetSpeakers()
        vol = getattr(dev, "EndpointVolume", None)
        if vol is None:
            iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(iface, POINTER(IAudioEndpointVolume))
        vol.SetMute(0, None)
        vol.SetMasterVolumeLevelScalar(1.0, None)
    except Exception as e:
        print(f"[звук] не вдалося підняти гучність ({e})")


def play_mp3(path, wait=False):
    mci = ctypes.windll.winmm.mciSendStringW
    mci("close zhdun", None, 0, None)
    mci(f'open "{path}" type mpegvideo alias zhdun', None, 0, None)
    mci("setaudio zhdun volume to 1000", None, 0, None)
    mci("play zhdun wait" if wait else "play zhdun", None, 0, None)


def _play_sound_worker():
    try:
        if FORCE_MAX_VOLUME:
            set_max_volume()
        for _ in range(BEEPS_BEFORE):
            winsound.Beep(1800, 180)
        if SOUND_FILE:
            for _ in range(SPEECH_REPEATS):
                winsound.PlaySound(SOUND_FILE, winsound.SND_FILENAME)
        elif os.path.exists(SPEECH_MP3):
            for _ in range(SPEECH_REPEATS):
                play_mp3(SPEECH_MP3, wait=True)
        elif not BEEPS_BEFORE:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception as e:
        print(f"[звук] помилка: {e}")


def play_sound():
    # у окремому потоці, щоб гудки/повтори не блокували читання повідомлень
    threading.Thread(target=_play_sound_worker, daemon=True).start()


def send_rpc(proc, method, params):
    global request_id
    with write_lock:
        request_id += 1
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": request_id}
        proc.stdin.write(json.dumps(payload) + "\n")
        proc.stdin.flush()


# Латинські літери, схожі на українські (a -> а тощо), щоб "БпЛA" з латинською A теж спрацювало
LOOKALIKES = str.maketrans("aeopcxyikmth", "аеорсхуікмтн")


def normalize(text):
    return text.lower().translate(LOOKALIKES).replace("ё", "е")


def find_matches(text):
    """Усі ключові слова, знайдені в тексті: [(слово, емодзі), ...]"""
    text = normalize(text)
    return [(w, e) for w, e in KEYWORDS.items() if normalize(w) in text]


def handle_envelope(proc, env):
    data = env.get("dataMessage")
    is_own = False
    if data is None:
        sent = (env.get("syncMessage") or {}).get("sentMessage")
        if sent and REACT_TO_OWN:
            data, is_own = sent, True
        else:
            return

    text = data.get("message")
    if not text:
        return

    # Ігноруємо старі повідомлення (що прийшли, поки бот був вимкнений)
    msg_ts = env.get("serverReceivedTimestamp") or data.get("timestamp") or 0
    if msg_ts < START_MS:
        return

    matches = find_matches(text)
    if not matches:
        return

    author = ACCOUNT if is_own else (env.get("sourceNumber") or env.get("sourceUuid") or env.get("source"))
    if not author:
        return

    params = {
        "emoji": "",
        "targetAuthor": author,
        "targetTimestamp": data["timestamp"],
    }

    group = (data.get("groupInfo") or {}).get("groupId")
    if group:
        params["groupId"] = group
        chat_id = group
    else:
        target = data.get("destination") if is_own else author
        params["recipient"] = [target or author]
        chat_id = target or author

    # Слово діє, якщо воно "для всіх чатів" або чат дозволений
    allowed = [(w, e) for w, e in matches
               if w in ALL_CHATS_WORDS or not ONLY_CHATS or chat_id in ONLY_CHATS]
    if not allowed:
        return
    word, emoji = allowed[0]
    params["emoji"] = emoji

    print(f"[збіг] '{word}' -> {emoji} | чат: {chat_id} | {text[:60]}")
    send_rpc(proc, "sendReaction", params)
    play_sound()


def main():
    if not ACCOUNT or ACCOUNT.startswith("+380XXX"):
        sys.exit(f'Вкажіть свій номер у {CONFIG_FILE}: {{"account": "+380..."}}')

    prepare_speech()

    proc = subprocess.Popen(
        [SIGNAL_CLI, "-a", ACCOUNT, "jsonRpc"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    print("Бот запущено. Ctrl+C для виходу.")

    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            if msg.get("method") == "receive":
                env = (msg.get("params") or {}).get("envelope")
                if env:
                    handle_envelope(proc, env)
            elif "error" in msg:
                print(f"[помилка signal-cli] {msg['error']}")
    except KeyboardInterrupt:
        pass
    finally:
        # .bat запускає java як дочірній процес: вбиваємо все дерево,
        # інакше старий signal-cli блокує акаунт при наступному запуску
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    print("signal-cli завершив роботу.")


if __name__ == "__main__":
    main()
