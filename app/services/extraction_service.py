"""
Section-wise OCR and diagram-localization extraction pipeline.

Produces an ordered list of Region(kind="text"|"diagram") in human reading
order for digital PDFs, scanned PDFs, DOCX files, and camera photos.
"""

from dataclasses import dataclass
from io import BytesIO
import logging
import math
import re
from typing import Literal
from xml.etree import ElementTree
import zipfile

from PIL import Image, ImageOps, UnidentifiedImageError
import pymupdf
import pytesseract

from ai_service import ask_gemini, is_ai_error

logger = logging.getLogger(__name__)

GEMINI_PAYLOAD_BUDGET_BYTES = 20 * 1024 * 1024
BATCH_HEADROOM_BYTES = 1 * 1024 * 1024
MAX_BATCH_BASE64_BYTES = GEMINI_PAYLOAD_BUDGET_BYTES - BATCH_HEADROOM_BYTES  # 19 MB
_CAPTION_RE = re.compile(r"^\s*(?:Figure|Fig\.?)\s*\d+", re.IGNORECASE)


@dataclass
class Region:
    """Ordered content region extracted from a document or image."""

    kind: Literal["text", "diagram"]
    text: str = ""
    image_bytes: bytes | None = None
    page_num: int = 0
    bbox: tuple[float, float, float, float] | None = None


