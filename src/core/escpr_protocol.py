"""
Epson ESC/P-R Protocol Engine and Command Formatter.
Generates binary ESC/P-R streams for Epson EcoTank L1110:
- Job headers and footers
- Page setup (A4, Letter, Legal, and native F4/Folio 215x330mm)
- Resolution selection (360 dpi, 720 dpi, 1440 dpi)
- Media profiles (Plain, Matte, Photo Glossy)
- TIFF PackBits run-length compression
- Maintenance command sequences (Head Cleaning, Nozzle Check, Form Feed)
"""

from enum import Enum
from typing import Tuple, Dict, NamedTuple
import struct


class Resolution(Enum):
    DRAFT_360 = 360
    NORMAL_720 = 720
    FINE_1440 = 1440


class MediaType(Enum):
    PLAIN_PAPER = 0
    MATTE = 1
    GLOSSY = 2


class ColorMode(Enum):
    MONOCHROME = "mono"
    COLOR_CMYK = "cmyk"
    COLOR_RGB = "rgb"


class PaperSize(NamedTuple):
    name: str
    width_mm: float
    height_mm: float

    @property
    def width_inches(self) -> float:
        return self.width_mm / 25.4

    @property
    def height_inches(self) -> float:
        return self.height_mm / 25.4

    def pixels(self, dpi: int) -> Tuple[int, int]:
        return int(round(self.width_inches * dpi)), int(round(self.height_inches * dpi))


# Standard and regional paper dimensions
PAPER_SIZES: Dict[str, PaperSize] = {
    # Crucial F4 / Folio standard for Indonesian education and legal docs
    "F4": PaperSize("F4 / Folio (215 x 330 mm)", 215.0, 330.0),
    "A4": PaperSize("A4 (210 x 297 mm)", 210.0, 297.0),
    "A5": PaperSize("A5 (148 x 210 mm)", 148.0, 210.0),
    "A6": PaperSize("A6 (105 x 148 mm)", 105.0, 148.0),
    "B5": PaperSize("B5 (182 x 257 mm)", 182.0, 257.0),
    "Letter": PaperSize("Letter (8.5 x 11 in)", 215.9, 279.4),
    "Legal": PaperSize("Legal (8.5 x 14 in)", 215.9, 355.6),
    "Photo_4x6": PaperSize("Photo 4x6 in (10x15 cm)", 101.6, 152.4),
}


def packbits_encode(data: bytes) -> bytes:
    """
    Compress byte array using TIFF PackBits Run-Length Encoding (RLE).
    Used by ESC/P-R raster line commands.
    Rules:
    - Run of 2 to 128 identical bytes: byte(257 - count) + repeated_byte
    - Sequence of 1 to 128 literal bytes: byte(count - 1) + literal_bytes
    """
    if not data:
        return b""

    # Fast-path optimization: highly effective for white margins / uniform background
    if min(data) == max(data):
        val = data[0]
        n = len(data)
        out = bytearray()
        full_chunks, rem = divmod(n, 128)
        chunk_header = bytes([(257 - 128) & 0xFF, val])
        out.extend(chunk_header * full_chunks)
        if rem >= 2:
            out.extend([(257 - rem) & 0xFF, val])
        elif rem == 1:
            out.extend([0x00, val])
        return bytes(out)

    out = bytearray()
    i = 0
    n = len(data)

    while i < n:
        # Check for run of identical bytes
        run_len = 1
        while i + run_len < n and run_len < 128 and data[i + run_len] == data[i]:
            run_len += 1

        if run_len >= 3:
            # Output repeated run
            out.append((257 - run_len) & 0xFF)
            out.append(data[i])
            i += run_len
        else:
            # Look for literal sequence (up to next run of >= 3 or max 128 bytes)
            lit_start = i
            lit_len = 0
            while i < n and lit_len < 128:
                if i + 2 < n and data[i] == data[i + 1] == data[i + 2]:
                    break
                lit_len += 1
                i += 1

            if lit_len > 0:
                out.append(lit_len - 1)
                out.extend(data[lit_start:lit_start + lit_len])

    return bytes(out)


