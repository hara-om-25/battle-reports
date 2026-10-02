import os
import tempfile
import unittest

import bot


class FakeAPI:
    def __init__(self):
        self.sent = []
        self.ts = 1000

    def send(self, recipient, text, mentions=None, attachments=None):
        self.ts += 1
        self.sent.append({"to": recipient, "text": text, "mentions": mentions,
                          "attachments": attachments, "ts": self.ts})
        return self.ts


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


SOURCE = "c291cmNl"
QUEUE = "cXVldWU="
PEOPLE = [("u1", "Олена"), ("u2", "Петро"), ("u3", "Іван")]


def envelope(group, text="", uuid="u-sender", name="Тарас", number="+380000000001", **extra):
    dm = {"message": text, "groupInfo": {"groupId": group}}
    dm.update(extra)
    return {"envelope": {"source": number, "sourceNumber": number, "sourceUuid": uuid,
                         "sourceName": name, "dataMessage": dm}}


def reaction(ts, emoji, uuid, remove=False):
    return envelope(QUEUE, uuid=uuid, number=None, reaction={
        "emoji": emoji, "targetSentTimestamp": ts, "isRemove": remove})


class BotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = dict(bot.DEFAULT_CONFIG,
                        bot_number="+380999999999",
                        source_group=SOURCE,
                        queue_group=bot.group_send_id(QUEUE),
                        keywords=["приліт", "вибух"],
                        state_file=os.path.join(self.tmp.name, "state.json"))
        self.api = FakeAPI()
        self.clock = Clock()
        self.voices = []
        self.bot = self.make_bot()

    def make_bot(self):
        def tts(text, lang):
            self.voices.append(text)
            return b"mp3"
        return bot.Bot(self.cfg, api=self.api, tts=tts, clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, people=PEOPLE):
        mentions = [{"uuid": u, "name": n} for u, n in people]
        self.bot.handle_envelope(envelope(QUEUE, "/add " + "￼ " * len(people), mentions=mentions))
        self.api.sent.clear()

    def incoming(self, text="Був ПРИЛІТ у місті"):
        self.bot.handle_envelope(envelope(SOURCE, text))
        return self.api.sent[-1]

    def mentioned(self, msg):
        m = msg["mentions"][0]
        utf16 = msg["text"].encode("utf-16-le")
        return m["author"], utf16[m["start"] * 2:(m["start"] + m["length"]) * 2].decode("utf-16-le")

    def order(self):
        return [m["id"] for m in self.bot.state.ordered()]

    # ---- базове ----------------------------------------------------------- #

    def test_group_id_roundtrip(self):
        self.assertEqual(bot.group_internal_id(bot.group_send_id(QUEUE)), QUEUE)

    def test_round_robin_with_mentions(self):
        self.add()
        authors = [self.mentioned(self.incoming())[0] for _ in range(4)]
        self.assertEqual(authors, ["u1", "u2", "u3", "u1"])
        msg = self.api.sent[0]
        self.assertEqual(msg["to"], bot.group_send_id(QUEUE))
        self.assertEqual(self.mentioned(msg)[1], "@Олена")
        self.assertIn("Прийшла черга @Олена 1/3", msg["text"])

    def test_voice_message(self):
        self.add()
        self.incoming()
        self.incoming()
        self.assertEqual(self.voices[-1], "Прийшла черга Петро, 2 з 3")
        self.assertTrue(self.api.sent[-1]["attachments"][0].startswith("data:audio/mpeg;"))
        self.bot.handle_envelope(envelope(QUEUE, "/voice off"))
        self.assertIsNone(self.incoming()["attachments"])

    def test_ignores_messages_without_keyword_and_other_groups(self):
        self.add()
        self.bot.handle_envelope(envelope(SOURCE, "все спокійно"))
        self.bot.handle_envelope(envelope("other", "приліт"))
        self.assertEqual(self.api.sent, [])

    def test_empty_queue_warns(self):
        msg = self.incoming("вибух")
        self.assertIn("Черга порожня", msg["text"])
        self.assertEqual(self.bot.state.tasks, [])

    # ---- реакції ---------------------------------------------------------- #

    def test_accept_closes_task(self):
        self.add()
        msg = self.incoming()
        self.bot.handle_envelope(reaction(msg["ts"], "➕", "u1"))
        self.assertEqual(self.bot.state.tasks, [])
        self.clock.now += 3600
        self.bot.check_timeouts()
        self.assertEqual(len(self.api.sent), 1)

    def test_decline_mode_end(self):
        self.add()
        msg = self.incoming()                       # Олена; черга: Петро, Іван, Олена
        self.bot.handle_envelope(reaction(msg["ts"], "➖️", "u1"))
        re = self.api.sent[-1]
        self.assertEqual(self.mentioned(re), ("u2", "@Петро"))
        self.assertIn("Олена не може", re["text"])
        self.assertIn("ПРИЛІТ", re["text"])
        self.assertEqual(self.order(), ["u3", "u2", "u1"])
        self.assertEqual(self.mentioned(self.incoming())[0], "u3")

    def test_decline_mode_next(self):
        self.add()
        self.bot.handle_envelope(envelope(QUEUE, "/mode next"))
        msg = self.incoming()
        self.bot.handle_envelope(reaction(msg["ts"], "👎", "u1"))
        self.assertEqual(self.mentioned(self.api.sent[-1])[0], "u2")
        self.assertEqual(self.order(), ["u1", "u3", "u2"])
        self.assertEqual(self.mentioned(self.incoming())[0], "u1")

    def test_only_assignee_can_answer(self):
        self.add()
        msg = self.incoming()
        self.bot.handle_envelope(reaction(msg["ts"], "➖", "u2"))
        self.bot.handle_envelope(reaction(msg["ts"], "➖", "u1", remove=True))
        self.assertEqual(len(self.api.sent), 1)
        self.assertEqual(self.bot.state.tasks[0]["assignee"], "u1")

    def test_quote_reply_minus(self):
        self.add()
        msg = self.incoming()
        self.bot.handle_envelope(envelope(QUEUE, "-", uuid="u1", quote={"id": msg["ts"]}))
        self.assertEqual(self.mentioned(self.api.sent[-1])[0], "u2")

    def test_nobody_takes(self):
        self.add(PEOPLE[:2])
        msg = self.incoming()
        self.bot.handle_envelope(reaction(msg["ts"], "➖", "u1"))
        msg = self.api.sent[-1]
        self.bot.handle_envelope(reaction(msg["ts"], "➖", "u2"))
        self.assertIn("Ніхто з черги не взяв", self.api.sent[-1]["text"])
        self.assertEqual(self.bot.state.tasks, [])

    def test_sync_message_from_own_phone(self):
        self.add()
        msg = self.incoming()
        env = reaction(msg["ts"], "➖", "u1")
        env["envelope"]["syncMessage"] = {"sentMessage": env["envelope"].pop("dataMessage")}
        self.bot.handle_envelope(env)
        self.assertEqual(self.mentioned(self.api.sent[-1])[0], "u2")

    # ---- таймаут ---------------------------------------------------------- #

    def test_timeout_passes_to_next(self):
        self.add()
        self.bot.handle_envelope(envelope(QUEUE, "/timeout 2"))
        self.incoming()
        self.clock.now += 119
        self.bot.check_timeouts()
        self.assertEqual(self.mentioned(self.api.sent[-1])[0], "u1")
        self.clock.now += 2
        self.bot.check_timeouts()
        re = self.api.sent[-1]
        self.assertEqual(self.mentioned(re)[0], "u2")
        self.assertIn("Олена не відповів(-ла) за 2 хв", re["text"])

    def test_timeout_zero_disables(self):
        self.add()
        self.bot.handle_envelope(envelope(QUEUE, "/timeout 0"))
        self.incoming()
        self.clock.now += 10 ** 6
        self.bot.check_timeouts()
        self.assertEqual(len(self.api.sent), 2)  # відповідь на /timeout + пересилання

    def test_parse_duration(self):
        self.assertEqual(bot.parse_duration("5"), 5)
        self.assertEqual(bot.parse_duration("30s"), 0.5)
        self.assertEqual(bot.parse_duration("1h"), 60)
        self.assertEqual(bot.parse_duration("1,5"), 1.5)
        self.assertIsNone(bot.parse_duration("abc"))

    # ---- черга та стан ---------------------------------------------------- #

    def test_state_persists_tasks_and_settings(self):
        self.add()
        self.bot.handle_envelope(envelope(QUEUE, "/mode next"))
        msg = self.incoming()
        restored = self.make_bot()
        self.assertEqual(restored.setting("pass_mode"), "next")
        self.assertEqual(restored.state.order, ["u2", "u3", "u1"])
        restored.handle_envelope(reaction(msg["ts"], "➖", "u1"))
        self.assertEqual(self.mentioned(self.api.sent[-1])[0], "u2")

    def test_numbering_is_stable(self):
        self.add()
        self.incoming()
        self.assertIn("1. Петро (2/3)", self.bot.format_queue())

    def test_remove_member(self):
        self.add()
        self.bot.handle_envelope(envelope(QUEUE, "/remove ￼", mentions=[{"uuid": "u2", "name": "Петро"}]))
        self.assertEqual(self.order(), ["u1", "u3"])

    def test_admin_only(self):
        self.bot.admins = {"+380111111111"}
        self.bot.handle_envelope(envelope(QUEUE, "/timeout 3"))
        self.assertIn("адміністраторам", self.api.sent[-1]["text"])
        self.bot.handle_envelope(envelope(QUEUE, "/join"))
        self.assertEqual(self.bot.state.head()["id"], "u-sender")

    def test_old_state_format(self):
        path = self.cfg["state_file"]
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"members": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}], "position": 1}')
        self.assertEqual(bot.State(path).order, ["b", "a"])

    def test_whole_word(self):
        m = bot.KeywordMatcher(["кот"], whole_word=True)
        self.assertEqual(m.find("котлета"), [])
        self.assertEqual(m.find("Кот біжить"), ["Кот"])


if __name__ == "__main__":
    unittest.main()
