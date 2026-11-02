"""
Gemini Embedder - Compatible with the existing Embedder interface
"""
import logging
import os
from typing import List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_random_exponential

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("knowledge_base")
load_dotenv()


class GeminiEmbedder:
    """
    GeminiEmbedder wraps Google Gemini embeddings with retry logic.
    Compatible interface with OpenAI Embedder.
    """
    def __init__(self,
                 api_key: Optional[str] = None,
                 model: str = "gemini-embedding-001",
                 dimensions: int = 1536,
                 max_retries: int = 6,
                 backoff_min: float = 1,
                 backoff_max: float = 20):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable or api_key argument must be set")
        
        # Initialize Gemini client
        self.client = genai.Client(api_key=self.api_key)
        self.model = model
        self.dimensions = dimensions
        
        # Configure retry decorator
        self._retry_decorator = retry(
            wait=wait_random_exponential(min=backoff_min, max=backoff_max),
            stop=stop_after_attempt(max_retries)
        )

    def get_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Returns embedding vector for a single text.
        """
        _model = model or self.model

        @self._retry_decorator
        def _call_api(_text: str, _model: str) -> List[float]:
            try:
                response = self.client.models.embed_content(
                    model=_model,
                    contents=_text,
                    config=types.EmbedContentConfig(
                        output_dimensionality=self.dimensions
                    )
                )
                return response.embeddings[0].values
            except Exception as e:
                log.error(f"Error while embedding text with Gemini: {e}", exc_info=True)
                raise

        return _call_api(text, _model)
    
    def get_embeddings(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        """
        Returns embedding vectors for a list of texts.
        """
        _model = model or self.model

        @self._retry_decorator
        def _call_api(_texts: List[str], _model: str) -> List[List[float]]:
            try:
                # Gemini supports batch embedding
                embeddings = []
                for text in _texts:
                    response = self.client.models.embed_content(
                        model=_model,
                        contents=text,
                        config=types.EmbedContentConfig(
                            output_dimensionality=self.dimensions
                        )
                    )
                    embeddings.append(response.embeddings[0].values)
                return embeddings
            except Exception as e:
                log.error(f"Error while embedding texts with Gemini: {e}", exc_info=True)
                raise

        return _call_api(texts, _model)

    async def aget_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Asynchronously returns embedding vector for a single text.
        Note: Google genai SDK doesn't have async support yet, so we use sync
        """
        return self.get_embedding(text, model)

    async def aget_embeddings(self, texts: List[str], model: Optional[str] = None) -> List[List[float]]:
        """
        Asynchronously returns embedding vectors for a list of texts.
        Note: Google genai SDK doesn't have async support yet, so we use sync
        """
        return self.get_embeddings(texts, model)


# Example usage
if __name__ == '__main__':
    embedder = GeminiEmbedder()
    text = "Your text goes here"
    vec = embedder.get_embedding(text)
    print(f"Embedding dimension: {len(vec)}")
    print(f"Embedding vector: {vec[:10]}...")  # Print first 10 dimensions for brevity
