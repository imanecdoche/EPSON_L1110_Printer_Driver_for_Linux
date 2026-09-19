"""
Main Application Window for Epson L1110 Driver & Control Center.
Three-panel functional layout:
- Left: Print job settings (F4/Folio default, Resolution, Media, Copies)
- Center: Document preview canvas with pagination & zoom
- Right: Ink tank gauges & hardware maintenance suite
Adheres strictly to workspace rules (functional UI, no arbitrary pills/badges).
"""

import os
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QFileDialog,
    QMessageBox,
    QProgressBar,
    QStatusBar,
)
from PyQt6.QtCore import Qt
from typing import Optional

from ..core.escpr_protocol import (
    PAPER_SIZES,
    Resolution,
    MediaType,
    ColorMode,
    PaperSize,
)
from ..core.rasterizer import DocumentRasterizer
from ..core.maintenance import MaintenanceController
from ..core.usb_device import EpsonUSBDevice
from .ink_widget import InkLevelWidget
from .preview_widget import PreviewWidget
from .worker_thread import PrintJobWorker, MaintenanceWorker
from .cleaning_dialog import HeadCleaningDialog


class MainWindow(QMainWindow):
    """Main window of the Epson L1110 Driver & Control Center."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Epson EcoTank L1110 — Control Center & Driver")
        self.resize(1150, 720)
        self.setMinimumSize(950, 600)

        # Core controllers
        self.maintenance_controller = MaintenanceController()
        self.usb_device: Optional[EpsonUSBDevice] = None
        self.current_file_path: Optional[str] = None
        self.active_print_worker: Optional[PrintJobWorker] = None
        self.active_maint_worker: Optional[MaintenanceWorker] = None

        self._init_usb_connection()
        self._setup_ui()

    def _init_usb_connection(self):
        """Attempts to discover USB printer."""
        try:
            self.usb_device = EpsonUSBDevice()
            self.usb_device.connect()
        except Exception:
            # If direct USB claim fails (e.g. udev not yet active), keep as None;
            # operations will gracefully fallback to CUPS raw queue
            self.usb_device = None

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # -------------------------------------------------------------
        # 1. LEFT PANEL: Print Settings
        # -------------------------------------------------------------
        panel_left = QGroupBox("Pengaturan Cetak")
        panel_left.setFixedWidth(280)
        left_layout = QVBoxLayout(panel_left)
        left_layout.setContentsMargins(10, 14, 10, 10)
        left_layout.setSpacing(10)

        # File Chooser
        lbl_doc_title = QLabel("<b>Dokumen Sumber:</b>")
        left_layout.addWidget(lbl_doc_title)

        self.btn_select_file = QPushButton("Pilih Berkas (PDF / Gambar)...")
        self.btn_select_file.setMinimumHeight(32)
        self.btn_select_file.clicked.connect(self._select_file)
        left_layout.addWidget(self.btn_select_file)

        self.lbl_selected_file = QLabel("Belum ada berkas dipilih")
        self.lbl_selected_file.setStyleSheet("color: #666666; font-size: 11px;")
        self.lbl_selected_file.setWordWrap(True)
        left_layout.addWidget(self.lbl_selected_file)

        left_layout.addSpacing(6)

        # Paper Size Selection (Default: F4 / Folio)
        lbl_paper = QLabel("<b>Ukuran Kertas:</b>")
        left_layout.addWidget(lbl_paper)
        self.combo_paper = QComboBox()
        # Add F4 as primary default
        for key, psize in PAPER_SIZES.items():
            self.combo_paper.addItem(psize.name, userData=key)
        self.combo_paper.setCurrentIndex(0)  # F4 is at index 0
        self.combo_paper.currentIndexChanged.connect(self._on_settings_changed)
        left_layout.addWidget(self.combo_paper)

        # Resolution Selection
        lbl_dpi = QLabel("<b>Kualitas & Resolusi Cetak:</b>")
        left_layout.addWidget(lbl_dpi)
        self.combo_dpi = QComboBox()
        self.combo_dpi.addItem("Normal / Standar (720 DPI)", userData=Resolution.NORMAL_720)
        self.combo_dpi.addItem("Draf Cepat Hemat Tinta (360 DPI)", userData=Resolution.DRAFT_360)
        self.combo_dpi.addItem("Tinggi / Foto Halus (1440 DPI)", userData=Resolution.FINE_1440)
        self.combo_dpi.currentIndexChanged.connect(self._on_settings_changed)
        left_layout.addWidget(self.combo_dpi)

        # Media Type
        lbl_media = QLabel("<b>Jenis Media Kertas:</b>")
        left_layout.addWidget(lbl_media)
        self.combo_media = QComboBox()
        self.combo_media.addItem("Kertas Biasa (Plain Paper)", userData=MediaType.PLAIN_PAPER)
        self.combo_media.addItem("Kertas Matte", userData=MediaType.MATTE)
        self.combo_media.addItem("Kertas Foto Glossy", userData=MediaType.GLOSSY)
        left_layout.addWidget(self.combo_media)

        # Color Mode
        lbl_color = QLabel("<b>Mode Warna:</b>")
        left_layout.addWidget(lbl_color)
        self.combo_color = QComboBox()
        self.combo_color.addItem("Berwarna (Full CMYK)", userData=ColorMode.COLOR_CMYK)
        self.combo_color.addItem("Monokrom (Hitam Putih Murni)", userData=ColorMode.MONOCHROME)
        left_layout.addWidget(self.combo_color)

        # Copies Count
        lbl_copies = QLabel("<b>Jumlah Salinan (Copies):</b>")
        left_layout.addWidget(lbl_copies)
        self.spin_copies = QSpinBox()
        self.spin_copies.setRange(1, 99)
        self.spin_copies.setValue(1)
        left_layout.addWidget(self.spin_copies)

        # Print Order (Normal vs Reverse)
        lbl_order = QLabel("<b>Urutan Cetak (Print Order):</b>")
        left_layout.addWidget(lbl_order)
        self.combo_order = QComboBox()
        self.combo_order.addItem("Normal (Depan ke Belakang: 1 → Akhir)", userData=False)
        self.combo_order.addItem("Reverse (Belakang ke Depan: Akhir → 1)", userData=True)
        left_layout.addWidget(self.combo_order)

        left_layout.addStretch()

        # Print Button
        self.btn_print = QPushButton("Cetak Dokumen")
        self.btn_print.setMinimumHeight(44)
        self.btn_print.setStyleSheet("""
            QPushButton {
                background-color: #1a5fb4;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1c71d8;
            }
            QPushButton:disabled {
                background-color: #999999;
            }
        """)
        self.btn_print.setEnabled(False)
        self.btn_print.clicked.connect(self._start_print_job)
        left_layout.addWidget(self.btn_print)

        main_layout.addWidget(panel_left)

        # -------------------------------------------------------------
        # 2. CENTER PANEL: Document Preview Canvas
        # -------------------------------------------------------------
        self.preview_widget = PreviewWidget()
        main_layout.addWidget(self.preview_widget, stretch=1)

        # -------------------------------------------------------------
        # 3. RIGHT PANEL: Status & Maintenance
        # -------------------------------------------------------------
        panel_right = QWidget()
        panel_right.setFixedWidth(280)
        right_layout = QVBoxLayout(panel_right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Status Group
        grp_status = QGroupBox("Status Perangkat")
        status_box = QVBoxLayout(grp_status)
        status_box.setContentsMargins(10, 12, 10, 10)
        status_box.setSpacing(6)

        self.lbl_device_status = QLabel("Printer: <b>Epson EcoTank L1110</b>")
        status_box.addWidget(self.lbl_device_status)

        conn_text = "Jalur: Direct USB (Siap)" if self.usb_device else "Jalur: CUPS Spooler (Siap)"
        self.lbl_conn_status = QLabel(conn_text)
        self.lbl_conn_status.setStyleSheet("color: #2e7d32; font-size: 12px;")
        status_box.addWidget(self.lbl_conn_status)

        right_layout.addWidget(grp_status)

        # Ink Widget
        self.ink_widget = InkLevelWidget()
        right_layout.addWidget(self.ink_widget)

        # Maintenance Group
        grp_maint = QGroupBox("Pusat Pemeliharaan (Maintenance)")
        maint_layout = QVBoxLayout(grp_maint)
        maint_layout.setContentsMargins(10, 12, 10, 10)
        maint_layout.setSpacing(8)

        self.btn_clean = QPushButton("Pembersihan Head (Head Cleaning)")
        self.btn_clean.clicked.connect(lambda: self._trigger_maintenance("clean"))
        maint_layout.addWidget(self.btn_clean)

        self.btn_nozzle = QPushButton("Cetak Pola Nozzle Check")
        self.btn_nozzle.clicked.connect(lambda: self._trigger_maintenance("nozzle"))
        maint_layout.addWidget(self.btn_nozzle)

        self.btn_eject = QPushButton("Keluarkan Kertas (Paper Eject)")
        self.btn_eject.clicked.connect(lambda: self._trigger_maintenance("eject"))
        maint_layout.addWidget(self.btn_eject)

        right_layout.addWidget(grp_maint)
        right_layout.addStretch()

        main_layout.addWidget(panel_right)

        # -------------------------------------------------------------
        # 4. STATUS BAR & PROGRESS
        # -------------------------------------------------------------
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

        self.status_bar.showMessage("Siap — Sistem siap menerima instruksi cetak.")

    def _get_current_rasterizer(self) -> DocumentRasterizer:
        """Constructs DocumentRasterizer according to selected UI options."""
        paper_key = self.combo_paper.currentData()
        paper = PAPER_SIZES.get(paper_key, PAPER_SIZES["F4"])
        dpi = self.combo_dpi.currentData()
        media = self.combo_media.currentData()
        color = self.combo_color.currentData()

        return DocumentRasterizer(paper=paper, resolution=dpi, media=media, color_mode=color)

    def _select_file(self):
        """Open file dialog for PDF and image documents."""
        file_filter = "Dokumen Cetak (*.pdf *.png *.jpg *.jpeg *.bmp *.tiff);;Berkas PDF (*.pdf);;Gambar (*.png *.jpg *.jpeg)"
        path, _ = QFileDialog.getOpenFileName(self, "Pilih Berkas Dokumen", "", file_filter)
        if path:
            self.current_file_path = path
            self.lbl_selected_file.setText(os.path.basename(path))
            self.btn_print.setEnabled(True)
            self._update_preview()

    def _on_settings_changed(self):
        """Triggered when paper or resolution changes."""
        if self.current_file_path:
            self._update_preview()

    def _update_preview(self):
        """Re-renders the document preview canvas."""
        if not self.current_file_path:
            return
        rasterizer = self._get_current_rasterizer()
        self.preview_widget.load_document(self.current_file_path, rasterizer)

    def _start_print_job(self):
        """Dispatches print job to asynchronous background thread."""
        if not self.current_file_path:
            return

        rasterizer = self._get_current_rasterizer()
        copies = self.spin_copies.value()
        reverse_order = bool(self.combo_order.currentData())

        # UI state
        self.btn_print.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        self.active_print_worker = PrintJobWorker(
            file_path=self.current_file_path,
            rasterizer=rasterizer,
            copies=copies,
            reverse_order=reverse_order,
            usb_device=self.usb_device,
        )
        self.active_print_worker.progress_updated.connect(self._on_print_progress)
        self.active_print_worker.job_finished.connect(self._on_print_finished)
        self.active_print_worker.start()

    def _on_print_progress(self, percent: int, msg: str):
        self.progress_bar.setValue(percent)
        self.status_bar.showMessage(msg)

    def _on_print_finished(self, success: bool, msg: str):
        self.btn_print.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(msg)

        if success:
            QMessageBox.information(self, "Pencetakan Berhasil", msg)
        else:
            QMessageBox.critical(self, "Gagal Mencetak", msg)

    def _trigger_maintenance(self, action: str):
        """Executes maintenance action."""
        if action == "clean":
            reply = QMessageBox.question(
                self,
                "Konfirmasi Head Cleaning",
                "Jalankan Pembersihan Head (Head Cleaning) pada printer Epson L1110?\n\n"
                "Siklus mekanis ini membutuhkan waktu sekitar 75-80 detik dan menggunakan sedikit tinta "
                "untuk membilas dan melancarkan nozzle yang tersumbat.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            dialog = HeadCleaningDialog(self.maintenance_controller, self.usb_device, parent=self)
            dialog.request_nozzle_check.connect(lambda: self._trigger_maintenance("nozzle"))
            dialog.exec()
            return

        action_names = {
            "nozzle": "Cetak Pola Uji Nozzle",
            "eject": "Keluarkan Kertas",
        }
        act_name = action_names.get(action, action)

        reply = QMessageBox.question(
            self,
            "Konfirmasi Pemeliharaan",
            f"Jalankan {act_name} pada printer Epson L1110 sekarang?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_bar.showMessage(f"Menjalankan {act_name}...")
        self.active_maint_worker = MaintenanceWorker(
            action=action,
            controller=self.maintenance_controller,
            usb_device=self.usb_device,
        )
        self.active_maint_worker.finished.connect(self._on_maintenance_finished)
        self.active_maint_worker.start()

    def _on_maintenance_finished(self, success: bool, msg: str):
        self.status_bar.showMessage(msg)
        if success:
            QMessageBox.information(self, "Pemeliharaan Selesai", msg)
        else:
            QMessageBox.warning(self, "Pemeliharaan Gagal", msg)

    def closeEvent(self, event):
        """Disconnect USB gracefully when window closes."""
        if self.usb_device:
            try:
                self.usb_device.disconnect()
            except Exception:
                pass
        event.accept()
