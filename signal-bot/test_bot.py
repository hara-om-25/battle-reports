import os
import tempfile
import unittest

import bot


class FakeAPI:
    def __init__(self):
        self.sent = []

    def send(self, recipient, text, mentions=None):
        self.sent.append((recipient, text, mentions))


SOURCE = "c291cmNl"
QUEUE = "cXVldWU="


def envelope(group, text, sender="+380000000001", uuid="u-sender", name="Тарас", mentions=None):
    return {"envelope": {
        "source": sender, "sourceNumber": sender, "sourceUuid": uuid, "sourceName": name,
        "dataMessage": {"message": text, "groupInfo": {"groupId": group},
                        "mentions": mentions or []},
    }}


class BotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cfg = dict(bot.DEFAULT_CONFIG,
                   bot_number="+380999999999",
                   source_group=SOURCE,
                   queue_group=bot.group_send_id(QUEUE),
                   keywords=["приліт", "вибух"],
                   state_file=os.path.join(self.tmp.name, "state.json"))
        self.cfg = cfg
        self.api = FakeAPI()
        self.bot = bot.Bot(cfg, api=self.api)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, *people):
        mentions = [{"uuid": u, "name": n} for u, n in people]
        self.bot.handle_envelope(envelope(QUEUE, "/add " + "￼ " * len(people), mentions=mentions))

    def test_group_id_roundtrip(self):
        self.assertEqual(bot.group_internal_id(bot.group_send_id(QUEUE)), QUEUE)

    def test_round_robin_with_mentions(self):
        self.add(("u1", "Олена"), ("u2", "Петро"))
        self.api.sent.clear()
        for _ in range(3):
            self.bot.handle_envelope(envelope(SOURCE, "Був ПРИЛІТ у місті"))
        authors = [m[0]["author"] for _, _, m in self.api.sent]
        self.assertEqual(authors, ["u1", "u2", "u1"])
        recipient, text, mentions = self.api.sent[0]
        self.assertEqual(recipient, bot.group_send_id(QUEUE))
        start, length = mentions[0]["start"], mentions[0]["length"]
        utf16 = text.encode("utf-16-le")
        self.assertEqual(utf16[start * 2:(start + length) * 2].decode("utf-16-le"), "@Олена")

    def test_ignores_messages_without_keyword_and_other_groups(self):
        self.add(("u1", "Олена"))
        self.api.sent.clear()
        self.bot.handle_envelope(envelope(SOURCE, "все спокійно"))
        self.bot.handle_envelope(envelope("other", "приліт"))
        self.assertEqual(self.api.sent, [])

    def test_empty_queue_warns(self):
        self.bot.handle_envelope(envelope(SOURCE, "вибух"))
        self.assertIn("Черга порожня", self.api.sent[0][1])
        self.assertIsNone(self.api.sent[0][2])

    def test_remove_keeps_order(self):
        self.add(("u1", "A"), ("u2", "B"), ("u3", "C"))
        self.bot.queue.next()  # A отримав, наступний B
        self.bot.queue.remove("u1")
        self.assertEqual(self.bot.queue.peek()["id"], "u2")

    def test_state_persists(self):
        self.add(("u1", "A"), ("u2", "B"))
        self.bot.queue.next()
        restored = bot.Queue(self.cfg["state_file"])
        self.assertEqual(restored.peek()["id"], "u2")

    def test_admin_only(self):
        self.bot.admins = {"+380111111111"}
        self.add(("u1", "A"))
        self.assertIn("адміністраторам", self.api.sent[-1][1])
        self.bot.handle_envelope(envelope(QUEUE, "/join"))
        self.assertEqual(self.bot.queue.peek()["id"], "u-sender")

    def test_whole_word(self):
        m = bot.KeywordMatcher(["кот"], whole_word=True)
        self.assertEqual(m.find("котлета"), [])
        self.assertEqual(m.find("Кот біжить"), ["Кот"])


if __name__ == "__main__":
    unittest.main()