class ESCPRBuilder:
    """Builder class for constructing complete ESC/P-R binary print streams."""

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

    def generate_init(self) -> bytes:
        """Printer hardware reset and ESC/P-R mode entry sequence."""
        buf = bytearray()
        # ESC @ : Reset printer
        buf.extend(b"\x1b@")
        # Enter ESC/P-R Mode
        buf.extend(b"\x1b(G\x01\x00\x01")
        return bytes(buf)

    def generate_page_setup(self) -> bytes:
        """Page geometry, resolution, media type, and margin setup."""
        buf = bytearray()
        dpi = self.resolution.value

        # Base unit definition (1/1440 or 1/720 inch)
        base_unit = 1440
        buf.extend(b"\x1b(U\x01\x00")
        buf.append(int(1440 / base_unit))

        # Page length in base units
        page_length_units = int(round(self.paper.height_inches * base_unit))
        buf.extend(b"\x1b(C\x02\x00")
        buf.extend(struct.pack("<H", min(page_length_units, 65535)))

        # Printable top & bottom margins
        top_margin = int(round(0.12 * base_unit))  # ~3mm standard top margin
        bottom_margin = int(round((self.paper.height_inches - 0.12) * base_unit))
        buf.extend(b"\x1b(c\x04\x00")
        buf.extend(struct.pack("<HH", top_margin, min(bottom_margin, 65535)))

        return bytes(buf)

    def encode_raster_band(self, row_data: bytes, compressed: bool = True) -> bytes:
        """
        Encode a single horizontal raster line.
        ESC . <comp_flag> <v_res> <h_res> <count_l> <count_h> <data...>
        """
        buf = bytearray()
        if compressed:
            payload = packbits_encode(row_data)
            comp_flag = 0x01  # TIFF PackBits
        else:
            payload = row_data
            comp_flag = 0x00  # Uncompressed

        # ESC . command
        buf.extend(b"\x1b.")
        buf.append(comp_flag)
        # Vertical and horizontal resolution code (0x01 for 720/1440, depending on unit)
        buf.append(0x01)
        buf.append(0x01)
        buf.extend(struct.pack("<H", len(payload)))
        buf.extend(payload)
        return bytes(buf)

    def generate_footer(self) -> bytes:
        """Form Feed (page eject) and printer reset."""
        buf = bytearray()
        # Form feed: 0x0C
        buf.append(0x0C)
        # Reset printer: ESC @
        buf.extend(b"\x1b@")
        return bytes(buf)


# =====================================================================
# Maintenance Command Factory
# =====================================================================

class MaintenanceCommands:
    """Generates direct hardware maintenance sequences for Epson L1110."""

    @staticmethod
    def head_cleaning() -> bytes:
        """
        Constructs the verified binary ESC/P2 / ESC/P-R Remote Mode command for Head Cleaning.
        Exact binary sequence (tested & verified via Gutenprint protocol standard):
        - ESC @
        - ESC ( R \x08\x00 \x00 REMOTE1  (8 bytes: null prefix + 7-char REMOTE1)
        - CH \x02\x00 \x00\x00           (Clean all heads)
        - ESC \x00\x00\x00               (Exit Remote Mode)
        - ESC \x00\x0c\x1b\x00\x1b\x00   (Eject paper feed reset)
        """
        return b"\x1b@\x1b(R\x08\x00\x00REMOTE1CH\x02\x00\x00\x00\x1b\x00\x00\x00\x1b\x00\x0c\x1b\x00\x1b\x00"

    @staticmethod
    def nozzle_check() -> bytes:
        """
        Constructs the verified binary ESC/P2 / ESC/P-R Remote Mode command for Nozzle Check.
        Exact binary sequence:
        - ESC @
        - ESC ( R \x08\x00 \x00 REMOTE1
        - VI \x02\x00 \x00\x00
        - NC \x02\x00 \x00\x10
        - NC \x02\x00 \x00\x00           (Trigger 4-color nozzle check pattern)
        - ESC \x00\x00\x00
        - ESC \x00\x0c\x1b\x00\x1b\x00
        """
        return b"\x1b@\x1b(R\x08\x00\x00REMOTE1VI\x02\x00\x00\x00NC\x02\x00\x00\x10NC\x02\x00\x00\x00\x1b\x00\x00\x00\x1b\x00\x0c\x1b\x00\x1b\x00"

    @staticmethod
    def paper_eject() -> bytes:
        """Eject paper currently in feed mechanism."""
        return b"\x1b@\x0c\x1b@"
