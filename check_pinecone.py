#!/usr/bin/env python3
from app.services.vectorstore import VectorStoreService

vectorstore = VectorStoreService()
if vectorstore.index:
    stats = vectorstore.index.describe_index_stats()
    print('Pinecone Index Stats:')
    print(f'  Total vectors: {stats.total_vector_count}')
    print(f'  Namespaces: {list(stats.namespaces.keys())}')
    if 'rag' in stats.namespaces:
        print(f'  RAG namespace: {stats.namespaces["rag"].vector_count} vectors')
else:
    print('Pinecone not available')
