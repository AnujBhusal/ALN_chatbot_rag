import pytest

from app.services.retrieval import group_results_by_document


def make_result(doc_id, chunk_id, score, text, title="Doc"):
    return {
        "id": f"chunk_{chunk_id}",
        "score": score,
        "metadata": {
            "document_id": doc_id,
            "chunk_id": chunk_id,
            "text": text,
            "title": title,
            "document_type": "general",
        },
    }


def test_grouping_prefers_high_top_score_over_many_medium():
    # Doc A: one very high-scoring chunk
    r1 = make_result(1, 101, 0.95, "Critical finding in ALN Annual Report", title="ALN Annual Report 2024")

    # Doc B: many medium-scoring chunks
    rs = [make_result(2, 200 + i, 0.30, f"Medium content B {i}", title="Meeting Notes") for i in range(6)]

    # Interleave to simulate arbitrary ordering from vector DB
    results = []
    results.extend(rs[:3])
    results.append(r1)
    results.extend(rs[3:])

    grouped = group_results_by_document(results)

    # The first grouped document should be Doc A (id=1) because its top-k avg is higher
    assert grouped, "Expected non-empty grouping"
    first_doc = grouped[0]
    assert first_doc.get("document_id") in (1, "1"), f"Expected doc 1 first, got {first_doc.get('document_id')}"


def test_deduplicate_and_top_k_average():
    # Doc C: duplicate chunk entries should be deduped
    dup1 = make_result(3, 301, 0.8, "Duplicate chunk text", title="Report C")
    dup2 = make_result(3, 301, 0.8, "Duplicate chunk text", title="Report C")

    # Doc D: two high chunks
    d1 = make_result(4, 401, 0.7, "Top chunk 1", title="Report D")
    d2 = make_result(4, 402, 0.6, "Top chunk 2", title="Report D")

    results = [dup1, dup2, d1, d2]
    grouped = group_results_by_document(results)

    # Ensure duplicates removed: doc 3 should have 1 source only
    doc3 = next((g for g in grouped if g.get("document_id") in (3, "3")), None)
    assert doc3 is not None
    assert len(doc3.get("sources", [])) == 1

    # Ensure doc 4 exists and has top sources sorted
    doc4 = next((g for g in grouped if g.get("document_id") in (4, "4")), None)
    assert doc4 is not None
    sources = doc4.get("sources", [])
    assert sources[0]["score"] >= sources[1]["score"]
