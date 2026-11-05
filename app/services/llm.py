"""Answer generation using Groq.

Why Groq?
  * It has a free tier and is extremely fast, which matters for voice: the
    user is waiting in silence while the answer is generated.
  * It serves open models (Qwen, gpt-oss, ...) through an OpenAI-style chat API.
"""

import logging
import re
from typing import Any

from app.core.errors import LLMServiceError
from app.models.schemas import Message

logger = logging.getLogger(__name__)

# Some "reasoning" models (e.g. Qwen) can put their private thinking inside
# <think>...</think> tags before the real answer. That text must never be
# spoken out loud, so we remove it. re.DOTALL lets "." match newlines too.
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMService:
    def __init__(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        max_tokens: int = 300,
        timeout_seconds: float = 30.0,
        client: Any | None = None,
    ) -> None:
        """`client` lets tests pass in a fake Groq client (no network, no API key)."""
        if client is None:
            from groq import Groq

            # max_retries: the SDK automatically retries short network hiccups.
            client = Groq(api_key=api_key, timeout=timeout_seconds, max_retries=2)
        # Typed as Any because it can be the real Groq client or a test fake.
        self._client: Any = client
        self._model = model
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens

    def generate_reply(self, user_text: str, history: list[Message] | None = None) -> str:
        """Ask the LLM to answer `user_text`, given earlier messages for context.

        Raises:
            LLMServiceError: Groq failed or returned an empty answer.
        """
        # The prompt is: system instructions, then past messages, then the new question.
        messages = [Message(role="system", content=self._system_prompt)]
        messages.extend(history or [])
        messages.append(Message(role="user", content=user_text))

        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[m.to_dict() for m in messages],
                max_tokens=self._max_tokens,  # short answers = faster speech
                temperature=0.7,
            )
            raw_reply = completion.choices[0].message.content or ""
            reply = THINK_BLOCK.sub("", raw_reply).strip()
        except Exception as exc:
            # Any Groq problem (bad key, quota, network) ends up here. We log the
            # real reason but do NOT send it to the user - it may contain details
            # about our account or infrastructure.
            logger.error("Groq request failed: %s", exc)
            raise LLMServiceError(
                "The AI service is currently unavailable. Please try again later."
            ) from exc

        if not reply:
            raise LLMServiceError("The AI service returned an empty answer. Please try again.")
        return reply
