"""
GEOPulse Ace Client — Geotab Ace AI Query Interface

Wraps the Geotab Ace API for natural-language fleet analytics queries.
Uses the async ask-wait-fetch pattern: create-chat → send-prompt → poll for results.

Usage:
    from mcp.ace_client import AceClient
    ace = AceClient()
    result = ace.query("Which vehicles drove the most last week?")
    # Returns: {"answer": "...", "data": [...], "reasoning": "..."}
"""

import os
import time
import json
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class AceClient:
    """Geotab Ace AI query client with create-chat → send-prompt → poll pattern."""

    def __init__(self, db_cache=None):
        self.server = os.getenv("GEOTAB_SERVER", "my.geotab.com")
        self.database = os.getenv("GEOTAB_DATABASE", "")
        self.username = os.getenv("GEOTAB_USERNAME", "")
        self.password = os.getenv("GEOTAB_PASSWORD", "")
        self.cache = db_cache
        self._credentials = None
        self._chat_id = None

    def _authenticate(self):
        """Authenticate with Geotab and store credentials."""
        if self._credentials:
            return self._credentials

        url = f"https://{self.server}/apiv1"
        resp = requests.post(url, json={
            "method": "Authenticate",
            "params": {
                "database": self.database,
                "userName": self.username,
                "password": self.password,
            }
        }, timeout=30)
        resp.raise_for_status()
        result = resp.json().get("result")
        if not result or "credentials" not in result:
            raise ValueError("Geotab authentication failed — check credentials")
        self._credentials = result["credentials"]
        # Update server in case of redirect
        if result.get("path"):
            self.server = result["path"]
        return self._credentials

    def _call_ace(self, function_name, function_params=None):
        """Make a GetAceResults call to the Geotab Ace API."""
        creds = self._authenticate()
        url = f"https://{self.server}/apiv1"
        payload = {
            "method": "GetAceResults",
            "params": {
                "credentials": creds,
                "serviceName": "dna-planet-orchestration",
                "functionName": function_name,
                "customerData": True,
                "functionParameters": function_params or {},
            }
        }
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        if "result" in data and "apiResult" in data["result"]:
            results = data["result"]["apiResult"].get("results", [])
            return results[0] if results else {}
        return data.get("result", {})

    def _create_chat(self):
        """Create a new Ace chat session. Retries up to 3 times."""
        for attempt in range(3):
            try:
                result = self._call_ace("create-chat", {})
                chat_id = result.get("chat_id")
                if chat_id:
                    self._chat_id = chat_id
                    logger.info(f"Ace chat created: {chat_id}")
                    return chat_id
            except Exception as e:
                logger.warning(f"create-chat attempt {attempt+1} failed: {e}")
            time.sleep(3)
        raise ConnectionError("Failed to create Ace chat after 3 attempts")

    def _send_prompt(self, question):
        """Send a question to the Ace chat and return message_group_id."""
        if not self._chat_id:
            self._create_chat()

        result = self._call_ace("send-prompt", {
            "chat_id": self._chat_id,
            "prompt": question,
        })
        mg_id = result.get("message_group_id") or \
                (result.get("message_group", {}) or {}).get("id")
        if not mg_id:
            raise ValueError("No message_group_id in Ace response")
        return mg_id

    def _poll_results(self, mg_id, max_attempts=30, interval=5):
        """Poll get-message-group until status is DONE or FAILED."""
        time.sleep(8)  # Initial delay per Ace rate limits

        for attempt in range(max_attempts):
            try:
                result = self._call_ace("get-message-group", {
                    "chat_id": self._chat_id,
                    "message_group_id": mg_id,
                })
                mg = result.get("message_group", {})
                status = (mg.get("status", {}) or {}).get("status", "")

                if status == "DONE":
                    return self._extract_answer(mg)
                elif status == "FAILED":
                    error = (mg.get("status", {}) or {}).get("error", "Unknown error")
                    raise RuntimeError(f"Ace query failed: {error}")

                logger.debug(f"Ace poll {attempt+1}/{max_attempts}: status={status}")
            except RuntimeError:
                raise
            except Exception as e:
                logger.warning(f"Ace poll error: {e}")

            time.sleep(interval)

        raise TimeoutError("Ace query timed out after 2.5 minutes")

    def _extract_answer(self, message_group):
        """Extract answer text, data rows, and reasoning from Ace response."""
        messages = message_group.get("messages", {})

        answer_text = ""
        reasoning = ""
        data_rows = []
        columns = []

        for key, msg in messages.items():
            if isinstance(msg, dict):
                # Get reasoning/explanation
                if msg.get("reasoning"):
                    reasoning = msg["reasoning"]
                if msg.get("answer"):
                    answer_text = msg["answer"]

                # Get preview data rows
                preview = msg.get("preview_array", [])
                if preview:
                    data_rows = preview
                cols = msg.get("columns", [])
                if cols:
                    columns = cols

                # Build answer text from reasoning if not explicit
                if not answer_text and reasoning:
                    answer_text = reasoning

        # Format data into readable text if we have rows but no text answer
        if data_rows and not answer_text:
            if columns:
                header = " | ".join(str(c) for c in columns)
                rows_text = "\n".join(
                    " | ".join(str(v) for v in row) for row in data_rows[:10]
                )
                answer_text = f"{header}\n{rows_text}"
            else:
                answer_text = json.dumps(data_rows[:10], indent=2)

        return {
            "answer": answer_text or "Ace returned no results for this query.",
            "data": data_rows[:10],
            "columns": columns,
            "reasoning": reasoning,
        }

    def query(self, question):
        """
        Ask a natural-language question to Geotab Ace.

        Args:
            question: Natural language fleet question

        Returns:
            dict with keys: answer, data, columns, reasoning
        """
        # Check cache first
        if self.cache:
            import hashlib
            cache_key = f"ace_{hashlib.sha256(question.encode()).hexdigest()[:24]}"
            cached = self.cache.get_llm_cache(cache_key, ttl_seconds=1800)
            if cached:
                logger.info("Ace cache hit")
                return json.loads(cached)

        try:
            mg_id = self._send_prompt(question)
            result = self._poll_results(mg_id)

            # Cache result
            if self.cache:
                self.cache.set_llm_cache(cache_key, json.dumps(result), "ace")

            return result
        except Exception as e:
            logger.error(f"Ace query failed: {e}")
            raise

    def is_available(self):
        """Check if Ace is reachable (try creating a chat)."""
        try:
            self._create_chat()
            return True
        except Exception:
            return False

    def get_info(self):
        """Return Ace client info for diagnostics."""
        return {
            "server": self.server,
            "database": self.database,
            "has_chat": self._chat_id is not None,
            "cache_enabled": self.cache is not None,
        }


# Quick test when run directly
if __name__ == "__main__":
    ace = AceClient()
    print(f"Server: {ace.server}")
    print(f"Database: {ace.database}")

    try:
        print("Testing Ace connection...")
        result = ace.query("How many vehicles are in the fleet?")
        print(f"✅ Ace connected!")
        print(f"   Answer: {result['answer'][:200]}")
        if result['data']:
            print(f"   Data rows: {len(result['data'])}")
    except Exception as e:
        print(f"❌ Ace failed: {e}")
