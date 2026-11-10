"""Session memory tracking candidate profiles, conversation turns, and dialogue history."""

import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field

from app.models.schemas import CandidateProfile, Message


@dataclass
class SessionData:
    """State storage for a single active interview session."""

    profile: CandidateProfile
    turn_count: int = 1
    history: deque[Message] = field(default_factory=lambda: deque(maxlen=60))
    is_complete: bool = False


class ConversationMemory:
    """Thread-safe in-memory session manager with LRU eviction."""

    def __init__(self, max_turns: int, max_sessions: int = 1000) -> None:
        self._max_turns = max_turns
        self._max_sessions = max_sessions
        self._sessions: OrderedDict[str, SessionData] = OrderedDict()
        self._lock = threading.Lock()

    def start_session(self, session_id: str, profile: CandidateProfile) -> SessionData:
        """Initialize or reset an interview session with a candidate profile."""
        with self._lock:
            session = SessionData(profile=profile, turn_count=1)
            self._sessions[session_id] = session
            self._sessions.move_to_end(session_id)
            self._evict_oldest()
            return session

    def get_session(self, session_id: str) -> SessionData | None:
        """Retrieve an active session by its ID."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                self._sessions.move_to_end(session_id)
            return session

    def get_history(self, session_id: str) -> list[Message]:
        """Return the past messages for a given session."""
        with self._lock:
            session = self._sessions.get(session_id)
            return list(session.history) if session else []

    def get_profile(self, session_id: str) -> CandidateProfile:
        """Return the candidate profile for the session (or default if not found)."""
        with self._lock:
            session = self._sessions.get(session_id)
            return session.profile if session else CandidateProfile()

    def get_turn(self, session_id: str) -> int:
        """Return the current turn number for this session."""
        with self._lock:
            session = self._sessions.get(session_id)
            return session.turn_count if session else 1

    def record_exchange(self, session_id: str, user_text: str, assistant_text: str) -> tuple[int, bool]:
        """Record an interview turn (candidate answer + interviewer question) and advance turn."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = SessionData(profile=CandidateProfile(), turn_count=1)
                self._sessions[session_id] = session

            session.history.append(Message(role="user", content=user_text))
            session.history.append(Message(role="assistant", content=assistant_text))
            session.turn_count += 1
            if session.turn_count > self._max_turns:
                session.is_complete = True

            self._sessions.move_to_end(session_id)
            self._evict_oldest()
            return session.turn_count, session.is_complete

    def record_interviewer_opening(self, session_id: str, opening_text: str) -> None:
        """Record the initial opening statement/question from the interviewer."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.history.append(Message(role="assistant", content=opening_text))

    def _evict_oldest(self) -> None:
        while len(self._sessions) > self._max_sessions:
            self._sessions.popitem(last=False)
