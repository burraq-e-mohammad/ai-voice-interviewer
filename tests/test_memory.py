"""Unit tests for the in-memory interview session manager."""

from app.models.schemas import CandidateProfile
from app.services.memory import ConversationMemory


def test_new_session_has_empty_history_and_default_profile() -> None:
    memory = ConversationMemory(max_turns=5, max_sessions=10)

    assert memory.get_history("unknown") == []
    assert memory.get_turn("unknown") == 1
    assert memory.get_profile("unknown") == CandidateProfile()


def test_start_session_stores_profile_and_opening_message() -> None:
    memory = ConversationMemory(max_turns=5, max_sessions=10)
    profile = CandidateProfile(name="Alex", position="Backend Engineer", company="Stripe")

    memory.start_session("s1", profile)
    memory.record_interviewer_opening("s1", "Welcome Alex!")

    assert memory.get_profile("s1") == profile
    assert [(m.role, m.content) for m in memory.get_history("s1")] == [
        ("assistant", "Welcome Alex!")
    ]


def test_record_exchange_advances_turn_and_marks_complete() -> None:
    memory = ConversationMemory(max_turns=2, max_sessions=10)
    memory.start_session("s1", CandidateProfile())

    turn1, done1 = memory.record_exchange("s1", "Answer 1", "Question 2")
    assert (turn1, done1) == (2, False)

    turn2, done2 = memory.record_exchange("s1", "Answer 2", "Closing")
    assert (turn2, done2) == (3, True)
    assert [m.content for m in memory.get_history("s1")] == [
        "Answer 1",
        "Question 2",
        "Answer 2",
        "Closing",
    ]


def test_sessions_are_isolated() -> None:
    memory = ConversationMemory(max_turns=5, max_sessions=10)
    memory.start_session("alice", CandidateProfile(name="Alice"))
    memory.record_exchange("alice", "Hi", "Hello Alice")

    assert memory.get_history("bob") == []


def test_evicts_least_recently_used_session_when_full() -> None:
    memory = ConversationMemory(max_turns=5, max_sessions=2)
    memory.record_exchange("old", "q", "a")
    memory.record_exchange("middle", "q", "a")
    memory.record_exchange("old", "q2", "a2")  # "old" becomes most recently used

    memory.record_exchange("new", "q", "a")  # over the limit -> evict "middle"

    assert memory.get_history("middle") == []
    assert memory.get_history("old") != []
    assert memory.get_history("new") != []


def test_returned_history_is_a_copy() -> None:
    memory = ConversationMemory(max_turns=5, max_sessions=10)
    memory.record_exchange("s1", "q", "a")

    memory.get_history("s1").clear()

    assert len(memory.get_history("s1")) == 2

