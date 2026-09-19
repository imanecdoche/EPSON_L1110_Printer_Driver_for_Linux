"""
Document Rasterization Engine for Epson L1110.
Converts PDF documents and image files (PNG, JPG, TIFF) into high-resolution
bitmaps and binary ESC/P-R raster print jobs.
Supports:
- Target paper dimensions (F4, A4, Letter, Legal, etc.)
- Multi-resolution scaling (360 dpi Draft, 720 dpi Normal, 1440 dpi Fine)
- Fast rendering via PyMuPDF (fitz) and Pillow
- Color separation (Monochrome 1-bit dithering / 8-bit Grayscale / Full Color)
- Live preview image generation for PyQt6 canvas
"""

import os
from typing import List, Tuple, Optional, Generator
from PIL import Image
import pymupdf  # Official PyMuPDF import

from .escpr_protocol import (
    ESCPRBuilder,
    PaperSize,
    Resolution,
    MediaType,
    ColorMode,
    PAPER_SIZES,
)


class DocumentRasterizer:
    """Renders documents (PDF, images) into raster data for printing and GUI preview."""

    def __init__(
        self,
        paper: PaperSize = PAPER_SIZES["F4"],
        resolution: Resolution = Resolution.NORMAL_720,
        media: MediaType = MediaType.PLAIN_PAPER,
        color_mode: ColorMode = ColorMode.COLOR_CMYK,
    ):
        self.paper = paper
        self.resolution = resolution
        self.media = media
        self.color_mode = color_mode
        self.builder = ESCPRBuilder(paper, resolution, media, color_mode)

    @property
    def target_pixel_dimensions(self) -> Tuple[int, int]:
        """Calculates exact width and height in pixels for the current paper and DPI."""
        return self.paper.pixels(self.resolution.value)

    def get_page_count(self, file_path: str) -> int:
        """Return the number of pages in the given document."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            doc = pymupdf.open(file_path)
            count = len(doc)
            doc.close()
            return count
        elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"]:
            return 1
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def render_page_image(
        self, file_path: str, page_number: int = 0, dpi: Optional[int] = None
    ) -> Image.Image:
        """
        Renders a specific page of a PDF or image into a PIL Image.
        Scales to the physical paper size maintaining aspect ratio, centered on page.
        """
        effective_dpi = dpi or self.resolution.value
        page_w_px, page_h_px = self.paper.pixels(effective_dpi)

        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            doc = pymupdf.open(file_path)
            if page_number < 0 or page_number >= len(doc):
                doc.close()
                raise IndexError(f"Page {page_number} out of range (total {len(doc)})")

            page = doc[page_number]
            # Calculate zoom matrix to match target DPI (PDF base is 72 dpi)
            zoom = effective_dpi / 72.0
            mat = pymupdf.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc.close()

        elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"]:
            img = Image.open(file_path).convert("RGB")
        else:
            raise ValueError(f"Unsupported file extension: {ext}")

        # Create blank canvas matching exact physical paper dimensions
        canvas = Image.new("RGB", (page_w_px, page_h_px), color=(255, 255, 255))

        # Calculate best-fit dimensions maintaining aspect ratio
        img_ratio = img.width / img.height
        canvas_ratio = page_w_px / page_h_px

        if img_ratio > canvas_ratio:
            # Fit to width
            scaled_w = page_w_px
            scaled_h = int(round(page_w_px / img_ratio))
        else:
            # Fit to height
            scaled_h = page_h_px
            scaled_w = int(round(page_h_px * img_ratio))

        scaled_img = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        # Center on canvas
        pos_x = (page_w_px - scaled_w) // 2
        pos_y = (page_h_px - scaled_h) // 2
        canvas.paste(scaled_img, (pos_x, pos_y))

        return canvas

    def render_preview_pixmap(self, file_path: str, page_number: int = 0, preview_dpi: int = 150) -> Image.Image:
        """Generates a lightweight preview image suitable for display in GUI canvas."""
        return self.render_page_image(file_path, page_number=page_number, dpi=preview_dpi)

    def generate_print_job(self, file_path: str, pages: Optional[List[int]] = None) -> bytes:
        """
        Generates a complete, ready-to-stream ESC/P-R binary print job (.prn)
        for all requested pages.
        """
        total_pages = self.get_page_count(file_path)
        pages_to_print = pages if pages is not None else list(range(total_pages))

        job_data = bytearray()
        job_data.extend(self.builder.generate_init())

        for p in pages_to_print:
            job_data.extend(self.builder.generate_page_setup())
            page_img = self.render_page_image(file_path, page_number=p)

            # Process raster rows
            if self.color_mode == ColorMode.MONOCHROME:
                # Convert to 1-bit dithered image (Floyd-Steinberg)
                mono_img = page_img.convert("1")
                width, height = mono_img.size
                row_bytes_len = (width + 7) // 8

                for y in range(height):
                    # Extract 1-bit row bytes
                    row_box = (0, y, width, y + 1)
                    row_slice = mono_img.crop(row_box)
                    raw_row = row_slice.tobytes()
                    job_data.extend(self.builder.encode_raster_band(raw_row, compressed=True))
            else:
                # Color RGB / CMYK raster stream
                # For basic ESC/P-R color band: 8-bit RGB lines
                width, height = page_img.size
                raw_bytes = page_img.tobytes()
                stride = width * 3

                for y in range(height):
                    row_data = raw_bytes[y * stride : (y + 1) * stride]
                    job_data.extend(self.builder.encode_raster_band(row_data, compressed=True))

            # Page footer (Form Feed)
            job_data.extend(self.builder.generate_footer())

        return bytes(job_data)
