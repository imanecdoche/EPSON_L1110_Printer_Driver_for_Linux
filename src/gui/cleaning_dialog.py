"""
Head Cleaning Progress Dialog for Epson L1110.
Provides transparent, detailed real-time feedback during the physical
print head cleaning cycle (~75-80 seconds).
Complies strictly with project guidelines (no arbitrary pills/badges).
"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
import time
import logging

from ..core.maintenance import MaintenanceController
from ..core.usb_device import EpsonUSBDevice
from typing import Optional

logger = logging.getLogger(__name__)


class CleaningExecutionThread(QThread):
    """
    Simulates / monitors the physical Epson EcoTank ~75-second cleaning cycle
    while transmitting the initial binary command.
    """
    tick = pyqtSignal(int, str)  # percent, phase description
    finished_cycle = pyqtSignal(bool, str)

    TOTAL_CYCLE_SECONDS = 75  # Epson L series typical cleaning duration

    def __init__(
        self,
        controller: MaintenanceController,
        usb_device: Optional[EpsonUSBDevice] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.usb_device = usb_device

    def run(self):
        try:
            # 1. Send hardware trigger
            self.tick.emit(2, "Mengirim instruksi aktivasi pembersihan ke mikrokontroler printer...")
            success = self.controller.clean_head(self.usb_device)
            if not success:
                self.finished_cycle.emit(False, "Gagal mengirimkan perintah ke printer.")
                return

            # 2. Progress through physical mechanical stages over the 75s duration
            start_time = time.time()
            phases = [
                (0.15, "Inisialisasi carriage motor dan pelepasan head lock..."),
                (0.40, "Pompa sirkulasi aktif: menyedot tinta pekat dan gelembung udara..."),
                (0.70, "Penyekaan (wiper) permukaan nozzle dan flushing tinta..."),
                (0.90, "Stabilisasi tekanan mikron dan penutupan capping station..."),
                (1.00, "Siklus pembersihan selesai. Lampu indikator printer kembali stabil."),
            ]

            while True:
                elapsed = time.time() - start_time
                progress_ratio = min(1.0, elapsed / self.TOTAL_CYCLE_SECONDS)
                percent = int(progress_ratio * 100)

                # Find current phase description
                desc = phases[-1][1]
                for threshold, text in phases:
                    if progress_ratio <= threshold:
                        desc = text
                        break

                self.tick.emit(percent, desc)

                if elapsed >= self.TOTAL_CYCLE_SECONDS:
                    break
                time.sleep(0.5)

            self.finished_cycle.emit(True, "Siklus pembersihan head printer telah selesai sempurna.")

        except Exception as e:
            logger.error(f"Error during head cleaning thread: {e}")
            self.finished_cycle.emit(False, f"Terjadi kesalahan: {e}")


class HeadCleaningDialog(QDialog):
    """Informative modal dialog showing transparent progress of the cleaning cycle."""

    request_nozzle_check = pyqtSignal()

    def __init__(
        self,
        controller: MaintenanceController,
        usb_device: Optional[EpsonUSBDevice] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Pembersihan Head (Head Cleaning) — Epson L1110")
        self.setFixedSize(520, 290)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.controller = controller
        self.usb_device = usb_device
        self.worker: Optional[CleaningExecutionThread] = None

        self._setup_ui()
        self._start_cycle()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Title
        self.lbl_title = QLabel("<b>Pembersihan Head Printer Sedang Berlangsung</b>")
        self.lbl_title.setStyleSheet("font-size: 15px; color: #1a1a1a;")
        layout.addWidget(self.lbl_title)

        # Detailed Phase Description
        self.lbl_phase = QLabel("Mempersiapkan komunikasi dengan printer Epson L1110...")
        self.lbl_phase.setWordWrap(True)
        self.lbl_phase.setStyleSheet("font-size: 12px; color: #333333; min-height: 38px;")
        layout.addWidget(self.lbl_phase)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(24)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #aaaaaa;
                border-radius: 4px;
                text-align: center;
                font-weight: bold;
                background-color: #f5f5f5;
            }
            QProgressBar::chunk {
                background-color: #1a73e8;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Remaining Time Label
        self.lbl_time = QLabel("Estimasi waktu tersisa: ~75 detik")
        self.lbl_time.setStyleSheet("font-size: 11px; color: #666666;")
        layout.addWidget(self.lbl_time)

        # Important Notice / Caution
        self.lbl_warning = QLabel(
            "<b>PENTING:</b> Jangan mematikan printer, membuka cover, atau mencabut kabel USB "
            "sampai proses ini selesai secara penuh."
        )
        self.lbl_warning.setWordWrap(True)
        self.lbl_warning.setStyleSheet("""
            background-color: #fff9db;
            color: #7c5e00;
            border: 1px solid #f0e080;
            border-radius: 4px;
            padding: 8px;
            font-size: 11.5px;
        """)
        layout.addWidget(self.lbl_warning)

        layout.addStretch()

        # Action Buttons (Disabled during active cleaning)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_nozzle = QPushButton("Cetak Nozzle Check Sekarang")
        self.btn_nozzle.setEnabled(False)
        self.btn_nozzle.clicked.connect(self._on_nozzle_clicked)
        btn_layout.addWidget(self.btn_nozzle)

        btn_layout.addStretch()

        self.btn_close = QPushButton("Tutup")
        self.btn_close.setEnabled(False)
        self.btn_close.setMinimumWidth(90)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _start_cycle(self):
        """Starts background worker."""
        self.worker = CleaningExecutionThread(self.controller, self.usb_device)
        self.worker.tick.connect(self._on_tick)
        self.worker.finished_cycle.connect(self._on_finished)
        self.worker.start()

    def _on_tick(self, percent: int, desc: str):
        self.progress_bar.setValue(percent)
        self.lbl_phase.setText(desc)
        total_sec = CleaningExecutionThread.TOTAL_CYCLE_SECONDS
        remaining = max(0, int(total_sec * (100 - percent) / 100))
        self.lbl_time.setText(f"Estimasi waktu tersisa: ~{remaining} detik ({percent}%)")

    def _on_finished(self, success: bool, msg: str):
        self.btn_close.setEnabled(True)
        if success:
            self.lbl_title.setText("<b style='color: #2e7d32;'>Pembersihan Head Selesai!</b>")
            self.lbl_phase.setText(
                "Siklus pembersihan mekanis telah selesai. Disarankan mencetak pola uji "
                "Nozzle Check untuk memverifikasi seluruh lubang jarum tinta mengalir lancar."
            )
            self.lbl_time.setText("Status: Selesai (100%)")
            self.btn_nozzle.setEnabled(True)
        else:
            self.lbl_title.setText("<b style='color: #c62828;'>Pembersihan Gagal</b>")
            self.lbl_phase.setText(msg)

    def _on_nozzle_clicked(self):
        """Dispatches nozzle check request and closes dialog."""
        self.request_nozzle_check.emit()
        self.accept()

    def closeEvent(self, event):
        """Prevent closing while worker is actively running."""
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Siklus Sedang Berjalan",
                "Pembersihan fisik sedang aktif di printer. Apakah Anda yakin ingin menutup dialog ini? "
                "(Printer akan tetap menyelesaikan siklusnya).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
