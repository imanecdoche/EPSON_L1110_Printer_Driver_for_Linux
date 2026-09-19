"""
Epson L1110 Hardware Maintenance Controller.
Executes Print Head Cleaning, Nozzle Check Pattern, and Paper Eject.
Supports dual execution paths:
1. Direct USB via EpsonUSBDevice (fast, standalone)
2. CUPS Raw Spooler via `lp -d EPSON-L1110-Series -o raw` (fallback if udev not yet applied)
"""

import subprocess
import tempfile
import os
import logging
from typing import Optional

from .escpr_protocol import MaintenanceCommands
from .usb_device import EpsonUSBDevice

logger = logging.getLogger(__name__)


class MaintenanceController:
    """Manages hardware maintenance operations for Epson L1110."""

    def __init__(self, cups_printer_name: str = "EPSON-L1110-Series"):
        self.cups_printer_name = cups_printer_name

    def _send_raw_command(self, cmd_bytes: bytes, usb_device: Optional[EpsonUSBDevice] = None) -> bool:
        """
        Sends raw bytes to printer:
        Attempts Direct USB first; falls back to CUPS raw queue if USB permissions are not configured.
        """
        # Try direct USB
        if usb_device and usb_device.is_connected():
            try:
                usb_device.write(cmd_bytes)
                logger.info("Maintenance command sent directly via PyUSB.")
                return True
            except Exception as e:
                logger.warning(f"Direct USB write failed: {e}. Falling back to CUPS spooler...")

        # Fallback to CUPS raw printing
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".prn") as tmp:
                tmp.write(cmd_bytes)
                tmp_path = tmp.name

            cmd = ["lp", "-d", self.cups_printer_name, "-o", "raw", tmp_path]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Command sent via CUPS: {res.stdout.strip()}")
            os.unlink(tmp_path)
            return True
        except Exception as e:
            logger.error(f"Failed to send command via CUPS: {e}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise RuntimeError(f"Unable to execute maintenance command: {e}")

    def clean_head(self, usb_device: Optional[EpsonUSBDevice] = None) -> bool:
        """Triggers the hardware Print Head Cleaning cycle."""
        logger.info("Executing Print Head Cleaning...")
        cmd = MaintenanceCommands.head_cleaning()
        return self._send_raw_command(cmd, usb_device)

    def print_nozzle_check(self, usb_device: Optional[EpsonUSBDevice] = None) -> bool:
        """Prints the 4-color Nozzle Check diagnostic pattern."""
        logger.info("Executing Nozzle Check...")
        cmd = MaintenanceCommands.nozzle_check()
        return self._send_raw_command(cmd, usb_device)

    def eject_paper(self, usb_device: Optional[EpsonUSBDevice] = None) -> bool:
        """Ejects any paper currently held in the feed mechanism."""
        logger.info("Executing Paper Eject...")
        cmd = MaintenanceCommands.paper_eject()
        return self._send_raw_command(cmd, usb_device)
