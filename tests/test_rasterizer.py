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


if __name__ == "__main__":
    test_packbits()
    test_f4_dimensions()
    test_rasterizer_job_generation()
    test_maintenance_commands()
    print("\n========================================")
    print("ALL RASTERIZER & PROTOCOL TESTS PASSED!")
    print("========================================")
