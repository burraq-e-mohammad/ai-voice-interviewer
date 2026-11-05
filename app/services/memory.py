"""Short-term conversation memory.

Why have memory at all?
  Without it, every question is answered in isolation, so a follow-up like
  "and how tall is it?" makes no sense to the bot. Keeping the last few
  exchanges fixes that.

Why keep it this simple?
  * It is in RAM only - no database to install. Restarting the server clears it.
  * Each session keeps only the last N exchanges (a `deque` with `maxlen`
    drops the oldest automatically), which also keeps LLM prompts small.
  * At most `max_sessions` sessions are stored; the least recently used one is
    evicted. This stops a client from filling RAM with fake session IDs.
  * Memory is optional: requests without a session_id are stateless.
"""

import threading
from collections import OrderedDict, deque

from app.models.schemas import Message


class ConversationMemory:
    def __init__(self, max_turns: int, max_sessions: int) -> None:
        # One "turn" = a user message + an assistant reply = 2 messages.
        self._max_messages = max_turns * 2
        self._max_sessions = max_sessions
        # OrderedDict remembers insertion order, which we use as "least recently used" order.
        self._sessions: OrderedDict[str, deque[Message]] = OrderedDict()
        self._lock = threading.Lock()

    def get_history(self, session_id: str) -> list[Message]:
        """Return a copy of the session's past messages (oldest first)."""
        with self._lock:
            history = self._sessions.get(session_id)
            return list(history) if history else []

    def add_exchange(self, session_id: str, user_text: str, assistant_text: str) -> None:
        """Store one user question and the bot's answer."""
        if self._max_messages == 0:
            return  # memory disabled via MAX_HISTORY_TURNS=0

        with self._lock:
            history = self._sessions.get(session_id)
            if history is None:
                history = deque(maxlen=self._max_messages)
                self._sessions[session_id] = history
            history.append(Message(role="user", content=user_text))
            history.append(Message(role="assistant", content=assistant_text))

            # Mark this session as most recently used...
            self._sessions.move_to_end(session_id)
            # ...and evict the least recently used ones if we have too many.
            while len(self._sessions) > self._max_sessions:
                self._sessions.popitem(last=False)
