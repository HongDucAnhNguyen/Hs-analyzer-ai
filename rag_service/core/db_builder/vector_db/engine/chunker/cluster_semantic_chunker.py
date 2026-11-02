import asyncio
import os
from typing import Any, Dict, List
from uuid import uuid4

import numpy as np

from ..embedder.embedder import Embedder
from ..embedder.gemini_embedder import GeminiEmbedder
from .recursive_token_chunker import RecursiveTokenChunker


def simple_token_count(text: str) -> int:
    """Simple token count approximation"""
    return len(text.split())

class ClusterSemanticChunker():
    def __init__(self, max_chunk_size=512, min_chunk_size=256):
        self.splitter = RecursiveTokenChunker(
            chunk_size=min_chunk_size,
            chunk_overlap=0,
            length_function=simple_token_count,
        )
        
        self._chunk_size = max_chunk_size
        self.max_cluster = max_chunk_size//min_chunk_size
        
        # Auto-detect embedder based on available API keys
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        
        if openai_key:
            print("🔧 Using OpenAI embedder for chunking")
            self.embedder = Embedder()
        elif gemini_key:
            print("🔧 Using Gemini embedder for chunking")
            self.embedder = GeminiEmbedder()
        else:
            raise ValueError("No API key found! Set OPENAI_API_KEY or GEMINI_API_KEY")

        
    def _get_similarity_matrix(self, sentences):
        BATCH_SIZE = 500
        N = len(sentences)
        embedding_matrix = None

        for i in range(0, N, BATCH_SIZE):
            batch_sentences = sentences[i:i+BATCH_SIZE]
            embeddings = self.embedder.get_embeddings(batch_sentences)

            # Convert embeddings list of lists to numpy array
            batch_embedding_matrix = np.array(embeddings)

            # Append the batch embedding matrix to the main embedding matrix
            if embedding_matrix is None:
                embedding_matrix = batch_embedding_matrix
            else:
                embedding_matrix = np.concatenate((embedding_matrix, batch_embedding_matrix), axis=0)

        similarity_matrix = np.dot(embedding_matrix, embedding_matrix.T)

        return similarity_matrix

    async def _aget_similarity_matrix(self, sentences):
        BATCH_SIZE = 500
        N = len(sentences)
        embedding_matrix = None

        for i in range(0, N, BATCH_SIZE):
            batch_sentences = sentences[i:i+BATCH_SIZE]
            embeddings = await self.embedder.aget_embeddings(batch_sentences)

            # Convert embeddings list of lists to numpy array
            batch_embedding_matrix = np.array(embeddings)

            # Append the batch embedding matrix to the main embedding matrix
            if embedding_matrix is None:
                embedding_matrix = batch_embedding_matrix
            else:
                embedding_matrix = np.concatenate((embedding_matrix, batch_embedding_matrix), axis=0)

        similarity_matrix = np.dot(embedding_matrix, embedding_matrix.T)

        return similarity_matrix

    def _calculate_reward(self, matrix, start, end):
        sub_matrix = matrix[start:end+1, start:end+1]
        return np.sum(sub_matrix)

    def _optimal_segmentation(self, matrix, max_cluster_size, window_size=3):
        mean_value = np.mean(matrix[np.triu_indices(matrix.shape[0], k=1)])
        matrix = matrix - mean_value  # Normalize the matrix
        np.fill_diagonal(matrix, 0)  # Set diagonal to 1 to avoid trivial solutions

        n = matrix.shape[0]
        dp = np.zeros(n)
        segmentation = np.zeros(n, dtype=int)

        for i in range(n):
            for size in range(1, max_cluster_size + 1):
                if i - size + 1 >= 0:
                    # local_density = calculate_local_density(matrix, i, window_size)
                    reward = self._calculate_reward(matrix, i - size + 1, i)
                    # Adjust reward based on local density
                    adjusted_reward = reward
                    if i - size >= 0:
                        adjusted_reward += dp[i - size]
                    if adjusted_reward > dp[i]:
                        dp[i] = adjusted_reward
                        segmentation[i] = i - size + 1

        clusters = []
        i = n - 1
        while i >= 0:
            start = segmentation[i]
            clusters.append((start, i))
            i = start - 1

        clusters.reverse()
        return clusters
    

    async def achunk(self, document: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = document.get('vietnamese_content') or document.get('english_content') or document.get('french_content', "")
        sentences = self.splitter.split_text(text)

        similarity_matrix = self._get_similarity_matrix(sentences)
        clusters = self._optimal_segmentation(similarity_matrix, max_cluster_size=self.max_cluster)
        pre_chunks: List[Dict[str, Any]] = []
        cum_count = 0
        for start, end in clusters:
            chunk_text = ' '.join(sentences[start:end+1])
            if not chunk_text:
                continue
            next_cum_count = cum_count + len(chunk_text)
            pre_chunks.append({
                "id": uuid4().hex,
                "text": chunk_text,
            })
            cum_count = next_cum_count

        if not pre_chunks:
            return []
        concurrency = getattr(self, "embed_concurrency", 5)
        sem = asyncio.Semaphore(concurrency)

        async def _embed_one(txt: str):
            async with sem:
                return await self.embedder.aget_embedding(txt)

        tasks = [asyncio.create_task(_embed_one(c["text"])) for c in pre_chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        chunks: List[Dict[str, Any]] = []
        for c, emb in zip(pre_chunks, results):
            if isinstance(emb, Exception):
                continue
            if emb is None:
                continue
            c_out = {
                "id": c["id"],
                "text": c["text"],
                "embedding_vector": emb,
                "code": document.get("code", []),
                "vietnamese_content": document.get("vietnamese_content", ""),
                "english_content": document.get("english_content", ""),
                "french_content": document.get("french_content", ""),
                "images": document.get("images", []),
                "pages": document.get("pages", []),
                "chapter_vi": document.get("chapter_vi", ""),
                "chapter_en": document.get("chapter_en", ""),
            }
            chunks.append(c_out)

        return chunks
    

    