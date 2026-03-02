"""
GEOPulse LLM Provider — Gemini & Ollama Abstraction

Routes all AI text generation through a single interface.
Switch providers via LLM_PROVIDER env var ('gemini' or 'ollama').

Usage:
    from mcp.llm_provider import LLMProvider
    llm = LLMProvider()
    text = llm.generate("Summarize this fleet data", system_prompt="You are a fleet analyst")
"""

import os
import json
import hashlib
import time
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class LLMProvider:
    """Unified interface for Gemini and Ollama LLM backends."""

    def __init__(self, db_cache=None):
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        self.model = os.getenv("LLM_MODEL", "")
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.cache = db_cache  # Optional DuckDBCache instance for response caching
        self._gemini_model = None

        # Set default models per provider
        if not self.model:
            self.model = "gemini-2.0-flash" if self.provider == "gemini" else "llama3.2"

    def _get_gemini_client(self):
        """Lazy-init Gemini client (new google.genai SDK)."""
        if self._gemini_model is None:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set in .env")
            self._gemini_model = genai.Client(api_key=api_key)
        return self._gemini_model

    # Keep legacy name for backward compat
    def _init_gemini(self):
        return self._get_gemini_client()

    def generate(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048):
        """
        Generate text from the configured LLM provider.

        Args:
            prompt: User prompt / input data
            system_prompt: System instructions (persona, rules)
            temperature: Creativity (0.0 = deterministic, 1.0 = creative)
            max_tokens: Maximum response length

        Returns:
            Generated text string
        """
        if self.provider == "gemini":
            return self._generate_gemini(prompt, system_prompt, temperature, max_tokens)
        elif self.provider == "ollama":
            return self._generate_ollama(prompt, system_prompt, temperature, max_tokens)
        else:
            raise ValueError(f"Unknown LLM_PROVIDER: {self.provider}. Use 'gemini' or 'ollama'.")

    def generate_cached(self, prompt, system_prompt=None, cache_key=None,
                        ttl_seconds=3600, temperature=0.7, max_tokens=2048):
        """
        Generate with DuckDB caching. Returns cached response if available and fresh.

        Args:
            cache_key: Unique key for this query. Auto-generated from prompt hash if None.
            ttl_seconds: Cache TTL in seconds (default: 1 hour)
        """
        if cache_key is None:
            cache_key = self._hash_key(prompt, system_prompt)

        # Check cache first
        if self.cache:
            cached = self.cache.get_llm_cache(cache_key, ttl_seconds)
            if cached:
                logger.debug(f"LLM cache hit: {cache_key[:20]}...")
                return cached

        # Generate fresh
        result = self.generate(prompt, system_prompt, temperature, max_tokens)

        # Store in cache
        if self.cache and result:
            self.cache.set_llm_cache(cache_key, result, self.model)

        return result

    def _generate_gemini(self, prompt, system_prompt, temperature, max_tokens):
        """Generate via Google Gemini API (google.genai SDK)."""
        from google.genai import types
        client = self._get_gemini_client()

        contents = prompt
        config = types.GenerateContentConfig(
            system_instruction=system_prompt or "",
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            return response.text
        except Exception as e:
            error_str = str(e)
            # On quota or rate limit, fail immediately — let the caller use fallback
            if "429" in error_str or "quota" in error_str.lower():
                logger.warning(f"Gemini quota hit — using fallback: {error_str[:80]}")
            else:
                logger.error(f"Gemini API error: {e}")
            raise

    def _generate_ollama(self, prompt, system_prompt, temperature, max_tokens):
        """Generate via local Ollama server."""
        import requests

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.ConnectionError:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.ollama_url}. "
                "Start Ollama with: ollama serve"
            )
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise

    def _hash_key(self, prompt, system_prompt):
        """Generate a stable cache key from prompt content."""
        content = f"{self.provider}:{self.model}:{system_prompt or ''}:{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def get_info(self):
        """Return provider info for diagnostics."""
        return {
            "provider": self.provider,
            "model": self.model,
            "ollama_url": self.ollama_url if self.provider == "ollama" else None,
            "cache_enabled": self.cache is not None,
        }


# Quick test when run directly
if __name__ == "__main__":
    llm = LLMProvider()
    info = llm.get_info()
    print(f"Provider: {info['provider']}")
    print(f"Model: {info['model']}")

    try:
        result = llm.generate(
            "Say 'GEOPulse LLM test successful' in exactly those words.",
            system_prompt="You are a helpful assistant. Respond only with the exact text requested."
        )
        print(f"✅ {info['provider'].title()} connected!")
        print(f"   Response: {result.strip()[:100]}")
    except Exception as e:
        print(f"❌ {info['provider'].title()} failed: {e}")
