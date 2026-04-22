import unittest

from app.services.retrieval import build_source_items


class RetrievalTests(unittest.TestCase):
    def test_grouped_sources_include_document_id(self):
        results = [
            {
                "id": 1,
                "metadata": {
                    "document_id": 7,
                    "title": "Doc A",
                    "document_type": "donor_proposal",
                    "year": 2024,
                    "text": "First chunk",
                },
            },
            {
                "id": 2,
                "metadata": {
                    "document_id": 7,
                    "title": "Doc A",
                    "document_type": "donor_proposal",
                    "year": 2024,
                    "text": "Second chunk",
                },
            },
        ]

        sources = build_source_items(results)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["document_id"], 7)
        self.assertEqual(sources[0]["type"], "donor_proposal")


if __name__ == "__main__":
    unittest.main()
