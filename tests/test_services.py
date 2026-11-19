from types import SimpleNamespace

from app.services.note_service import (
    extract_topic_for_search,
    chunk_notes_content,
)


# ── extract_topic_for_search ──────────────────────────────────────────────────


def test_extract_topic_strips_summarize_prefix():
    assert (
        extract_topic_for_search("summarize the note on Photosynthesis")
        == "Photosynthesis"
    )


def test_extract_topic_strips_explain_prefix():
    assert (
        extract_topic_for_search("explain the note about Newton's Laws")
        == "Newton's Laws"
    )


def test_extract_topic_strips_extract_key_points_prefix():
    assert (
        extract_topic_for_search("extract key points from Thermodynamics")
        == "Thermodynamics"
    )


def test_extract_topic_passes_through_when_no_prefix():
    assert extract_topic_for_search("DNA replication") == "DNA replication"


def test_extract_topic_handles_empty_string():
    assert extract_topic_for_search("") == ""


def test_extract_topic_handles_whitespace_only():
    assert extract_topic_for_search("   ") == ""


# ── chunk_notes_content ───────────────────────────────────────────────────────


def test_chunk_empty_list_returns_no_batches():
    assert chunk_notes_content([], user_id=None) == []


def test_chunk_single_short_note_returns_one_batch():
    notes = [SimpleNamespace(md_content="short")]
    batches = chunk_notes_content(notes, user_id=None)
    assert len(batches) == 1


def test_chunk_two_notes_under_limit_returns_one_batch():
    notes = [
        SimpleNamespace(md_content="First note"),
        SimpleNamespace(md_content="Second note"),
    ]
    batches = chunk_notes_content(notes, user_id=None)
    assert len(batches) == 1


def test_chunk_oversize_returns_multiple_batches():
    oversize_content = ("x" * 20000) + "\n\n" + ("y" * 20000)
    notes = [SimpleNamespace(md_content=oversize_content)]
    batches = chunk_notes_content(notes, user_id=None)
    assert len(batches) > 1


def test_chunk_preserves_all_content():
    notes = [
        SimpleNamespace(md_content="Alpha unique content"),
        SimpleNamespace(md_content="Beta unique content"),
    ]
    batches = chunk_notes_content(notes, user_id=None)
    combined = "\n".join(b if isinstance(b, str) else b[0] for b in batches)
    assert "Alpha unique content" in combined
    assert "Beta unique content" in combined


def test_chunk_skips_notes_with_empty_content():
    notes = [
        SimpleNamespace(md_content=""),
        SimpleNamespace(md_content="Real note content"),
    ]
    batches = chunk_notes_content(notes, user_id=None)
    assert len(batches) == 1
    text = batches[0] if isinstance(batches[0], str) else batches[0][0]
    assert "Real note content" in text
