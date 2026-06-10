"""
Datadex — ChromaDB Vector Store

Manages vector storage and semantic search using ChromaDB.
Uses ChromaDB's built-in default embedding function (all-MiniLM-L6-v2).
"""

import os
import uuid
from typing import List, Optional

import chromadb
from chromadb.api.types import EmbeddingFunction


class ChromaStore:
    """Vector store wrapper around ChromaDB for document chunk storage and search."""

    def __init__(self, persist_directory: str):
        """Initialize ChromaDB client with persistent storage.

        Args:
            persist_directory: Directory path for ChromaDB persistent storage
        """
        os.makedirs(persist_directory, exist_ok=True)
        self.client = chromadb.PersistentClient(path=persist_directory)

    def _collection_name(self, workspace: str) -> str:
        return f"datadex_{workspace}"

    def get_or_create_collection(self, workspace: str):
        """Get or create a ChromaDB collection for the given workspace."""
        name = self._collection_name(workspace)
        return self.client.get_or_create_collection(name=name)

    def delete_collection(self, workspace: str):
        """Delete a workspace collection (for re-indexing)."""
        name = self._collection_name(workspace)
        try:
            self.client.delete_collection(name)
        except (ValueError, chromadb.errors.NotFoundError):
            pass  # Collection doesn't exist

    def add_chunks(
        self,
        workspace: str,
        chunks: list,
        texts: List[str],
        metadatas: Optional[List[dict]] = None,
    ):
        """Add document chunks to the vector store.

        Args:
            workspace: Workspace name
            chunks: List of Chunk objects (from markdown_parser)
            texts: List of text strings to embed
            metadatas: Optional list of metadata dicts
        """
        collection = self.get_or_create_collection(workspace)
        ids = [str(uuid.uuid4()) for _ in texts]
        metas = metadatas or [{} for _ in texts]

        batch_size = 5000
        for i in range(0, len(texts), batch_size):
            collection.add(
                documents=texts[i:i + batch_size],
                metadatas=metas[i:i + batch_size],
                ids=ids[i:i + batch_size],
            )
        return ids

    def search(
        self,
        workspace: str,
        query: str,
        top_k: int = 5,
        metadata_filter: Optional[dict] = None,
    ) -> List[dict]:
        """Search document chunks by semantic similarity.

        Args:
            workspace: Workspace name to search in
            query: Natural language query string
            top_k: Number of results to return
            metadata_filter: Optional metadata filter dict

        Returns:
            List of result dicts with 'document', 'metadata', and 'distance' keys
        """
        collection = self.get_or_create_collection(workspace)

        # Build ChromaDB where filter
        where = None
        if metadata_filter:
            where = metadata_filter

        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )

        output = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                output.append({
                    "document": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                })

        return output

    def count(self, workspace: str) -> int:
        """Count chunks in a workspace collection."""
        collection = self.get_or_create_collection(workspace)
        return collection.count()
