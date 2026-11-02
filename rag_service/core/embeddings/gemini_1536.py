"""
Custom Gemini Embedding for LlamaIndex that forces gemini-embedding-001 to use 1536 dimensions
By default gemini-embedding-001 returns 3072 dimensions!
"""
from typing import Any, List
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr
from google import genai
from google.genai import types
import os


class Gemini1536Embedding(BaseEmbedding):
    """
    Gemini embedding wrapper that forces gemini-embedding-001 to return 1536 dimensions.
    The default is 3072 dimensions which causes dimension mismatch!
    """
    
    _client: Any = PrivateAttr()
    _model_name: str = PrivateAttr()
    _output_dim: int = PrivateAttr()
    
    def __init__(self, api_key: str = None, **kwargs):
        super().__init__(**kwargs)
        api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY required")
        self._client = genai.Client(api_key=api_key)
        self._model_name = "models/gemini-embedding-001"  # This model has 3072 dims by default!
        self._output_dim = 1536  # Force to 1536 for compatibility
    
    def _get_query_embedding(self, query: str) -> List[float]:
        """Get query embedding with exactly 1536 dimensions."""
        response = self._client.models.embed_content(
            model=self._model_name,
            contents=query,
            config=types.EmbedContentConfig(
                task_type="retrieval_query",
                output_dimensionality=self._output_dim  # CRITICAL: Force 1536!
            )
        )
        return response.embeddings[0].values
    
    def _get_text_embedding(self, text: str) -> List[float]:
        """Get text embedding with exactly 1536 dimensions."""
        response = self._client.models.embed_content(
            model=self._model_name,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="retrieval_document",
                output_dimensionality=self._output_dim  # CRITICAL: Force 1536!
            )
        )
        return response.embeddings[0].values
    
    async def _aget_query_embedding(self, query: str) -> List[float]:
        """Async get query embedding."""
        return self._get_query_embedding(query)
    
    async def _aget_text_embedding(self, text: str) -> List[float]:
        """Async get text embedding."""
        return self._get_text_embedding(text)
    
    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get multiple text embeddings."""
        return [self._get_text_embedding(text) for text in texts]
    
    @classmethod
    def class_name(cls) -> str:
        return "Gemini1536Embedding"
