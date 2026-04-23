import os
import sys
from dotenv import load_dotenv

def validate():
    print("STEP 1: load .env")
    try:
        load_dotenv()
        print("PASS")
    except Exception as e:
        print(f"FAIL: {e}")
        return

    print("STEP 2: verify PINECONE_API_KEY")
    api_key = os.getenv('PINECONE_API_KEY')
    if api_key:
        print("PASS")
    else:
        print("FAIL: PINECONE_API_KEY is empty")
        return

    print("STEP 3: verify import Pinecone")
    try:
        from pinecone import Pinecone
        print("PASS")
    except ImportError as e:
        print(f"FAIL: {e}")
        return

    print("STEP 4: list index names")
    try:
        pc = Pinecone(api_key=api_key)
        indexes = pc.list_indexes()
        index_names = [idx.name for idx in indexes]
        print(f"PASS (count: {len(index_names)})")
    except Exception as e:
        print(f"FAIL: {e}")
        return

    print("STEP 5: check PINECONE_INDEX")
    target_index = os.getenv('PINECONE_INDEX')
    if not target_index:
        print("FAIL: PINECONE_INDEX env var not set")
    elif target_index in index_names:
        print(f"PASS ({target_index} exists)")
    else:
        print(f"FAIL ({target_index} not found in {index_names})")

    print("STEP 6: VectorStoreService._ensure_connected()")
    try:
        # Add current directory to path for imports
        sys.path.append(os.getcwd())
        from app.services.vectorstore import VectorStoreService
        vss = VectorStoreService()
        vss._ensure_connected()
        print("PASS")
    except Exception as e:
        print(f"FAIL: {e}")

    print("RESULT: Completed validation")

if __name__ == '__main__':
    validate()