def _prepare_pil_image(img_bytes: bytes) -> Image.Image:
    """Apply EXIF orientation transpose and convert image bytes to RGB PIL Image."""
    img = Image.open(BytesIO(img_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _pil_to_png_bytes(img: Image.Image) -> bytes:
    """Encode a PIL Image as PNG bytes."""
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _bbox_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Compute Intersection-over-Union for two (x0, y0, x1, y1) bounding boxes."""
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    iw = max(0.0, ix1 - ix0)
    ih = max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0.0 else 0.0


def _find_gutter_split(band: list[Region], page_width: float) -> float | None:
    """Return a vertical split x-coordinate if band has a 2-column whitespace gutter."""
    if len(band) < 2 or page_width <= 0:
        return None

    left_bound = 0.35 * page_width
    right_bound = 0.65 * page_width
    step = max(1.0, page_width / 200.0)

    best_start = None
    best_len = 0
    curr_start = None
    curr_len = 0

    x = left_bound
    while x <= right_bound:
        overlaps = any(r.bbox and r.bbox[0] < x < r.bbox[2] for r in band)
        if not overlaps:
            if curr_start is None:
                curr_start = x
                curr_len = 1
            else:
                curr_len += 1
            if curr_len > best_len:
                best_len = curr_len
                best_start = curr_start
        else:
            curr_start = None
            curr_len = 0
        x += step

    if best_start is None or best_len == 0:
        return None

    split_x = best_start + (best_len * step) / 2.0
    has_left = any(r.bbox and (r.bbox[0] + r.bbox[2]) / 2.0 < split_x for r in band)
    has_right = any(r.bbox and (r.bbox[0] + r.bbox[2]) / 2.0 > split_x for r in band)
    return split_x if (has_left and has_right) else None


def _keep_captions_adjacent(regions: list[Region]) -> list[Region]:
    """Move figure captions immediately after their horizontally aligned diagram."""
    result = list(regions)
    diagrams = [(idx, r) for idx, r in enumerate(result) if r.kind == "diagram" and r.bbox]
    if not diagrams:
        return result

    captions = [
        r for r in result
        if r.kind == "text" and r.bbox and _CAPTION_RE.match(r.text)
    ]
    for cap in captions:
        cx0, cy0, cx1, cy1 = cap.bbox
        best_diag = None
        best_dist = float("inf")
        for _, diag in diagrams:
            dx0, dy0, dx1, dy1 = diag.bbox
            if min(cx1, dx1) > max(cx0, dx0):
                dist = min(abs(cy0 - dy1), abs(dy0 - cy1))
                if dist < best_dist:
                    best_dist = dist
                    best_diag = diag
        if best_diag is not None:
            result.remove(cap)
            diag_idx = result.index(best_diag)
            result.insert(diag_idx + 1, cap)
    return result


def _sort_regions_reading_order(regions: list[Region], page_width: float) -> list[Region]:
    """Sort regions into human reading order using spanning bands and column gutters."""
    if not regions:
        return []

    spanning: list[Region] = []
    regular: list[Region] = []
    mid_x = page_width / 2.0

    for r in regions:
        if r.bbox is None:
            regular.append(r)
            continue
        x0, _, x1, _ = r.bbox
        if (x1 - x0) > 0.6 * page_width and x0 < mid_x < x1:
            spanning.append(r)
        else:
            regular.append(r)

    spanning.sort(key=lambda r: (r.bbox[1], r.bbox[0]))

    bands: list[list[Region]] = [[] for _ in range(len(spanning) + 1)]
    for r in regular:
        if r.bbox is None:
            bands[-1].append(r)
            continue
        cy = (r.bbox[1] + r.bbox[3]) / 2.0
        placed = False
        for idx, sp in enumerate(spanning):
            if cy < sp.bbox[1]:
                bands[idx].append(r)
                placed = True
                break
        if not placed:
            bands[-1].append(r)

    ordered: list[Region] = []
    for idx, band in enumerate(bands):
        split_x = _find_gutter_split(band, page_width)
        if split_x is not None:
            left = [r for r in band if r.bbox and (r.bbox[0] + r.bbox[2]) / 2.0 <= split_x]
            right = [r for r in band if r.bbox and (r.bbox[0] + r.bbox[2]) / 2.0 > split_x]
            left.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
            right.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
            ordered.extend(left)
            ordered.extend(right)
        else:
            band.sort(key=lambda r: (r.bbox[1], r.bbox[0]) if r.bbox else (0.0, 0.0))
            ordered.extend(band)

        if idx < len(spanning):
            ordered.append(spanning[idx])

    return _keep_captions_adjacent(ordered)


def _cluster_vector_drawings(
    page: pymupdf.Page,
    raster_bboxes: list[tuple[float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    """Cluster dense vector drawings (>60x60 pt) that do not overlap raster images."""
    page_w = page.rect.width
    page_h = page.rect.height
    raw_rects: list[list[float]] = []

    for d in page.get_drawings():
        rect = d.get("rect")
        if rect is None:
            continue
        x0, y0, x1, y1 = float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)
        w, h = x1 - x0, y1 - y0
        # Ignore full-page borders and zero-area artifacts
        if w > 0.9 * page_w and h > 0.9 * page_h:
            continue
        if w <= 0 and h <= 0:
            continue
        raw_rects.append([x0, y0, x1, y1])

    if not raw_rects:
        return []

    pad = 12.0
    merged = True
    while merged:
        merged = False
        next_rects: list[list[float]] = []
        used = [False] * len(raw_rects)
        for i in range(len(raw_rects)):
            if used[i]:
                continue
            cur = list(raw_rects[i])
            used[i] = True
            for j in range(i + 1, len(raw_rects)):
                if used[j]:
                    continue
                other = raw_rects[j]
                if (
                    cur[0] - pad <= other[2]
                    and cur[2] + pad >= other[0]
                    and cur[1] - pad <= other[3]
                    and cur[3] + pad >= other[1]
                ):
                    cur[0] = min(cur[0], other[0])
                    cur[1] = min(cur[1], other[1])
                    cur[2] = max(cur[2], other[2])
                    cur[3] = max(cur[3], other[3])
                    used[j] = True
                    merged = True
            next_rects.append(cur)
        raw_rects = next_rects

    clusters: list[tuple[float, float, float, float]] = []
    for x0, y0, x1, y1 in raw_rects:
        w, h = x1 - x0, y1 - y0
        if w <= 60.0 or h <= 60.0:
            continue
        if w > 0.92 * page_w and h > 0.92 * page_h:
            continue
        cand = (x0, y0, x1, y1)
        if any(_bbox_iou(cand, rb) > 0.3 for rb in raster_bboxes):
            continue
        clusters.append(cand)
    return clusters


def _crop_pdf_bbox(pix_img: Image.Image, bbox: tuple[float, float, float, float], dpi: int = 200) -> bytes:
    """Crop a PDF point-space bbox from a rendered PIL page image and return PNG bytes."""
    scale = dpi / 72.0
    pw, ph = pix_img.size
    x0 = max(0, int(math.floor(bbox[0] * scale)))
    y0 = max(0, int(math.floor(bbox[1] * scale)))
    x1 = min(pw, int(math.ceil(bbox[2] * scale)))
    y1 = min(ph, int(math.ceil(bbox[3] * scale)))
    if x1 <= x0 or y1 <= y0:
        return b""
    return _pil_to_png_bytes(pix_img.crop((x0, y0, x1, y1)))


def extract_pdf_regions(file_bytes: bytes) -> list[Region]:
    """Extract ordered text and diagram regions from a digital or scanned PDF."""
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    page_results: dict[int, list[Region]] = {}
    scanned_pages: list[tuple[int, bytes]] = []

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_dict = page.get_text("dict")
            blocks = page_dict.get("blocks", [])

            raw_text_chars = []
            for b in blocks:
                if b.get("type") == 0:
                    for line in b.get("lines", []):
                        for span in line.get("spans", []):
                            raw_text_chars.append(span.get("text", ""))
            joined_raw = "".join(raw_text_chars)
            non_ws = re.sub(r"\s+", "", joined_raw)
            garbled_ratio = (non_ws.count("\ufffd") / len(non_ws)) if non_ws else 0.0

            if len(non_ws) < 30 or garbled_ratio > 0.15:
                pix = page.get_pixmap(dpi=200)
                scanned_pages.append((page_num, pix.tobytes("png")))
                continue

            page_w = float(page.rect.width)
            page_h = float(page.rect.height)
            top_margin = 0.05 * page_h
            bottom_margin = 0.95 * page_h
            regions: list[Region] = []
            raster_bboxes: list[tuple[float, float, float, float]] = []
            rendered_pil: Image.Image | None = None

            def _get_rendered_pil() -> Image.Image:
                nonlocal rendered_pil
                if rendered_pil is None:
                    pix = page.get_pixmap(dpi=200)
                    rendered_pil = _prepare_pil_image(pix.tobytes("png"))
                return rendered_pil

            for b in blocks:
                bbox = tuple(float(v) for v in b.get("bbox", (0, 0, 0, 0)))
                x0, y0, x1, y1 = bbox
                bw, bh = x1 - x0, y1 - y0

                # Skip running headers/footers in the top/bottom 5%
                if y1 <= top_margin or y0 >= bottom_margin:
                    continue

                if b.get("type") == 0:
                    if bw < 25.0:
                        continue
                    lines_text = []
                    for line in b.get("lines", []):
                        line_str = "".join(
                            span.get("text", "") for span in line.get("spans", [])
                        ).strip()
                        if line_str:
                            lines_text.append(line_str)
                    text = " ".join(lines_text).strip()
                    if text:
                        regions.append(
                            Region(kind="text", text=text, page_num=page_num, bbox=bbox)
                        )

                elif b.get("type") == 1:
                    if bw < 25.0 or bh < 25.0:
                        continue
                    img_bytes = b.get("image")
                    if not img_bytes and b.get("xref"):
                        try:
                            img_bytes = doc.extract_image(b["xref"])["image"]
                        except Exception:
                            img_bytes = None
                    if not img_bytes:
                        img_bytes = _crop_pdf_bbox(_get_rendered_pil(), bbox)
                    if img_bytes:
                        try:
                            png_bytes = _pil_to_png_bytes(_prepare_pil_image(img_bytes))
                            raster_bboxes.append(bbox)
                            regions.append(
                                Region(
                                    kind="diagram",
                                    image_bytes=png_bytes,
                                    page_num=page_num,
                                    bbox=bbox,
                                )
                            )
                        except Exception:
                            continue

            for v_bbox in _cluster_vector_drawings(page, raster_bboxes):
                crop_bytes = _crop_pdf_bbox(_get_rendered_pil(), v_bbox)
                if crop_bytes:
                    regions.append(
                        Region(
                            kind="diagram",
                            image_bytes=crop_bytes,
                            page_num=page_num,
                            bbox=v_bbox,
                        )
                    )

            page_results[page_num] = _sort_regions_reading_order(regions, page_w)

        if scanned_pages:
            scanned_regions = extract_images_regions([img for _, img in scanned_pages])
            for reg in scanned_regions:
                actual_page_num = scanned_pages[reg.page_num][0]
                reg.page_num = actual_page_num
                page_results.setdefault(actual_page_num, []).append(reg)

        ordered_all: list[Region] = []
        for p_idx in range(len(doc)):
            ordered_all.extend(page_results.get(p_idx, []))
        return ordered_all
    finally:
        doc.close()


def extract_docx_regions(file_bytes: bytes) -> list[Region]:
    """Extract ordered text, Markdown tables, and inline diagrams from a DOCX file."""
    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "v": "urn:schemas-microsoft-com:vml",
    }
    w_ns = f"{{{ns['w']}}}"
    a_blip_tag = f"{{{ns['a']}}}blip"
    v_img_tag = f"{{{ns['v']}}}imagedata"
    r_embed_attr = f"{{{ns['r']}}}embed"
    r_id_attr = f"{{{ns['r']}}}id"

    regions: list[Region] = []

    with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
        rel_map: dict[str, str] = {}
        if "word/_rels/document.xml.rels" in zf.namelist():
            rels_root = ElementTree.fromstring(zf.read("word/_rels/document.xml.rels"))
            for rel in rels_root:
                rel_type = rel.attrib.get("Type", "")
                if rel_type.endswith("/image"):
                    rid = rel.attrib.get("Id")
                    target = rel.attrib.get("Target", "").lstrip("/")
                    if target and not target.startswith("word/"):
                        target = f"word/{target}"
                    if rid and target:
                        rel_map[rid] = target

        def _load_png_from_rid(rid: str | None) -> bytes | None:
            if not rid or rid not in rel_map:
                return None
            target = rel_map[rid]
            if target not in zf.namelist():
                return None
            try:
                return _pil_to_png_bytes(_prepare_pil_image(zf.read(target)))
            except (UnidentifiedImageError, Exception):
                return None

        def _process_paragraph(p_el: ElementTree.Element) -> tuple[str, list[Region]]:
            """Walk paragraph elements in order, splitting text around inline images."""
            p_regions: list[Region] = []
            buf: list[str] = []

            def _flush():
                txt = "".join(buf).strip()
                buf.clear()
                if txt:
                    p_regions.append(Region(kind="text", text=txt))

            for elem in p_el.iter():
                if elem.tag == f"{w_ns}t" and elem.text:
                    buf.append(elem.text)
                elif elem.tag == a_blip_tag:
                    png = _load_png_from_rid(elem.attrib.get(r_embed_attr))
                    if png:
                        _flush()
                        p_regions.append(Region(kind="diagram", image_bytes=png))
                elif elem.tag == v_img_tag:
                    png = _load_png_from_rid(elem.attrib.get(r_id_attr))
                    if png:
                        _flush()
                        p_regions.append(Region(kind="diagram", image_bytes=png))

            _flush()
            combined_text = " ".join(r.text for r in p_regions if r.kind == "text")
            return combined_text, p_regions

        doc_root = ElementTree.fromstring(zf.read("word/document.xml"))
        body = doc_root.find("w:body", ns)
        if body is None:
            return []

        for child in body:
            if child.tag == f"{w_ns}p":
                _, p_regions = _process_paragraph(child)
                regions.extend(p_regions)
            elif child.tag == f"{w_ns}tbl":
                rows_md: list[str] = []
                tbl_diagrams: list[Region] = []
                for tr in child.findall("w:tr", ns):
                    cells_text: list[str] = []
                    for tc in tr.findall("w:tc", ns):
                        cell_parts: list[str] = []
                        for p in tc.findall("w:p", ns):
                            c_txt, p_regs = _process_paragraph(p)
                            if c_txt:
                                cell_parts.append(c_txt)
                            tbl_diagrams.extend(r for r in p_regs if r.kind == "diagram")
                        cells_text.append(" ".join(cell_parts).replace("|", "\\|").strip())
                    if any(cells_text):
                        rows_md.append("| " + " | ".join(cells_text) + " |")
                        if len(rows_md) == 1:
                            rows_md.append("| " + " | ".join("---" for _ in cells_text) + " |")
                if rows_md:
                    regions.append(Region(kind="text", text="\n".join(rows_md)))
                regions.extend(tbl_diagrams)

    return regions


def _apply_nms(items: list[dict], iou_threshold: float = 0.6) -> list[dict]:
    """Suppress overlapping bounding boxes above iou_threshold."""
    kept: list[dict] = []
    for item in items:
        box = item["clamped_box"]
        if any(_bbox_iou(box, k["clamped_box"]) > iou_threshold for k in kept):
            continue
        kept.append(item)
    return kept


def _encode_image_for_batch(pil_img: Image.Image) -> tuple[Image.Image, bytes, int]:
    """Encode PIL image and downscale to <=2000px JPEG if its base64 exceeds budget."""
    png_bytes = _pil_to_png_bytes(pil_img)
    b64_size = math.ceil(len(png_bytes) * 4 / 3)
    if b64_size <= MAX_BATCH_BASE64_BYTES:
        return pil_img, png_bytes, b64_size

    w, h = pil_img.size
    if max(w, h) > 2000:
        scale = 2000.0 / max(w, h)
        pil_img = pil_img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.LANCZOS,
        )
    buf = BytesIO()
    pil_img.save(buf, format="JPEG", quality=90)
    jpg_bytes = buf.getvalue()
    return pil_img, jpg_bytes, math.ceil(len(jpg_bytes) * 4 / 3)


def _tesseract_fallback(orig_idx: int, pil_img: Image.Image) -> list[Region]:
    """Run whole-image Tesseract OCR as a single text region fallback."""
    try:
        text = pytesseract.image_to_string(pil_img).strip()
    except Exception as e:
        logger.warning("[extraction_service] Tesseract fallback failed: %s", e)
        text = ""
    return [Region(kind="text", text=text, page_num=orig_idx)] if text else []


def _process_image_batch(batch: list[tuple[int, Image.Image, bytes, int]]) -> list[Region]:
    """Call Gemini Vision to localize regions in a batch, recursively splitting on failure."""
    prompt_lines = [
        f"Analyze the following {len(batch)} image(s) (indexed 0 to {len(batch) - 1})."
    ]
    for i in range(len(batch)):
        prompt_lines.append(f"Image {i}")
    batch_prompt = "\n".join(prompt_lines)

    payload = [batch_prompt, *[item[1] for item in batch]]
    result = ask_gemini(question=payload, action="detect_regions")

    if is_ai_error(result) or not isinstance(result, list):
        if len(batch) > 1:
            mid = len(batch) // 2
            return _process_image_batch(batch[:mid]) + _process_image_batch(batch[mid:])
        orig_idx, pil_img, _, _ = batch[0]
        return _tesseract_fallback(orig_idx, pil_img)

    grouped: dict[int, list[dict]] = {i: [] for i in range(len(batch))}
    for entry in result:
        if not isinstance(entry, dict):
            continue
        img_idx = entry.get("image_index", 0)
        if not isinstance(img_idx, int) or img_idx not in grouped:
            continue
        box = entry.get("box_2d")
        if not isinstance(box, list) or len(box) != 4:
            continue
        try:
            ymin, xmin, ymax, xmax = [max(0.0, min(1000.0, float(v))) for v in box]
        except (TypeError, ValueError):
            continue
        if (xmax - xmin) < 20.0 or (ymax - ymin) < 20.0:
            continue
        grouped[img_idx].append({
            "kind": entry.get("kind"),
            "clamped_box": (xmin, ymin, xmax, ymax),
            "text": (entry.get("text") or "").strip(),
        })

    all_regions: list[Region] = []
    for local_idx, (orig_idx, pil_img, _, _) in enumerate(batch):
        items = _apply_nms(grouped[local_idx], iou_threshold=0.6)
        w, h = pil_img.size
        img_regions: list[Region] = []

        for item in items:
            xmin, ymin, xmax, ymax = item["clamped_box"]
            kind = item["kind"]
            if kind == "diagram":
                px0 = max(0, int(math.floor((xmin / 1000.0) * w)) - 15)
                py0 = max(0, int(math.floor((ymin / 1000.0) * h)) - 15)
                px1 = min(w, int(math.ceil((xmax / 1000.0) * w)) + 15)
                py1 = min(h, int(math.ceil((ymax / 1000.0) * h)) + 15)
                if px1 > px0 and py1 > py0:
                    crop_bytes = _pil_to_png_bytes(pil_img.crop((px0, py0, px1, py1)))
                    img_regions.append(
                        Region(
                            kind="diagram",
                            image_bytes=crop_bytes,
                            page_num=orig_idx,
                            bbox=(xmin, ymin, xmax, ymax),
                        )
                    )
            elif kind == "text":
                txt = item["text"]
                if not txt:
                    px0 = max(0, int(math.floor((xmin / 1000.0) * w)))
                    py0 = max(0, int(math.floor((ymin / 1000.0) * h)))
                    px1 = min(w, int(math.ceil((xmax / 1000.0) * w)))
                    py1 = min(h, int(math.ceil((ymax / 1000.0) * h)))
                    if px1 > px0 and py1 > py0:
                        try:
                            txt = pytesseract.image_to_string(
                                pil_img.crop((px0, py0, px1, py1))
                            ).strip()
                        except Exception:
                            txt = ""
                if txt:
                    img_regions.append(
                        Region(
                            kind="text",
                            text=txt,
                            page_num=orig_idx,
                            bbox=(xmin, ymin, xmax, ymax),
                        )
                    )

        if not img_regions:
            img_regions = _tesseract_fallback(orig_idx, pil_img)
        else:
            img_regions = _sort_regions_reading_order(img_regions, page_width=1000.0)

        all_regions.extend(img_regions)

    return all_regions


def extract_images_regions(image_bytes_list: list[bytes]) -> list[Region]:
    """Extract ordered text and diagram regions from camera photos or scanned pages."""
    if not image_bytes_list:
        return []

    prepared: list[tuple[int, Image.Image, bytes, int]] = []
    for idx, raw_bytes in enumerate(image_bytes_list):
        pil_img = _prepare_pil_image(raw_bytes)
        scaled_img, enc_bytes, b64_bytes = _encode_image_for_batch(pil_img)
        prepared.append((idx, scaled_img, enc_bytes, b64_bytes))

    batches: list[list[tuple[int, Image.Image, bytes, int]]] = []
    current_batch: list[tuple[int, Image.Image, bytes, int]] = []
    current_b64 = 0

    for item in prepared:
        item_b64 = item[3]
        if current_batch and current_b64 + item_b64 > MAX_BATCH_BASE64_BYTES:
            batches.append(current_batch)
            current_batch = []
            current_b64 = 0
        current_batch.append(item)
        current_b64 += item_b64

    if current_batch:
        batches.append(current_batch)

    regions: list[Region] = []
    for batch in batches:
        regions.extend(_process_image_batch(batch))
    return regions
