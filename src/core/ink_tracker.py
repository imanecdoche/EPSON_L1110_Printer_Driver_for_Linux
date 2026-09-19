"""
Persistent Ink Consumption Tracker and Manager for Epson EcoTank L1110.
Tracks ink usage across print jobs with mathematical precision based on:
- ISO 24712 / 24711 standard EcoTank yields (~4,500 pages BK, ~7,500 pages CMY for 65ml bottle)
- Color Mode (Monochrome uses only BK; CMYK uses all 4 channels)
- Print Resolution scaling (Draft uses less, Fine/Photo uses more)
- Persistent JSON storage in ~/.config/epson-l1110/ink_levels.json
- Manual calibration interface to sync with physical bottle liquid height
"""

import os
import json
import logging
from typing import Dict
from .escpr_protocol import ColorMode, Resolution

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.expanduser("~/.config/epson-l1110")
CONFIG_FILE = os.path.join(CONFIG_DIR, "ink_levels.json")

# Standard Epson 003 EcoTank bottle yields (~65ml)
# BK bottle yields ~4,500 pages at 5% coverage
# CMY bottles yield ~7,500 composite pages
BK_PER_PAGE_PCT = 100.0 / 4500.0   # ~0.0222% per normal page
COLOR_PER_PAGE_PCT = 100.0 / 7500.0 # ~0.0133% per normal page


class InkTracker:
    """Manages persistent and real-time ink consumption."""

    def __init__(self):
        self.levels: Dict[str, float] = {
            "BK": 85.0,
            "C": 75.0,
            "M": 70.0,
            "Y": 80.0,
        }
        self.load()

    def load(self):
        """Loads saved ink levels from local config."""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    saved = json.load(f)
                    for k in ["BK", "C", "M", "Y"]:
                        if k in saved:
                            self.levels[k] = float(max(0.0, min(100.0, saved[k])))
        except Exception as e:
            logger.warning(f"Could not load ink levels from {CONFIG_FILE}: {e}")

    def save(self):
        """Saves current ink levels to local config."""
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, "w") as f:
                json.dump({k: round(v, 2) for k, v in self.levels.items()}, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save ink levels to {CONFIG_FILE}: {e}")

    def get_levels(self) -> Dict[str, int]:
        """Returns integer percentages for UI gauges."""
        return {k: int(round(v)) for k, v in self.levels.items()}

    def set_levels(self, bk: float, c: float, m: float, y: float):
        """Manual calibration to match visual physical tank liquid levels."""
        self.levels["BK"] = max(0.0, min(100.0, float(bk)))
        self.levels["C"] = max(0.0, min(100.0, float(c)))
        self.levels["M"] = max(0.0, min(100.0, float(m)))
        self.levels["Y"] = max(0.0, min(100.0, float(y)))
        self.save()

    def consume_print_job(
        self,
        pages: int,
        color_mode: ColorMode = ColorMode.COLOR_CMYK,
        resolution: Resolution = Resolution.NORMAL_720,
    ):
        """
        Deducts consumed ink dynamically based on printed page count and settings.
        """
        # Multipliers based on resolution
        res_multiplier = {
            Resolution.DRAFT_360: 0.6,
            Resolution.NORMAL_720: 1.0,
            Resolution.FINE_1440: 2.2,
        }.get(resolution, 1.0)

        if color_mode == ColorMode.MONOCHROME:
            # Only black is consumed
            bk_used = pages * BK_PER_PAGE_PCT * res_multiplier
            self.levels["BK"] = max(0.0, self.levels["BK"] - bk_used)
        else:
            # Full CMYK consumed
            bk_used = pages * BK_PER_PAGE_PCT * res_multiplier * 0.7
            c_used = pages * COLOR_PER_PAGE_PCT * res_multiplier
            m_used = pages * COLOR_PER_PAGE_PCT * res_multiplier
            y_used = pages * COLOR_PER_PAGE_PCT * res_multiplier

            self.levels["BK"] = max(0.0, self.levels["BK"] - bk_used)
            self.levels["C"] = max(0.0, self.levels["C"] - c_used)
            self.levels["M"] = max(0.0, self.levels["M"] - m_used)
            self.levels["Y"] = max(0.0, self.levels["Y"] - y_used)

        self.save()

    def consume_head_cleaning(self):
        """Head cleaning uses ~1.5% to 2.5% of each ink tank to flush nozzles."""
        for k in self.levels:
            self.levels[k] = max(0.0, self.levels[k] - 1.8)
        self.save()
