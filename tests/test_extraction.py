from io import BytesIO
import zipfile

import pymupdf
from PIL import Image

from app.models import Diagram, Note
from app.services import extraction_service
from app.services.extraction_service import (
    extract_docx_regions,
    extract_images_regions,
    extract_pdf_regions,
)


def _make_png_bytes(width=120, height=80, color=(40, 120, 200)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def _make_docx_bytes(document_xml: str, rels_xml: str, media: dict[str, bytes]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml.encode("utf-8"))
        zf.writestr("word/_rels/document.xml.rels", rels_xml.encode("utf-8"))
        for path, data in media.items():
            zf.writestr(path, data)
    return buf.getvalue()


def test_digital_pdf_single_column_inline_image():
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_textbox(
        pymupdf.Rect(50, 80, 550, 140),
        "Top paragraph explaining the core concept in detail for testing.",
        fontsize=12,
    )
    page.insert_image(pymupdf.Rect(150, 200, 450, 340), stream=_make_png_bytes(300, 140))
    page.insert_textbox(
        pymupdf.Rect(50, 400, 550, 460),
        "Bottom paragraph continuing the discussion after the diagram.",
        fontsize=12,
    )
    pdf_bytes = doc.tobytes()
    doc.close()

    regions = extract_pdf_regions(pdf_bytes)
    assert [r.kind for r in regions] == ["text", "diagram", "text"]
    assert "Top paragraph" in regions[0].text
    assert regions[1].image_bytes is not None
    assert "Bottom paragraph" in regions[2].text


def test_digital_pdf_two_column_reading_order():
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    # Left column (x: 40..260)
    page.insert_textbox(
        pymupdf.Rect(40, 100, 260, 180),
        "Left column first block with enough text.",
        fontsize=11,
    )
    page.insert_textbox(
        pymupdf.Rect(40, 220, 260, 300),
        "Left column second block with enough text.",
        fontsize=11,
    )
    # Right column (x: 340..560)
    page.insert_textbox(
        pymupdf.Rect(340, 100, 560, 180),
        "Right column first block with enough text.",
        fontsize=11,
    )
    page.insert_textbox(
        pymupdf.Rect(340, 220, 560, 300),
        "Right column second block with enough text.",
        fontsize=11,
    )
    pdf_bytes = doc.tobytes()
    doc.close()

    regions = extract_pdf_regions(pdf_bytes)
    texts = [r.text for r in regions if r.kind == "text"]
    assert len(texts) == 4
    assert "Left column first" in texts[0]
    assert "Left column second" in texts[1]
    assert "Right column first" in texts[2]
    assert "Right column second" in texts[3]


def test_digital_pdf_spanning_figure_splits_two_columns():
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    # Top 2-column band (y: 80..160)
    page.insert_textbox(
        pymupdf.Rect(40, 80, 240, 160),
        "Top left column line one.\nTop left column line two.",
        fontsize=11,
    )
    page.insert_textbox(
        pymupdf.Rect(360, 80, 560, 160),
        "Top right column line one.\nTop right column line two.",
        fontsize=11,
    )
    # Full-width spanning figure (width > 60% of 600 = 360, crossing 300)
    page.insert_image(pymupdf.Rect(60, 220, 540, 360), stream=_make_png_bytes(480, 140))
    # Bottom 2-column band (y: 420..520)
    page.insert_textbox(
        pymupdf.Rect(40, 420, 240, 520),
        "Bottom left column line one.\nBottom left column line two.",
        fontsize=11,
    )
    page.insert_textbox(
        pymupdf.Rect(360, 420, 560, 520),
        "Bottom right column line one.\nBottom right column line two.",
        fontsize=11,
    )
    pdf_bytes = doc.tobytes()
    doc.close()

    regions = extract_pdf_regions(pdf_bytes)
    assert [r.kind for r in regions] == ["text", "text", "diagram", "text", "text"]
    assert "Top left" in regions[0].text
    assert "Top right" in regions[1].text
    assert "Bottom left" in regions[3].text
    assert "Bottom right" in regions[4].text


def test_docx_inline_image_and_table():
    doc_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <w:body>
        <w:p><w:r><w:t>Intro before image.</w:t></w:r></w:p>
        <w:p><w:r><a:blip r:embed="rId1"/></w:r></w:p>
        <w:tbl>
          <w:tr>
            <w:tc><w:p><w:r><w:t>Term</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>Definition</w:t></w:r></w:p></w:tc>
          </w:tr>
          <w:tr>
            <w:tc><w:p><w:r><w:t>Ohm</w:t></w:r></w:p></w:tc>
            <w:tc><w:p><w:r><w:t>Unit of resistance</w:t></w:r></w:p></w:tc>
          </w:tr>
        </w:tbl>
        <w:p><w:r><w:t>Conclusion after table.</w:t></w:r></w:p>
      </w:body>
    </w:document>"""
    rels_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
        Target="media/img1.png"/>
    </Relationships>"""
    docx_bytes = _make_docx_bytes(doc_xml, rels_xml, {"word/media/img1.png": _make_png_bytes()})

    regions = extract_docx_regions(docx_bytes)
    assert [r.kind for r in regions] == ["text", "diagram", "text", "text"]
    assert regions[0].text == "Intro before image."
    assert regions[1].image_bytes is not None
    assert "| Term | Definition |" in regions[2].text
    assert "| Ohm | Unit of resistance |" in regions[2].text
    assert regions[3].text == "Conclusion after table."


def test_camera_upload_12_photos_single_batch_and_inline_crop(
    logged_in_client, db, user, monkeypatch
):
    calls = []

    def fake_ask_gemini(question, action):
        calls.append((action, len(question) - 1))
        return [
            {"image_index": 0, "kind": "text", "box_2d": [50, 50, 250, 950], "text": "Header notes"},
            {"image_index": 0, "kind": "diagram", "box_2d": [300, 100, 700, 900], "text": ""},
            {"image_index": 0, "kind": "text", "box_2d": [750, 50, 950, 950], "text": "Footer notes"},
            {"image_index": 11, "kind": "text", "box_2d": [50, 50, 250, 950], "text": "Last page text"},
        ]

    monkeypatch.setattr(extraction_service, "ask_gemini", fake_ask_gemini)
    monkeypatch.setattr("app.uploads.routes.format_note_content", lambda md, uid: md)
    monkeypatch.setattr("app.uploads.routes.get_meta_data", lambda md, user_id: {"tags": ["camera"]})
    monkeypatch.setattr("app.uploads.routes.upsert_note_vector", lambda note: None)

    files = [
        (BytesIO(_make_png_bytes(200, 200)), f"photo_{i}.png")
        for i in range(12)
    ]
    res = logged_in_client.post(
        "/upload_note_file",
        data={"files": files},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert calls == [("detect_regions", 12)]

    note = db.session.get(Note, data["note_id"])
    assert note is not None
    diagrams = Diagram.query.filter_by(note_id=note.id).all()
    assert len(diagrams) == 1
    expected_link = f"![Diagram](/diagram_image/{diagrams[0].id}.png)"
    assert note.md_content.index("Header notes") < note.md_content.index(expected_link)
    assert note.md_content.index(expected_link) < note.md_content.index("Footer notes")
    assert "Last page text" in note.md_content


def test_upload_images_rejects_over_50mb_budget(logged_in_client, monkeypatch):
    monkeypatch.setattr("app.uploads.routes.MAX_IMAGE_UPLOAD_BYTES", 200)
    files = [
        (BytesIO(_make_png_bytes(100, 100)), "a.png"),
        (BytesIO(_make_png_bytes(100, 100)), "b.png"),
    ]
    res = logged_in_client.post(
        "/upload_note_file",
        data={"files": files},
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"
    assert "50 MB" in data["message"]


def test_extract_images_regions_splits_oversized_batches(monkeypatch):
    batch_sizes = []

    def fake_ask_gemini(question, action):
        n_imgs = len(question) - 1
        batch_sizes.append(n_imgs)
        return [
            {"image_index": i, "kind": "text", "box_2d": [50, 50, 200, 900], "text": f"Page {i}"}
            for i in range(n_imgs)
        ]

    monkeypatch.setattr(extraction_service, "ask_gemini", fake_ask_gemini)
    # Force budget small enough that 1 image fits per batch, 2nd triggers a new batch
    sample = _make_png_bytes(100, 100)
    monkeypatch.setattr(extraction_service, "MAX_BATCH_BASE64_BYTES", 500)
    monkeypatch.setattr(
        extraction_service,
        "_encode_image_for_batch",
        lambda img: (img, b"x" * 300, 400),
    )

    regions = extract_images_regions([sample, sample, sample])
    assert batch_sizes == [1, 1, 1]
    assert len(regions) == 3


def test_extract_images_regions_tesseract_fallback_on_gemini_failure(monkeypatch):
    monkeypatch.setattr(
        extraction_service,
        "ask_gemini",
        lambda question, action: {"error": True, "type": "rate_limit", "msg": "429"},
    )
    monkeypatch.setattr(
        extraction_service.pytesseract,
        "image_to_string",
        lambda img: "Fallback OCR text",
    )

    regions = extract_images_regions([_make_png_bytes()])
    assert len(regions) == 1
    assert regions[0].kind == "text"
    assert regions[0].text == "Fallback OCR text"
