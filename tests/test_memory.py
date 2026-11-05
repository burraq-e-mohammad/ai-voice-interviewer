"""Unit tests for the in-memory conversation history."""

from app.services.memory import ConversationMemory


def test_new_session_has_empty_history() -> None:
    memory = ConversationMemory(max_turns=3, max_sessions=10)

    assert memory.get_history("unknown") == []


def test_stores_user_and_assistant_messages_in_order() -> None:
    memory = ConversationMemory(max_turns=3, max_sessions=10)

    memory.add_exchange("s1", "Hi", "Hello!")

    history = memory.get_history("s1")
    assert [(m.role, m.content) for m in history] == [("user", "Hi"), ("assistant", "Hello!")]


def test_keeps_only_the_last_n_turns() -> None:
    memory = ConversationMemory(max_turns=2, max_sessions=10)

    for i in range(5):
        memory.add_exchange("s1", f"q{i}", f"a{i}")

    contents = [m.content for m in memory.get_history("s1")]
    assert contents == ["q3", "a3", "q4", "a4"]


def test_sessions_are_isolated() -> None:
    memory = ConversationMemory(max_turns=3, max_sessions=10)

    memory.add_exchange("alice", "I am Alice", "Hi Alice")

    assert memory.get_history("bob") == []


def test_evicts_least_recently_used_session_when_full() -> None:
    memory = ConversationMemory(max_turns=3, max_sessions=2)
    memory.add_exchange("old", "q", "a")
    memory.add_exchange("middle", "q", "a")
    memory.add_exchange("old", "q2", "a2")  # "old" is now the most recently used

    memory.add_exchange("new", "q", "a")  # over the limit -> evict "middle"

    assert memory.get_history("middle") == []
    assert memory.get_history("old") != []
    assert memory.get_history("new") != []


def test_zero_turns_disables_memory() -> None:
    memory = ConversationMemory(max_turns=0, max_sessions=10)

    memory.add_exchange("s1", "q", "a")

    assert memory.get_history("s1") == []


def test_returned_history_is_a_copy() -> None:
    memory = ConversationMemory(max_turns=3, max_sessions=10)
    memory.add_exchange("s1", "q", "a")

    memory.get_history("s1").clear()  # changing the copy...

    assert len(memory.get_history("s1")) == 2  # ...does not change the stored history
