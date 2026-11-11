import unittest

from action_store import claim_action, release_action, session_lock


class ActionStoreTests(unittest.TestCase):
    def test_first_claim_succeeds(self):
        self.assertTrue(claim_action("s1", "a1"))

    def test_duplicate_claim_rejected(self):
        claim_action("s1", "a2")
        self.assertFalse(claim_action("s1", "a2"))

    def test_same_action_different_session_allowed(self):
        claim_action("s1", "a3")
        self.assertTrue(claim_action("s2", "a3"))

    def test_empty_action_id_always_allowed(self):
        self.assertTrue(claim_action("s1", ""))
        self.assertTrue(claim_action("s1", ""))

    def test_failed_action_can_retry(self):
        claim_action("s1", "a4")
        release_action("s1", "a4", completed=False)
        self.assertTrue(claim_action("s1", "a4"))

    def test_session_lock_is_stable(self):
        self.assertIs(session_lock("s1"), session_lock("s1"))
        self.assertIsNot(session_lock("s1"), session_lock("s2"))


if __name__ == "__main__":
    unittest.main()
