import unittest

from app.services.intent import detect_intent, can_access_document_type


class IntentTests(unittest.TestCase):
    def test_detect_donor_intent(self):
        intent = detect_intent("What are key commitments in donor proposals for 2023?")
        self.assertEqual(intent.document_type, "donor_proposal")
        self.assertTrue(intent.is_summary)
        self.assertEqual(intent.year, 2023)

    def test_staff_restricted_from_internal_policy(self):
        self.assertFalse(can_access_document_type("staff", "internal_policy"))
        self.assertTrue(can_access_document_type("admin", "internal_policy"))


if __name__ == "__main__":
    unittest.main()
