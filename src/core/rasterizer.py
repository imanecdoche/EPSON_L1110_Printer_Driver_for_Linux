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
from PIL import Image, ImageOps
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
        margins_mm: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),  # (top, bottom, left, right)
        scaling_mode: str = "fit",  # "fit", "actual", "custom"
        scale_factor: float = 1.0,  # multiplier for custom scaling, supports negative (mirroring)
        position_offset_mm: Tuple[float, float] = (0.0, 0.0),  # (offset_x_mm, offset_y_mm)
    ):
        self.paper = paper
        self.resolution = resolution
        self.media = media
        self.color_mode = color_mode
        self.margins_mm = margins_mm
        self.scaling_mode = scaling_mode
        self.scale_factor = scale_factor
        self.position_offset_mm = position_offset_mm
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

    def get_document_page_size_mm(self, file_path: str, page_number: int = 0) -> Tuple[float, float]:
        """Returns physical dimensions of the source page in millimeters (width_mm, height_mm)."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            try:
                doc = pymupdf.open(file_path)
                if page_number < 0 or page_number >= len(doc):
                    page_number = 0
                page = doc[page_number]
                w_mm = (page.rect.width / 72.0) * 25.4
                h_mm = (page.rect.height / 72.0) * 25.4
                doc.close()
                return (w_mm, h_mm)
            except Exception:
                return (210.0, 297.0)
        elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"]:
            try:
                with Image.open(file_path) as img:
                    dpi = img.info.get("dpi", (300.0, 300.0))
                    dpi_x = float(dpi[0]) if dpi and float(dpi[0]) > 10 else 300.0
                    dpi_y = float(dpi[1]) if dpi and float(dpi[1]) > 10 else 300.0
                    w_mm = (img.width / dpi_x) * 25.4
                    h_mm = (img.height / dpi_y) * 25.4
                    return (w_mm, h_mm)
            except Exception:
                return (210.0, 297.0)
        return (210.0, 297.0)

    def get_raw_page_image(self, file_path: str, page_number: int = 0, dpi: int = 150) -> Image.Image:
        """Extracts and renders unplaced source page image at requested DPI."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            doc = pymupdf.open(file_path)
            if page_number < 0 or page_number >= len(doc):
                doc.close()
                raise IndexError(f"Page {page_number} out of range (total {len(doc)})")
            page = doc[page_number]
            zoom = dpi / 72.0
            mat = pymupdf.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc.close()
            return img
        elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"]:
            return Image.open(file_path).convert("RGB")
        else:
            raise ValueError(f"Unsupported file extension: {ext}")

    def render_page_image(
        self,
        file_path: str,
        page_number: int = 0,
        dpi: Optional[int] = None,
        margins_mm: Optional[Tuple[float, float, float, float]] = None,
        scaling_mode: Optional[str] = None,
        scale_factor: Optional[float] = None,
        position_offset_mm: Optional[Tuple[float, float]] = None,
    ) -> Image.Image:
        """
        Renders a specific page of a PDF or image into a PIL Image on the physical paper canvas.
        Handles individual 4-sided margins, scaling (fit, actual, custom with +/- step 0.2x),
        and interactive drag position offset.
        """
        effective_dpi = dpi or self.resolution.value
        page_w_px, page_h_px = self.paper.pixels(effective_dpi)

        img = self.get_raw_page_image(file_path, page_number=page_number, dpi=effective_dpi)

        # Blank canvas matching exact physical paper dimensions
        canvas = Image.new("RGB", (page_w_px, page_h_px), color=(255, 255, 255))

        # Margin calculation in pixels (1 inch = 25.4 mm)
        cur_margins = margins_mm if margins_mm is not None else self.margins_mm
        top_mm, bottom_mm, left_mm, right_mm = cur_margins

        top_px = int(round((max(0.0, float(top_mm)) / 25.4) * effective_dpi))
        bottom_px = int(round((max(0.0, float(bottom_mm)) / 25.4) * effective_dpi))
        left_px = int(round((max(0.0, float(left_mm)) / 25.4) * effective_dpi))
        right_px = int(round((max(0.0, float(right_mm)) / 25.4) * effective_dpi))

        # Usable printable bounds within margins
        printable_w = max(20, page_w_px - left_px - right_px)
        printable_h = max(20, page_h_px - top_px - bottom_px)

        cur_mode = scaling_mode or self.scaling_mode
        cur_scale = scale_factor if scale_factor is not None else self.scale_factor

        # Determine dimensions of source page
        actual_w = img.width
        actual_h = img.height
        img_ratio = actual_w / actual_h
        printable_ratio = printable_w / printable_h

        if cur_mode == "fit":
            # Scale proportionally to fit inside printable bounds
            if img_ratio > printable_ratio:
                scaled_w = printable_w
                scaled_h = max(10, int(round(printable_w / img_ratio)))
            else:
                scaled_h = printable_h
                scaled_w = max(10, int(round(printable_h * img_ratio)))
        elif cur_mode == "actual":
            # 1:1 Actual physical size
            scaled_w = max(10, actual_w)
            scaled_h = max(10, actual_h)
        elif cur_mode == "custom":
            # Custom multiplier (step 0.2x, supports negative values)
            mult = abs(cur_scale) if abs(cur_scale) >= 0.05 else 0.2
            scaled_w = max(10, int(round(actual_w * mult)))
            scaled_h = max(10, int(round(actual_h * mult)))
        else:
            scaled_w = printable_w
            scaled_h = max(10, int(round(printable_w / img_ratio)))

        scaled_img = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        # Support negative scale factor (mirror / horizontal flip)
        if cur_mode == "custom" and cur_scale < 0:
            scaled_img = ImageOps.mirror(scaled_img)

        # Positioning: centered in printable area + position_offset_mm
        cur_offset = position_offset_mm if position_offset_mm is not None else self.position_offset_mm
        offset_x_px = int(round((cur_offset[0] / 25.4) * effective_dpi))
        offset_y_px = int(round((cur_offset[1] / 25.4) * effective_dpi))

        base_x = left_px + (printable_w - scaled_w) // 2
        base_y = top_px + (printable_h - scaled_h) // 2

        pos_x = base_x + offset_x_px
        pos_y = base_y + offset_y_px

        canvas.paste(scaled_img, (pos_x, pos_y))
        return canvas

    def render_preview_pixmap(self, file_path: str, page_number: int = 0, preview_dpi: int = 150) -> Image.Image:
        """Generates a lightweight preview image suitable for display in GUI canvas."""
        return self.render_page_image(file_path, page_number=page_number, dpi=preview_dpi)

    def generate_print_job(
        self, file_path: str, pages: Optional[List[int]] = None, reverse_order: bool = False
    ) -> bytes:
        """
        Generates a complete, ready-to-stream ESC/P-R binary print job (.prn)
        for all requested pages.
        reverse_order: If True, prints from last page down to first page (N -> 1).
        """
        total_pages = self.get_page_count(file_path)
        pages_to_print = pages if pages is not None else list(range(total_pages))
        if reverse_order:
            pages_to_print = list(reversed(pages_to_print))

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


