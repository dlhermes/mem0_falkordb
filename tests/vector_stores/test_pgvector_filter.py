"""
Tests for PR #6879: validate that in/nin filter operator values are lists.

Before this fix, `{"user_id": {"in": "alice"}}` silently iterated the string
char-by-char into `= ANY({a,l,i,c,e})`, matching nothing and producing a
confusing "no results" instead of an error. This validates that in/nin
values must be a list and raises ValueError otherwise.

Tests hit the pure `_build_filter_conditions` function directly, so no
PostgreSQL connection is needed.
"""

import pytest

from mem0.vector_stores.pgvector import _build_filter_conditions


class TestInNinValueValidation:
    """in/nin operator values must be lists."""

    @pytest.mark.parametrize("op", ["in", "nin"])
    @pytest.mark.parametrize("bad_value", ["alice", 42, 3.14, {"a": 1}])
    def test_non_list_value_raises_valueerror(self, op, bad_value):
        """String, int, float and dict values all raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            _build_filter_conditions({"user_id": {op: bad_value}})
        assert (
            str(exc_info.value)
            == f"Filter operator {op!r} for key 'user_id' requires a list value, got {type(bad_value).__name__}"
        )

    def test_in_list_works(self):
        """in with a list builds the ANY condition."""
        conditions, params = _build_filter_conditions({"user_id": {"in": ["alice", "bob"]}})
        assert conditions == ["payload->>%s = ANY(%s)"]
        assert params == ["user_id", ["alice", "bob"]]

    def test_nin_list_works(self):
        """nin with a list builds the negated ANY condition."""
        conditions, params = _build_filter_conditions({"user_id": {"nin": ["alice", "bob"]}})
        assert conditions == ["NOT (payload->>%s = ANY(%s))"]
        assert params == ["user_id", ["alice", "bob"]]

    def test_list_items_cast_to_str(self):
        """Non-string list items are stringified like before."""
        conditions, params = _build_filter_conditions({"run_id": {"in": [1, 2]}})
        assert params == ["run_id", ["1", "2"]]

    def test_empty_list_works(self):
        """An empty list is still a list and must not raise."""
        conditions, params = _build_filter_conditions({"user_id": {"in": []}})
        assert params == ["user_id", []]

    def test_mixed_valid_and_invalid_raises(self):
        """A bad value anywhere in the filter dict raises."""
        with pytest.raises(ValueError):
            _build_filter_conditions({"user_id": {"in": ["alice"]}, "agent_id": {"nin": "bad"}})


class TestLikeEscapingUnaffected:
    """The existing LIKE/ILIKE wildcard escaping must keep working."""

    def test_contains_percent_escaped(self):
        conditions, params = _build_filter_conditions({"name": {"contains": "50%"}})
        assert conditions == ["payload->>%s LIKE %s ESCAPE '\\'"]
        assert params == ["name", "%50\\%%"]

    def test_icontains_underscore_escaped(self):
        conditions, params = _build_filter_conditions({"name": {"icontains": "a_b"}})
        assert conditions == ["payload->>%s ILIKE %s ESCAPE '\\'"]
        assert params == ["name", "%a\\_b%"]

    def test_contains_backslash_escaped(self):
        conditions, params = _build_filter_conditions({"name": {"contains": r"a\b"}})
        assert params == ["name", r"%a\\b%"]

    def test_contains_with_plain_text(self):
        conditions, params = _build_filter_conditions({"name": {"contains": "alice"}})
        assert params == ["name", "%alice%"]
