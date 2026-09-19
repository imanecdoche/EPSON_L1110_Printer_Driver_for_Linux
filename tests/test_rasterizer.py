#!/usr/bin/env python3
"""
Unit tests for ESC/P-R Protocol Builder and Document Rasterizer.
Tests:
1. PackBits compression algorithm correctness
2. Paper geometry and pixel conversions (especially F4 / Folio)
3. Image and PDF rasterization
4. Complete print job binary generation
"""

import os
import sys
import tempfile
from PIL import Image

# Add project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.escpr_protocol import (
    packbits_encode,
    PAPER_SIZES,
    Resolution,
    ESCPRBuilder,
    MaintenanceCommands,
)
from src.core.rasterizer import DocumentRasterizer


def test_packbits():
    print("Testing PackBits Compression...")
    # Test 1: Uniform run of repeated bytes
    data = b"\xaa" * 20
    comp = packbits_encode(data)
    # Run of 20 bytes -> (257 - 20) & 0xFF = 237, followed by \xaa
    assert len(comp) == 2, f"Expected 2 bytes, got {len(comp)}"
    assert comp == bytes([(257 - 20) & 0xFF, 0xaa]), f"Unexpected output: {comp!r}"

    # Test 2: Literal bytes
    lit = b"\x01\x02\x03\x04\x05"
    comp_lit = packbits_encode(lit)
    assert comp_lit == b"\x04\x01\x02\x03\x04\x05", f"Unexpected literal output: {comp_lit!r}"

    # Test 3: Empty
    assert packbits_encode(b"") == b""
    print("[PASS] PackBits compression tests passed!")


def test_f4_dimensions():
    print("\nTesting F4 Paper Dimensions...")
    f4 = PAPER_SIZES["F4"]
    assert f4.width_mm == 215.0
    assert f4.height_mm == 330.0

    w_360, h_360 = f4.pixels(360)
    w_720, h_720 = f4.pixels(720)
    print(f"  F4 at 360 dpi : {w_360} x {h_360} px")
    print(f"  F4 at 720 dpi : {w_720} x {h_720} px")
    assert w_720 == w_360 * 2
    assert h_720 == h_360 * 2
    print("[PASS] F4 dimensions verified!")


def test_rasterizer_job_generation():
    print("\nTesting Document Rasterizer & ESC/P-R Job Generation...")
    # Create a small test image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img = Image.new("RGB", (300, 400), color=(0, 100, 200))
        img.save(tmp.name)
        img_path = tmp.name

    try:
        rasterizer = DocumentRasterizer(paper=PAPER_SIZES["F4"], resolution=Resolution.DRAFT_360)
        assert rasterizer.get_page_count(img_path) == 1

        # Test preview rendering
        preview = rasterizer.render_preview_pixmap(img_path, preview_dpi=72)
        assert preview.size[0] > 0 and preview.size[1] > 0
        print(f"  Preview image size: {preview.size}")

        # Test print job generation
        job = rasterizer.generate_print_job(img_path)
        assert len(job) > 0
        assert job.startswith(b"\x1b@\x1b(G")
        assert job.endswith(b"\x0c\x1b@")
        print(f"[PASS] Successfully generated valid ESC/P-R print job: {len(job)} bytes!")

    finally:
        if os.path.exists(img_path):
            os.unlink(img_path)


def test_maintenance_commands():
    print("\nTesting Maintenance Command Generators...")
    clean_cmd = MaintenanceCommands.head_cleaning()
    nozzle_cmd = MaintenanceCommands.nozzle_check()
    eject_cmd = MaintenanceCommands.paper_eject()

    assert b"REMOTE1CH" in clean_cmd
    assert b"REMOTE1VI" in nozzle_cmd and b"NC" in nozzle_cmd
    assert b"\x0c" in eject_cmd
    print("[PASS] Maintenance command formats verified!")


def test_print_order():
    print("\nTesting Print Order (Normal vs Reverse)...")
    import pymupdf
    # Create a 2-page PDF
    doc = pymupdf.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((100, 100), "PAGE ONE")
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((100, 100), "PAGE TWO")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        doc.save(tmp.name)
        pdf_path = tmp.name
    doc.close()

    try:
        rasterizer = DocumentRasterizer(paper=PAPER_SIZES["A4"], resolution=Resolution.DRAFT_360)
        assert rasterizer.get_page_count(pdf_path) == 2

        # Normal order
        job_normal = rasterizer.generate_print_job(pdf_path, reverse_order=False)
        assert len(job_normal) > 0

        # Reverse order
        job_reverse = rasterizer.generate_print_job(pdf_path, reverse_order=True)
        assert len(job_reverse) > 0

        print(f"  Normal print job size : {len(job_normal)} bytes")
        print(f"  Reverse print job size: {len(job_reverse)} bytes")
        print("[PASS] Print order test passed!")
    finally:
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)


def test_generate_print_pdf():
    print("\nTesting generate_print_pdf for CUPS pipeline...")
    import pymupdf
    from src.gui.worker_thread import map_paper_to_cups_pagesize

    doc = pymupdf.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 50), "PDF PAGE ONE")
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 50), "PDF PAGE TWO")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_in:
        doc.save(tmp_in.name)
        pdf_in = tmp_in.name
    doc.close()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_out:
        pdf_out = tmp_out.name

    try:
        rasterizer = DocumentRasterizer(
            paper=PAPER_SIZES["A4"],
            resolution=Resolution.DRAFT_360,
            margins_mm=(10.0, 10.0, 15.0, 15.0),
            scaling_mode="fit",
            position_offset_mm=(5.0, -5.0),
        )

        progress_called = []
        def on_prog(curr, tot):
            progress_called.append((curr, tot))

        out_path = rasterizer.generate_print_pdf(
            pdf_in,
            pdf_out,
            pages=[0, 1],
            progress_callback=on_prog,
            dpi=150,
        )
        assert os.path.exists(out_path)
        assert len(progress_called) == 2

        out_doc = pymupdf.open(out_path)
        assert len(out_doc) == 2
        print(f"  Generated multi-page print PDF with {len(out_doc)} pages at dimensions: {out_doc[0].rect}")
        out_doc.close()

        # Test PageSize mapping
        assert map_paper_to_cups_pagesize("A4 (210 x 297 mm)") == "A4"
        assert map_paper_to_cups_pagesize("F4 / Folio (215 x 330 mm)") == "Legal"
        assert map_paper_to_cups_pagesize("Letter (8.5 x 11 in)") == "Letter"
        print("[PASS] generate_print_pdf and CUPS PageSize mapping verified!")
    finally:
        if os.path.exists(pdf_in):
            os.unlink(pdf_in)
        if os.path.exists(pdf_out):
            os.unlink(pdf_out)


if __name__ == "__main__":
    test_packbits()
    test_f4_dimensions()
    test_rasterizer_job_generation()
    test_maintenance_commands()
    test_print_order()
    test_generate_print_pdf()
    print("\n========================================")
    print("ALL RASTERIZER & PROTOCOL TESTS PASSED!")
    print("========================================")

