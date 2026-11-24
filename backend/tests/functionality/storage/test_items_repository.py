from datetime import date, datetime, timezone

import pytest

from functionality.storage.items_repository import (
    InvalidCursorError, _fill_daily_counts, _item_to_row, decode_cursor, encode_cursor, to_plain_text_summary,
)
from interfaces.collection_interfaces import Advisory, AffectedProduct, build_item_id
from tests.fakes import make_article

"""Tests for the pure helpers in the items repository (no database needed)."""


def test_summary_strips_html_and_entities():
    assert to_plain_text_summary("<p>Hello&nbsp;<b>world</b> &amp; more</p>") == "Hello world & more"


def test_summary_of_empty_content_is_none():
    assert to_plain_text_summary(None) is None
    assert to_plain_text_summary("<p> </p>") is None


def test_long_summary_is_cut_at_a_word_with_ellipsis():
    summary = to_plain_text_summary("word " * 100, max_length=50)
    assert len(summary) <= 50
    assert summary.endswith("…")
    assert "wor…" not in summary


def test_cursor_round_trip():
    sort_at = datetime(2026, 11, 20, 9, 30, tzinfo=timezone.utc)
    assert decode_cursor(encode_cursor(sort_at, "a" * 64)) == (sort_at, "a" * 64)


@pytest.mark.parametrize("cursor", [
    "not-base64!!",
    encode_cursor(datetime(2026, 1, 1, tzinfo=timezone.utc), "'; DROP TABLE collected_items; --"),
    "eyJmb28iOiAiYmFyIn0=",  # valid base64 JSON, wrong keys
])
def test_invalid_cursors_are_rejected(cursor):
    with pytest.raises(InvalidCursorError):
        decode_cursor(cursor)


def test_daily_counts_fill_missing_days_with_zero():
    rows = [(date(2026, 11, 2), "web", 4), (date(2026, 11, 2), "advisory", 1), (date(2026, 10, 1), "web", 9)]
    counts = _fill_daily_counts(rows, date(2026, 11, 1), days=3)

    assert [c.date for c in counts] == [date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)]
    assert (counts[0].web, counts[1].web, counts[1].advisory, counts[2].social) == (0, 4, 1, 0)


def test_type_specific_fields_go_into_details():
    row = _item_to_row(make_article("rss:a", "one"))
    details = row[9].adapted
    assert details == {"site_name": "Example"}


def test_advisory_details_keep_affected_products():
    now = datetime.now(timezone.utc)
    advisory = Advisory(
        item_id=build_item_id("cisa_kev", "CVE-2026-1"), source_name="cisa_kev", external_id="CVE-2026-1",
        title="Vuln", url=None, content=None, published_at=now, collected_at=now, raw_payload={},
        cve_id="CVE-2026-0001", affected=[AffectedProduct(vendor="Acme", product="Widget", ecosystem=None)],
        severity=None, known_exploited=True, known_ransomware_use=None, remediation_due_date=None,
    )
    details = _item_to_row(advisory)[9].adapted
    assert details["affected"] == [{"vendor": "Acme", "product": "Widget", "ecosystem": None}]
    assert details["known_exploited"] is True
    assert "title" not in details and "raw_payload" not in details
