# -*- coding: utf-8 -*-
"""Step 1 of the pipeline: read the genealogy report PDF.

The report was produced by "The Complete Genealogy Reporter" (MyHeritage Family
Tree Builder).  Every person carries a stable id that the report prints as a
superscript behind the name.  Plain text extraction glues that superscript onto
the name ("Bertram Ahrenholt12"), which makes the narrative ambiguous, so this
step keeps the superscripts as explicit ``{12}`` markers instead.

Outputs (into ../data/raw):
    lines.json    one record per text line, in reading order
    marked.txt    the same thing as a readable file, for eyeballing
    photos/*.jpg  every embedded portrait, named by page and position
    photos.json   bounding boxes of the portraits, for mapping them to people
"""
from __future__ import annotations

import json
import os
import sys

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# The report and everything made from it are data, and live in the data folder.
# Asked for, not created - see the note in build_data.py.
SOURCE_DIR = store.report_dir(create=False)
RAW_DIR = store.raw_dir(create=False)
PHOTO_DIR = store.build_photo_dir(create=False)

# Superscript ids are set at 7pt; body text is 10pt.
SUPERSCRIPT_MAX_SIZE = 8.5


def find_pdf() -> str:
    pdfs = [f for f in os.listdir(SOURCE_DIR) if f.lower().endswith(".pdf")]
    if not pdfs:
        raise SystemExit("Keine PDF in %s gefunden." % SOURCE_DIR)
    if len(pdfs) > 1:
        raise SystemExit("Mehrere PDFs in %s - bitte nur die Reportdatei behalten." % SOURCE_DIR)
    return os.path.join(SOURCE_DIR, pdfs[0])


def line_text(line: dict) -> str:
    out = ""
    for span in line["spans"]:
        text = span["text"]
        if span["size"] < SUPERSCRIPT_MAX_SIZE and text.strip().isdigit():
            out = out.rstrip() + "{%s}" % text.strip()
        else:
            out += text
    return out.replace("\x00", "").rstrip()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PHOTO_DIR, exist_ok=True)
    for old in os.listdir(PHOTO_DIR):
        os.remove(os.path.join(PHOTO_DIR, old))

    pdf_path = find_pdf()
    doc = pymupdf.open(pdf_path)

    lines: list[dict] = []
    photos: list[dict] = []

    for pno, page in enumerate(doc, start=1):
        page_items = []
        for block in page.get_text("dict")["blocks"]:
            if block["type"] == 1:
                continue
            for line in block["lines"]:
                page_items.append((round(line["bbox"][1], 1), round(line["bbox"][0], 1), line_text(line)))
        page_items.sort()
        for y, x, text in page_items:
            if text.strip():
                lines.append({"page": pno, "y": y, "x": x, "text": text})

        for info in page.get_image_info(xrefs=True):
            xref = info["xref"]
            if not xref:
                continue
            name = "p%03d_y%04d.jpg" % (pno, round(info["bbox"][1]))
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:      # CMYK -> RGB
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                pix.save(os.path.join(PHOTO_DIR, name), "jpeg", jpg_quality=88)
            except Exception as exc:            # pragma: no cover - defensive
                print("  Bild %s auf Seite %d nicht lesbar: %s" % (xref, pno, exc))
                continue
            photos.append({
                "file": name,
                "page": pno,
                "top": round(info["bbox"][1], 1),
                "bottom": round(info["bbox"][3], 1),
                "left": round(info["bbox"][0], 1),
                "width": info["width"],
                "height": info["height"],
            })

    with open(os.path.join(RAW_DIR, "lines.json"), "w", encoding="utf-8") as fh:
        json.dump(lines, fh, ensure_ascii=False)
    with open(os.path.join(RAW_DIR, "photos.json"), "w", encoding="utf-8") as fh:
        json.dump(photos, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(RAW_DIR, "marked.txt"), "w", encoding="utf-8") as fh:
        page = None
        for rec in lines:
            if rec["page"] != page:
                page = rec["page"]
                fh.write("\n=== SEITE %d ===\n" % page)
            fh.write(rec["text"] + "\n")

    print("Quelle : %s" % os.path.basename(pdf_path))
    print("Seiten : %d" % len(doc))
    print("Zeilen : %d" % len(lines))
    print("Fotos  : %d" % len(photos))


if __name__ == "__main__":
    main()
