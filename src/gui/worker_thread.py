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
from ..core.escpr_protocol import ColorMode
from ..core.usb_device import EpsonUSBDevice
from ..core.maintenance import MaintenanceController

logger = logging.getLogger(__name__)


def get_cups_printer_name(default: str = "EPSON-L1110-Series") -> str:
    """Returns an active Epson CUPS queue name if available."""
    try:
        res = subprocess.run(["lpstat", "-e"], capture_output=True, text=True, check=True)
        printers = [p.strip() for p in res.stdout.splitlines() if p.strip()]
        if default in printers:
            return default
        for p in printers:
            if "l1110" in p.lower() or "epson" in p.lower():
                return p
        if printers:
            return printers[0]
    except Exception:
        pass
    return default


def map_paper_to_cups_pagesize(paper_name: str) -> str:
    """Maps custom PaperSize name to standard CUPS PPD PageSize keyword."""
    name = paper_name.upper()
    if "A4" in name:
        return "A4"
    elif "A5" in name:
        return "A5"
    elif "A6" in name:
        return "A6"
    elif "B5" in name:
        return "B5"
    elif "B6" in name:
        return "B6"
    elif "LETTER" in name:
        return "Letter"
    elif "LEGAL" in name or "F4" in name or "FOLIO" in name:
        return "Legal"
    elif "PHOTO" in name or "4X6" in name:
        return "Postcard"
    return "A4"


class PrintJobWorker(QThread):
    """Asynchronously generates high-fidelity print documents and submits to CUPS queue."""

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
        self.cups_request_id: Optional[str] = None

    def cancel(self):
        """Requests worker cancellation and cancels CUPS spool if submitted."""
        self._is_cancelled = True
        if self.cups_request_id:
            try:
                subprocess.run(["cancel", self.cups_request_id], check=False)
            except Exception:
                pass

    def run(self):
        tmp_pdf_path = None
        try:
            if self._is_cancelled:
                self.job_finished.emit(self.job_id, False, "Tugas cetak dibatalkan oleh pengguna.")
                return

            self.progress_updated.emit(self.job_id, 10, "Memulai persiapan dokumen cetak...")

            total_pages = self.rasterizer.get_page_count(self.file_path)
            pages_to_print = self.pages if self.pages is not None else list(range(total_pages))
            if self.reverse_order:
                pages_to_print = list(reversed(pages_to_print))

            if not pages_to_print:
                self.job_finished.emit(self.job_id, False, "Tidak ada halaman yang dipilih untuk dicetak.")
                return

            total_selected = len(pages_to_print)
            order_desc = "Belakang ke Depan" if self.reverse_order else "Depan ke Belakang"

            # 1. Render pages with margins, scaling, and offset to high-fidelity PDF
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp_pdf_path = tmp.name

            def on_page_rendered(curr: int, tot: int):
                if self._is_cancelled:
                    return
                pct = int(15 + (curr / tot) * 60)
                self.progress_updated.emit(
                    self.job_id, pct, f"Merender halaman {curr}/{tot} ({order_desc})..."
                )

            self.rasterizer.generate_print_pdf(
                file_path=self.file_path,
                output_path=tmp_pdf_path,
                pages=pages_to_print,
                reverse_order=False,  # Already reversed above
                progress_callback=on_page_rendered,
            )

            if self._is_cancelled:
                if tmp_pdf_path and os.path.exists(tmp_pdf_path):
                    os.unlink(tmp_pdf_path)
                self.job_finished.emit(self.job_id, False, "Tugas cetak dibatalkan oleh pengguna.")
                return

            # 2. Submit to CUPS queue using official Epson ESC/P-R driver filter
            self.progress_updated.emit(self.job_id, 80, "Mengirim dokumen ke filter driver resmi Epson CUPS...")

            printer_name = self.cups_printer or get_cups_printer_name()
            cups_page_size = map_paper_to_cups_pagesize(self.rasterizer.paper.name)
            cups_ink = "MONO" if self.rasterizer.color_mode == ColorMode.MONOCHROME else "COLOR"
            cups_media = "PLAIN_NORMAL"

            cmd = [
                "lp",
                "-d", printer_name,
                "-n", str(self.copies),
                "-o", f"PageSize={cups_page_size}",
                "-o", f"MediaType={cups_media}",
                "-o", f"Ink={cups_ink}",
                "-o", "fit-to-page=false",
                tmp_pdf_path,
            ]
            logger.info(f"Submitting print job to CUPS: {' '.join(cmd)}")
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output_msg = res.stdout.strip()
            logger.info(f"CUPS submission successful: {output_msg}")

            # Extract CUPS request ID if available
            for part in output_msg.split():
                if part.startswith(f"{printer_name}-") or ("-" in part and part.split("-")[-1].isdigit()):
                    self.cups_request_id = part
                    break

            self.progress_updated.emit(self.job_id, 100, "Dokumen berhasil dikirim ke printer.")
            self.job_finished.emit(
                self.job_id,
                True,
                f"Sukses! Dokumen ({self.copies} salinan, {total_selected} halaman) berhasil dikirim ke antrean cetak {printer_name}.",
            )

        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip() if e.stderr else str(e)
            logger.error(f"CUPS error: {err_msg}")
            self.job_finished.emit(self.job_id, False, f"Gagal mencetak melalui antrean sistem CUPS: {err_msg}")
        except Exception as e:
            logger.error(f"Print error: {e}")
            self.job_finished.emit(self.job_id, False, f"Gagal mencetak dokumen: {str(e)}")
        finally:
            if tmp_pdf_path and os.path.exists(tmp_pdf_path):
                try:
                    os.unlink(tmp_pdf_path)
                except Exception:
                    pass




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
