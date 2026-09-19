"""
Asynchronous Worker Threads for Epson L1110 Operations.
Keeps GUI completely responsive during document rasterization, USB streaming,
and hardware maintenance commands.
"""

from PyQt6.QtCore import QThread, pyqtSignal
import subprocess
import tempfile
import os
import logging
from typing import Optional

from ..core.rasterizer import DocumentRasterizer
from ..core.usb_device import EpsonUSBDevice
from ..core.maintenance import MaintenanceController

logger = logging.getLogger(__name__)


class PrintJobWorker(QThread):
    """Asynchronously generates ESC/P-R print jobs and streams to printer."""

    progress_updated = pyqtSignal(int, str)  # (percent, message)
    job_finished = pyqtSignal(bool, str)     # (success, message)

    def __init__(
        self,
        file_path: str,
        rasterizer: DocumentRasterizer,
        copies: int = 1,
        usb_device: Optional[EpsonUSBDevice] = None,
        cups_printer: str = "EPSON-L1110-Series",
        parent=None,
    ):
        super().__init__(parent)
        self.file_path = file_path
        self.rasterizer = rasterizer
        self.copies = max(1, copies)
        self.usb_device = usb_device
        self.cups_printer = cups_printer

    def run(self):
        try:
            self.progress_updated.emit(10, "Memulai proses rasterisasi dokumen...")

            # 1. Generate ESC/P-R binary print job
            self.progress_updated.emit(30, "Merender halaman dan kompresi PackBits...")
            job_bytes = self.rasterizer.generate_print_job(self.file_path)

            self.progress_updated.emit(70, f"Aliran data biner siap ({len(job_bytes):,} bytes)...")

            # 2. Transmit to printer
            sent = False
            # Path A: Direct USB
            if self.usb_device and self.usb_device.is_connected():
                self.progress_updated.emit(85, "Mengirim langsung via port USB bulk...")
                for c in range(self.copies):
                    self.usb_device.write(job_bytes)
                sent = True

            # Path B: Fallback via CUPS raw spooler
            if not sent:
                self.progress_updated.emit(85, f"Mengirim {self.copies} salinan via antrean cetak sistem...")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".prn") as tmp:
                    tmp.write(job_bytes)
                    tmp_path = tmp.name

                for c in range(self.copies):
                    cmd = ["lp", "-d", self.cups_printer, "-o", "raw", tmp_path]
                    subprocess.run(cmd, capture_output=True, text=True, check=True)

                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            self.progress_updated.emit(100, "Dokumen berhasil dikirim ke printer.")
            self.job_finished.emit(True, f"Sukses! Dokumen ({self.copies} salinan) berhasil dikirim ke Epson L1110.")

        except Exception as e:
            logger.error(f"Print error: {e}")
            self.job_finished.emit(False, f"Gagal mencetak dokumen: {str(e)}")


class MaintenanceWorker(QThread):
    """Asynchronously executes maintenance commands."""

    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        action: str,  # "clean", "nozzle", "eject"
        controller: MaintenanceController,
        usb_device: Optional[EpsonUSBDevice] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.action = action
        self.controller = controller
        self.usb_device = usb_device

    def run(self):
        try:
            if self.action == "clean":
                self.controller.clean_head(self.usb_device)
                self.finished.emit(True, "Siklus Head Cleaning berhasil dikirim ke printer.")
            elif self.action == "nozzle":
                self.controller.print_nozzle_check(self.usb_device)
                self.finished.emit(True, "Pola Nozzle Check berhasil dikirim ke printer.")
            elif self.action == "eject":
                self.controller.eject_paper(self.usb_device)
                self.finished.emit(True, "Perintah Paper Eject berhasil dijalankan.")
            else:
                self.finished.emit(False, f"Aksi tidak dikenal: {self.action}")
        except Exception as e:
            self.finished.emit(False, f"Gagal mengeksekusi pemeliharaan: {e}")
