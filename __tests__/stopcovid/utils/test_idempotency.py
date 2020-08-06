# import os
# import unittest
#
# from stopcovid.utils.idempotency import IdempotencyChecker
#
#
# class TestIdempotency(unittest.TestCase):
#     def setUp(self) -> None:
#         os.environ["STAGE"] = "test"
#         self.idempotency_checker = IdempotencyChecker(
#             region_name="us-west-2",
#             endpoint_url="http://localhost:9000",
#             aws_access_key_id="fake-key",
#             aws_secret_access_key="fake-secret",
#         )
#         self.idempotency_checker.drop_and_recreate_table()
#
#     def test_idempotency(self):
#         self.assertFalse(self.idempotency_checker.already_processed("idempotency", "realm1"))
#         self.idempotency_checker.record_as_processed("idempotency", "realm1", 5)
#         self.assertTrue(self.idempotency_checker.already_processed("idempotency", "realm1"))
