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
from typing import Optional, List

from ..core.rasterizer import DocumentRasterizer
from ..core.usb_device import EpsonUSBDevice
from ..core.maintenance import MaintenanceController

logger = logging.getLogger(__name__)


class PrintJobWorker(QThread):
    """Asynchronously generates ESC/P-R print jobs and streams to printer."""

    progress_updated = pyqtSignal(str, int, str)  # (job_id, percent, message)
    job_finished = pyqtSignal(str, bool, str)     # (job_id, success, message)

    def __init__(
        self,
        file_path: str,
        rasterizer: DocumentRasterizer,
        copies: int = 1,
        reverse_order: bool = False,
        usb_device: Optional[EpsonUSBDevice] = None,
        cups_printer: str = "EPSON-L1110-Series",
        job_id: str = "#1",
        pages: Optional[List[int]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.file_path = file_path
        self.rasterizer = rasterizer
        self.copies = max(1, copies)
        self.reverse_order = reverse_order
        self.usb_device = usb_device
        self.cups_printer = cups_printer
        self.job_id = job_id
        self.pages = pages
        self._is_cancelled = False

    def cancel(self):
        """Requests worker cancellation."""
        self._is_cancelled = True

    def run(self):
        try:
            if self._is_cancelled:
                self.job_finished.emit(self.job_id, False, "Tugas cetak dibatalkan oleh pengguna.")
                return

            self.progress_updated.emit(self.job_id, 10, "Memulai proses rasterisasi dokumen...")

            # 1. Generate ESC/P-R binary print job
            order_desc = "Belakang ke Depan (Reverse)" if self.reverse_order else "Depan ke Belakang (Normal)"
            self.progress_updated.emit(self.job_id, 30, f"Merender halaman [{order_desc}] dan kompresi PackBits...")
            job_bytes = self.rasterizer.generate_print_job(
                self.file_path, pages=self.pages, reverse_order=self.reverse_order
            )

            if self._is_cancelled:
                self.job_finished.emit(self.job_id, False, "Tugas cetak dibatalkan oleh pengguna.")
                return

            self.progress_updated.emit(self.job_id, 70, f"Aliran data biner siap ({len(job_bytes):,} bytes)...")

            # 2. Transmit to printer
            sent = False
            # Path A: Direct USB
            if self.usb_device and self.usb_device.is_connected():
                self.progress_updated.emit(self.job_id, 85, "Mengirim langsung via port USB bulk...")
                for c in range(self.copies):
                    if self._is_cancelled:
                        self.job_finished.emit(self.job_id, False, "Tugas cetak dibatalkan saat transmisi data.")
                        return
                    self.usb_device.write(job_bytes)
                sent = True

            # Path B: Fallback via CUPS raw spooler
            if not sent:
                self.progress_updated.emit(self.job_id, 85, f"Mengirim {self.copies} salinan via antrean cetak sistem...")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".prn") as tmp:
                    tmp.write(job_bytes)
                    tmp_path = tmp.name

                for c in range(self.copies):
                    if self._is_cancelled:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                        self.job_finished.emit(self.job_id, False, "Tugas cetak dibatalkan saat pengiriman.")
                        return
                    cmd = ["lp", "-d", self.cups_printer, "-o", "raw", tmp_path]
                    subprocess.run(cmd, capture_output=True, text=True, check=True)

                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            self.progress_updated.emit(self.job_id, 100, "Dokumen berhasil dikirim ke printer.")
            self.job_finished.emit(self.job_id, True, f"Sukses! Dokumen ({self.copies} salinan) berhasil dikirim ke Epson L1110.")

        except Exception as e:
            logger.error(f"Print error: {e}")
            self.job_finished.emit(self.job_id, False, f"Gagal mencetak dokumen: {str(e)}")



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
