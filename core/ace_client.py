"""
GEOPulse Ace Client — Geotab Ace AI Query Interface

Wraps the Geotab Ace API for natural-language fleet analytics queries.
Uses the async ask-wait-fetch pattern: create-chat → send-prompt → poll for results.

Usage:
    from core.ace_client import AceClient
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
        self._last_question = ""

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
        path = result.get("path")
        if path and "." in path and path.lower() != "thisserver":
            self.server = path
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

        # Check for API-level errors returned as HTTP 200 with JSON error body
        if "error" in data:
            err = data["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise RuntimeError(f"Geotab Ace API error: {msg}")

        if "result" in data and isinstance(data["result"], dict) and "apiResult" in data["result"]:
            results = data["result"]["apiResult"].get("results", [])
            if not results:
                raise RuntimeError("Ace returned empty results — Ace may not be enabled for this database (check Administration > Beta Features)")
            return results[0]
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

        self._last_question = question  # Store so _poll_results can pass it to _extract_answer
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

                # status can be a dict {"status": "DONE"} or just a string "DONE"
                raw_status = mg.get("status", {})
                if isinstance(raw_status, dict):
                    status = raw_status.get("status", "")
                    status_error = raw_status.get("error", "Unknown error")
                else:
                    status = str(raw_status)
                    status_error = "Unknown error"

                if status == "DONE":
                    return self._extract_answer(mg, question=self._last_question)
                elif status == "FAILED":
                    raise RuntimeError(f"Ace query failed: {status_error}")

                logger.debug(f"Ace poll {attempt+1}/{max_attempts}: status={status}")
            except RuntimeError:
                raise
            except Exception as e:
                logger.warning(f"Ace poll error: {e}")

            time.sleep(interval)

        raise TimeoutError("Ace query timed out after 2.5 minutes")

    def _extract_answer(self, message_group, question=""):
        """Extract answer text, data rows, and reasoning from Ace response."""
        messages = message_group.get("messages", {})

        answer_text = ""
        reasoning = ""
        data_rows = []
        columns = []

        # Message types that belong to the user (not Ace's response) — skip these
        USER_TYPES = {
            "USER", "PROMPT", "HUMAN", "INPUT", "QUERY",
            "user", "prompt", "human", "input", "query",
        }

        # messages can be a dict {id: msg} or a list [msg, ...]
        if isinstance(messages, list):
            msg_iter = list(enumerate(messages))
        elif isinstance(messages, dict):
            msg_iter = list(messages.items())
        else:
            msg_iter = []

        # Log message types at INFO level once so we can see the structure
        type_summary = {
            str(k): msg.get("type", msg.get("role", "?"))
            for k, msg in msg_iter if isinstance(msg, dict)
        }
        logger.info(f"Ace response messages — types: {type_summary}")

        for key, msg in msg_iter:
            if not isinstance(msg, dict):
                continue

            # Skip user / prompt messages — we only want Ace's replies
            msg_type = msg.get("type", msg.get("role", ""))
            if msg_type in USER_TYPES:
                logger.debug(f"Ace message [{key}]: skipping user-type '{msg_type}'")
                continue

            # Collect reasoning
            for field in ("reasoning", "thinking", "explanation"):
                val = msg.get(field)
                if val and isinstance(val, str):
                    reasoning = val
                    break

            # Look for the main answer text — Ace uses different field names
            for field in ("answer", "text", "content", "message_text",
                          "response", "html", "markdown", "summary"):
                val = msg.get(field)
                if val and isinstance(val, str) and not answer_text:
                    # Skip if it's just echoing back the question
                    if question and val.strip() == question.strip():
                        logger.debug(f"Ace message [{key}]: skipping echo of question")
                        continue
                    answer_text = val
                    break

            # Get preview data rows
            preview = msg.get("preview_array", [])
            if preview and isinstance(preview, list):
                data_rows = preview
            cols = msg.get("columns", [])
            if cols and isinstance(cols, list):
                columns = cols

        # If still no answer, fall back to reasoning
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

        if not answer_text:
            # Dump the raw structure at WARNING level so we can identify the field name
            logger.warning(
                "Ace extraction: could not find answer text. "
                "Raw message_group keys: %s | messages sample: %s",
                list(message_group.keys()),
                json.dumps(
                    {k: (list(v.keys()) if isinstance(v, dict) else type(v).__name__)
                     for k, v in (messages.items() if isinstance(messages, dict)
                                  else enumerate(messages))}
                )
            )

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
