"""Tests for orbit.gui.utils.label_utils."""

import pytest

from orbit.gui.utils.label_utils import ID_DISPLAY_LENGTH, entity_label, format_id


class TestFormatId:
    def test_short_id_kept(self):
        assert format_id("11") == "11"

    def test_long_id_elided(self):
        long_id = "a" * (ID_DISPLAY_LENGTH + 5)
        out = format_id(long_id)
        assert out.startswith("a" * ID_DISPLAY_LENGTH)
        assert out.endswith("…")

    def test_missing_id(self):
        assert format_id(None) == "?"
        assert format_id("") == "?"


class TestEntityLabel:
    def test_id_leads_the_name(self):
        assert entity_label("11", "Säröleden") == "[11] Säröleden"

    def test_name_with_parentheses_stays_readable(self):
        """Why the ID leads: a trailing (11) would be lost inside the name."""
        assert entity_label("11", "Säröleden (seg 1/2)") == "[11] Säröleden (seg 1/2)"

    def test_kind_used_when_unnamed(self):
        assert entity_label("7", None, kind="Polyline") == "[7] Polyline"

    def test_empty_name_falls_back_to_kind(self):
        assert entity_label("7", "", kind="Road") == "[7] Road"

    def test_id_only(self):
        assert entity_label("7") == "[7]"

    def test_rich_bolds_only_the_id(self):
        assert entity_label("11", "Road A", rich=True) == "[<b>11</b>] Road A"


@pytest.mark.parametrize("entity_id,name", [("1", "A"), ("22", None)])
def test_label_always_contains_the_id(entity_id, name):
    assert entity_id in entity_label(entity_id, name, kind="Road")
