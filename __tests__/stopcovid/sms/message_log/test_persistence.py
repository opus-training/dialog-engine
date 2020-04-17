import unittest

from stopcovid import db
from stopcovid.sms.message_log.persistence import MessageRepository
from sqlalchemy.exc import IntegrityError

from __tests__.utils.time import get_timestamp_min_in_past


class TestMessageRepository(unittest.TestCase):
    def setUp(self):
        self.repo = MessageRepository(db.get_test_sqlalchemy_engine)
        self.repo.drop_and_recreate_tables_testing_only()

    def test_save_messages(self):
        messages = [
            {
                "twilio_message_id": "twi-1",
                "from_number": "9998883333",
                "to_number": "1113334444",
                "body": "Good morning",
                "status": "delivered",
                "created_at": get_timestamp_min_in_past(5),
            },
            {
                "twilio_message_id": "twi-2",
                "from_number": "9998883333",
                "to_number": "1113334444",
                "body": "Time for a new drill",
                "status": "sent",
                "created_at": get_timestamp_min_in_past(15),
            },
        ]
        self.repo.upsert_messages(messages)
        persisted_messages = self.repo._get_messages()
        self.assertEqual(len(messages), len(persisted_messages))
        for obj, persisted in zip(messages, persisted_messages):
            self.assertNotEqual(obj, persisted)
            self.assertIsNotNone(persisted.id)
            self.assertEqual(obj["twilio_message_id"], persisted.twilio_message_id)
            self.assertEqual(obj["from_number"], persisted.from_number)
            self.assertEqual(obj["to_number"], persisted.to_number)
            self.assertEqual(obj["body"], persisted.body)
            self.assertEqual(obj["status"], persisted.status)
            self.assertEqual(obj["created_at"], persisted.created_at)

    def test_update_message(self):
        messages = [
            {
                "twilio_message_id": "twi-1",
                "from_number": "9998883333",
                "to_number": "1113334444",
                "body": "Good morning",
                "status": "sent",
            },
            {
                "twilio_message_id": "twi-1",
                "from_number": "9998883333",
                "to_number": "1113334444",
                "body": "Good morning",
                "status": "delivered",
            },
        ]

        self.repo.upsert_messages(messages)
        persisted_messages = self.repo._get_messages()
        self.assertEqual(len(persisted_messages), 1)
        self.assertEqual(persisted_messages[0]["twilio_message_id"], "twi-1")
        self.assertEqual(persisted_messages[0]["from_number"], "9998883333")
        self.assertEqual(persisted_messages[0]["to_number"], "1113334444")
        self.assertEqual(persisted_messages[0]["body"], "Good morning")
        # status is updated from second upsert
        self.assertEqual(persisted_messages[0]["status"], "delivered")

    def test_update_message_out_of_order(self):
        messages = [
            {
                "twilio_message_id": "twi-1",
                "from_number": "9998883333",
                "to_number": "1113334444",
                "status": "delivered",
            },
            {
                "twilio_message_id": "twi-1",
                "from_number": "9998883333",
                "to_number": "1113334444",
                "body": "Good morning",
                "status": "sent",
                "created_at": get_timestamp_min_in_past(10),
            },
        ]

        self.repo.upsert_messages(messages)
        persisted_messages = self.repo._get_messages()
        self.assertEqual(len(persisted_messages), 1)
        self.assertEqual(persisted_messages[0]["twilio_message_id"], "twi-1")
        self.assertEqual(persisted_messages[0]["from_number"], "9998883333")
        self.assertEqual(persisted_messages[0]["to_number"], "1113334444")
        self.assertEqual(persisted_messages[0]["body"], "Good morning")
        self.assertEqual(persisted_messages[0]["status"], "delivered")
        self.assertEqual(persisted_messages[0]["created_at"], messages[1]["created_at"])

    def test_upsert_with_incomplete_data_on_insert(self):
        messages = [
            {"twilio_message_id": "twi-1", "to_number": "1113334444", "body": "Good morning"}
        ]

        with self.assertRaises(IntegrityError):
            self.repo.upsert_messages(messages)
