import os
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX", "documents"))

# Test query with dummy vector (just zeros)
dummy_vector = [0.0] * 384

print("Testing with no filter:")
res1 = index.query(vector=dummy_vector, top_k=2, include_metadata=True)
print(f"Results: {len(res1['matches'])}")
if len(res1['matches']) > 0:
    meta = res1['matches'][0].get('metadata', {})
    print(f"Sample document_id: {meta.get('document_id')} (Type: {type(meta.get('document_id'))})")

print("\nTesting with $in [13]:")
res2 = index.query(vector=dummy_vector, top_k=2, filter={"document_id": {"$in": [13]}}, include_metadata=True)
print(f"Results: {len(res2['matches'])}")

print("\nTesting with $in [13.0]:")
res3 = index.query(vector=dummy_vector, top_k=2, filter={"document_id": {"$in": [13.0]}}, include_metadata=True)
print(f"Results: {len(res3['matches'])}")

print("\nTesting with $eq 13:")
res4 = index.query(vector=dummy_vector, top_k=2, filter={"document_id": {"$eq": 13}}, include_metadata=True)
print(f"Results: {len(res4['matches'])}")
