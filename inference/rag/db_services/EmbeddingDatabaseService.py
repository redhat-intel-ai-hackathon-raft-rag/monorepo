import chromadb
from llmmodel import embedding_pipeline
from gcloud_conf import TaskType


class EmbeddingDatabaseService:
    def __init__(self):
        self.client = chromadb.Client()
        self.collection = self.client.create_collection(name="documents")
        self.embedder = embedding_pipeline

    def add_document(self, document, metadata):
        """Add a document and its embedding to the vector database."""
        embedding = self.embedder(
            [document],
            task_type=TaskType.RETRIEVAL_DOCUMENT)[0].values
        self.collection.add(
            ids=[metadata['id']],
            documents=[document],
            embeddings=embedding,
            metadatas=[metadata]
        )

    def query_similar_documents(self, query, n_results=5):
        """Retrieve similar documents based on the query."""
        query_embedding = self.embedder(
            [query],
            task_type=TaskType.RETRIEVAL_QUERY)[0].values
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=n_results)
        return results['documents'][0], results['metadatas'][0]

if __name__ == '__main__':
    service = EmbeddingDatabaseService()
    service.add_document("Hello world", {"id": "1"})
    service.add_document("Hello world", {"id": "2"})
    service.add_document("Hello world", {"id": "3"})
    service.add_document("Hello world", {"id": "4"})
    service.add_document("Hello world", {"id": "5"})
    print(service.query_similar_documents("Hello world"))