def parse_page_selection(
    mode: str,
    custom_str: str,
    total_pages: int,
) -> List[int]:
    """
    Parses page selection criteria into 0-indexed list of page indices.
    - 'all': all pages
    - 'odd': pages 1, 3, 5, ...
    - 'even': pages 2, 4, 6, ...
    - 'custom': parsed from comma-separated ranges e.g. "1, 3, 5-8"
    """
    if total_pages <= 0:
        return []

    if mode == "all":
        return list(range(total_pages))
    elif mode == "odd":
        return [i for i in range(total_pages) if (i + 1) % 2 != 0]
    elif mode == "even":
        return [i for i in range(total_pages) if (i + 1) % 2 == 0]
    elif mode == "custom":
        if not custom_str or not custom_str.strip():
            return list(range(total_pages))

        chosen: List[int] = []
        chunks = custom_str.replace(" ", "").split(",")
        for chunk in chunks:
            if not chunk:
                continue
            if "-" in chunk:
                parts = chunk.split("-")
                if len(parts) == 2:
                    try:
                        start = int(parts[0])
                        end = int(parts[1])
                        if start <= end:
                            for p in range(start, end + 1):
                                if 1 <= p <= total_pages:
                                    chosen.append(p - 1)
                        else:
                            for p in range(start, end - 1, -1):
                                if 1 <= p <= total_pages:
                                    chosen.append(p - 1)
                    except ValueError:
                        pass
            else:
                try:
                    p = int(chunk)
                    if 1 <= p <= total_pages:
                        chosen.append(p - 1)
                except ValueError:
                    pass

        # Deduplicate while preserving order
        unique_chosen = list(dict.fromkeys(chosen))
        return unique_chosen if unique_chosen else list(range(total_pages))

    return list(range(total_pages))

