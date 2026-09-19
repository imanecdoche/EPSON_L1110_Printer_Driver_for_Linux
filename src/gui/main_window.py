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
    QDoubleSpinBox,
    QLineEdit,
    QCheckBox,
    QScrollArea,
    QFrame,
    QFileDialog,
    QMessageBox,
    QProgressBar,
    QStatusBar,
)
from PyQt6.QtCore import Qt, QTimer
from typing import Optional, List

from ..core.escpr_protocol import (
    PAPER_SIZES,
    Resolution,
    MediaType,
    ColorMode,
    PaperSize,
)
from ..core.rasterizer import DocumentRasterizer, parse_page_selection
from ..core.maintenance import MaintenanceController
from ..core.usb_device import EpsonUSBDevice
from ..core.ink_tracker import InkTracker
from ..core.print_queue import PrintQueueManager, JobStatus, PrintJob
from .ink_widget import InkLevelWidget
from .preview_widget import PreviewWidget
from .queue_widget import PrintQueueDialog
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
        self.ink_tracker = InkTracker()
        self.queue_manager = PrintQueueManager()
        self.usb_device: Optional[EpsonUSBDevice] = None
        self.current_file_path: Optional[str] = None
        self.imported_doc_pages: int = 0
        self.doc_offset_mm: Tuple[float, float] = (0.0, 0.0)
        self.active_print_worker: Optional[PrintJobWorker] = None
        self.active_maint_worker: Optional[MaintenanceWorker] = None

        # Print Queue Dialog (separate window)
        self.queue_dialog = PrintQueueDialog(self)
        self.queue_dialog.cancel_requested.connect(self._on_cancel_job_requested)
        self.queue_dialog.clear_requested.connect(self._on_clear_queue_requested)
        self.queue_dialog.refresh_requested.connect(self._sync_queue_status)

        self._init_usb_connection()
        self._setup_ui()

        # Background timer for CUPS queue synchronization
        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self._sync_queue_status)
        self.queue_timer.start(3000)

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
        panel_left.setFixedWidth(310)
        panel_outer = QVBoxLayout(panel_left)
        panel_outer.setContentsMargins(2, 6, 2, 4)

        scroll_left = QScrollArea()
        scroll_left.setWidgetResizable(True)
        scroll_left.setFrameShape(QFrame.Shape.NoFrame)
        scroll_left.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(6, 4, 6, 6)
        left_layout.setSpacing(8)

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

        left_layout.addSpacing(4)

        # Paper Size Selection (Default: F4 / Folio)
        lbl_paper = QLabel("<b>Ukuran Kertas:</b>")
        left_layout.addWidget(lbl_paper)
        self.combo_paper = QComboBox()
        for key, psize in PAPER_SIZES.items():
            self.combo_paper.addItem(psize.name, userData=key)
        self.combo_paper.setCurrentIndex(0)  # F4 default
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
        self.spin_copies.valueChanged.connect(self._update_total_print_pages_label)
        left_layout.addWidget(self.spin_copies)

        # Print Order (Normal vs Reverse)
        lbl_order = QLabel("<b>Urutan Cetak (Print Order):</b>")
        left_layout.addWidget(lbl_order)
        self.combo_order = QComboBox()
        self.combo_order.addItem("Normal (Depan ke Belakang: 1 → Akhir)", userData=False)
        self.combo_order.addItem("Reverse (Belakang ke Depan: Akhir → 1)", userData=True)
        left_layout.addWidget(self.combo_order)

        # Page Selection Mode (All, Odd, Even, Custom Range)
        lbl_pages = QLabel("<b>Pilihan Halaman (Page Range):</b>")
        left_layout.addWidget(lbl_pages)
        self.combo_page_range = QComboBox()
        self.combo_page_range.addItem("Semua Halaman (All Pages)", userData="all")
        self.combo_page_range.addItem("Halaman Ganjil Saja (1, 3, 5...)", userData="odd")
        self.combo_page_range.addItem("Halaman Genap Saja (2, 4, 6...)", userData="even")
        self.combo_page_range.addItem("Kustom / Tertentu (contoh: 1-3, 5, 8)", userData="custom")
        self.combo_page_range.currentIndexChanged.connect(self._on_page_selection_changed)
        left_layout.addWidget(self.combo_page_range)

        self.edit_custom_pages = QLineEdit()
        self.edit_custom_pages.setPlaceholderText("Contoh: 1-3, 5, 8 atau 3,6,8")
        self.edit_custom_pages.setEnabled(False)
        self.edit_custom_pages.textChanged.connect(self._on_page_selection_changed)
        left_layout.addWidget(self.edit_custom_pages)

        # Custom Margins (Top, Bottom, Left, Right in mm)
        lbl_margin_title = QLabel("<b>Margin Kustom (mm):</b>")
        left_layout.addWidget(lbl_margin_title)

        margin_grid = QGridLayout()
        margin_grid.setSpacing(4)

        margin_grid.addWidget(QLabel("Atas:"), 0, 0)
        self.spin_margin_top = QDoubleSpinBox()
        self.spin_margin_top.setRange(0.0, 100.0)
        self.spin_margin_top.setSingleStep(1.0)
        self.spin_margin_top.setValue(0.0)
        self.spin_margin_top.setDecimals(1)
        self.spin_margin_top.setSuffix(" mm")
        self.spin_margin_top.valueChanged.connect(self._on_settings_changed)
        margin_grid.addWidget(self.spin_margin_top, 0, 1)

        margin_grid.addWidget(QLabel("Bawah:"), 0, 2)
        self.spin_margin_bottom = QDoubleSpinBox()
        self.spin_margin_bottom.setRange(0.0, 100.0)
        self.spin_margin_bottom.setSingleStep(1.0)
        self.spin_margin_bottom.setValue(0.0)
        self.spin_margin_bottom.setDecimals(1)
        self.spin_margin_bottom.setSuffix(" mm")
        self.spin_margin_bottom.valueChanged.connect(self._on_settings_changed)
        margin_grid.addWidget(self.spin_margin_bottom, 0, 3)

        margin_grid.addWidget(QLabel("Kiri:"), 1, 0)
        self.spin_margin_left = QDoubleSpinBox()
        self.spin_margin_left.setRange(0.0, 100.0)
        self.spin_margin_left.setSingleStep(1.0)
        self.spin_margin_left.setValue(0.0)
        self.spin_margin_left.setDecimals(1)
        self.spin_margin_left.setSuffix(" mm")
        self.spin_margin_left.valueChanged.connect(self._on_settings_changed)
        margin_grid.addWidget(self.spin_margin_left, 1, 1)

        margin_grid.addWidget(QLabel("Kanan:"), 1, 2)
        self.spin_margin_right = QDoubleSpinBox()
        self.spin_margin_right.setRange(0.0, 100.0)
        self.spin_margin_right.setSingleStep(1.0)
        self.spin_margin_right.setValue(0.0)
        self.spin_margin_right.setDecimals(1)
        self.spin_margin_right.setSuffix(" mm")
        self.spin_margin_right.valueChanged.connect(self._on_settings_changed)
        margin_grid.addWidget(self.spin_margin_right, 1, 3)

        left_layout.addLayout(margin_grid)

        left_layout.addSpacing(4)

        # Document Scaling Mode (Fit to Page, Actual Size, Custom)
        lbl_scaling = QLabel("<b>Penskalaan (Scaling):</b>")
        left_layout.addWidget(lbl_scaling)
        self.combo_scaling = QComboBox()
        self.combo_scaling.addItem("Pas ke Kertas (Fit to Page)", userData="fit")
        self.combo_scaling.addItem("Ukuran Asli (Actual Size 1:1)", userData="actual")
        self.combo_scaling.addItem("Kustom (Custom Scale)", userData="custom")
        self.combo_scaling.currentIndexChanged.connect(self._on_scaling_changed)
        left_layout.addWidget(self.combo_scaling)

        # Custom scale factor (step 0.2x, supports negative / minus)
        scale_box = QHBoxLayout()
        scale_box.setSpacing(6)
        scale_box.addWidget(QLabel("Faktor Skala:"))
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(-5.0, 5.0)
        self.spin_scale.setSingleStep(0.2)
        self.spin_scale.setValue(1.0)
        self.spin_scale.setDecimals(1)
        self.spin_scale.setSuffix("x")
        self.spin_scale.setEnabled(False)
        self.spin_scale.valueChanged.connect(self._on_settings_changed)
        scale_box.addWidget(self.spin_scale)
        left_layout.addLayout(scale_box)

        # Snap to Grid & Safe Area Guidelines
        self.chk_snap = QCheckBox("Snap to Grid & Safe Area")
        self.chk_snap.setChecked(True)
        self.chk_snap.toggled.connect(self._on_snap_toggled)
        left_layout.addWidget(self.chk_snap)

        # Interactive Drag Position display & Reset button
        pos_box = QHBoxLayout()
        pos_box.setSpacing(6)
        self.lbl_doc_position = QLabel("Posisi: X: 0.0, Y: 0.0 mm")
        self.lbl_doc_position.setStyleSheet("color: #444444; font-size: 11px;")
        pos_box.addWidget(self.lbl_doc_position, stretch=1)
        self.btn_reset_pos = QPushButton("Pusatkan")
        self.btn_reset_pos.setToolTip("Kembalikan posisi dokumen ke tengah area cetak")
        self.btn_reset_pos.clicked.connect(self._reset_doc_position)
        pos_box.addWidget(self.btn_reset_pos)
        left_layout.addLayout(pos_box)

        left_layout.addSpacing(6)

        # Informative Total Pages to Print Box (Physical pages = doc pages * copies)
        self.lbl_total_print_pages = QLabel("Total halaman dicetak: <b>0 lembar</b>")
        self.lbl_total_print_pages.setStyleSheet("""
            QLabel {
                background-color: #f7f9fa;
                border: 1px solid #d0d7de;
                border-radius: 4px;
                padding: 8px 10px;
                font-size: 12px;
                color: #24292f;
            }
        """)
        self.lbl_total_print_pages.setWordWrap(True)
        left_layout.addWidget(self.lbl_total_print_pages)

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

        scroll_left.setWidget(left_widget)
        panel_outer.addWidget(scroll_left)

        main_layout.addWidget(panel_left)

        # -------------------------------------------------------------
        # 2. CENTER PANEL: Document Preview Canvas
        # -------------------------------------------------------------
        self.preview_widget = PreviewWidget()
        self.preview_widget.position_offset_changed.connect(self._on_canvas_position_changed)
        self.preview_widget.position_offset_committed.connect(self._on_canvas_position_committed)
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

        conn_text = "Jalur: Driver CUPS Epson (Siap)"
        self.lbl_conn_status = QLabel(conn_text)
        self.lbl_conn_status.setStyleSheet("color: #2e7d32; font-size: 12px;")
        status_box.addWidget(self.lbl_conn_status)

        self.btn_open_queue = QPushButton("Lihat Antrean Cetak...")
        self.btn_open_queue.setToolTip("Buka jendela antrean cetak (Print Queue)")
        self.btn_open_queue.clicked.connect(self._open_print_queue_dialog)
        status_box.addWidget(self.btn_open_queue)

        right_layout.addWidget(grp_status)

        # Ink Widget
        self.ink_widget = InkLevelWidget()
        init_levels = self.ink_tracker.get_levels()
        self.ink_widget.update_levels(
            init_levels["BK"], init_levels["C"], init_levels["M"], init_levels["Y"]
        )
        self.ink_widget.levels_changed.connect(self._on_ink_calibrated)
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

        self.btn_status_queue = QPushButton("Antrean: 0")
        self.btn_status_queue.setToolTip("Buka jendela antrean cetak")
        self.btn_status_queue.setStyleSheet("""
            QPushButton {
                background-color: #f0f2f5;
                border: 1px solid #d0d7de;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
                color: #24292f;
            }
            QPushButton:hover {
                background-color: #e1e4e8;
            }
        """)
        self.btn_status_queue.clicked.connect(self._open_print_queue_dialog)
        self.status_bar.addPermanentWidget(self.btn_status_queue)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

        self.status_bar.showMessage("Siap — Sistem siap menerima instruksi cetak.")

    def _get_current_rasterizer(self) -> DocumentRasterizer:
        """Constructs DocumentRasterizer according to selected UI options, scaling, and custom margins."""
        paper_key = self.combo_paper.currentData()
        paper = PAPER_SIZES.get(paper_key, PAPER_SIZES["F4"])
        dpi = self.combo_dpi.currentData()
        media = self.combo_media.currentData()
        color = self.combo_color.currentData()

        top = self.spin_margin_top.value() if hasattr(self, "spin_margin_top") else 0.0
        bottom = self.spin_margin_bottom.value() if hasattr(self, "spin_margin_bottom") else 0.0
        left = self.spin_margin_left.value() if hasattr(self, "spin_margin_left") else 0.0
        right = self.spin_margin_right.value() if hasattr(self, "spin_margin_right") else 0.0
        margins_mm = (top, bottom, left, right)

        scaling_mode = self.combo_scaling.currentData() if hasattr(self, "combo_scaling") else "fit"
        scale_factor = self.spin_scale.value() if hasattr(self, "spin_scale") else 1.0
        pos_offset = getattr(self, "doc_offset_mm", (0.0, 0.0))

        return DocumentRasterizer(
            paper=paper,
            resolution=dpi,
            media=media,
            color_mode=color,
            margins_mm=margins_mm,
            scaling_mode=scaling_mode,
            scale_factor=scale_factor,
            position_offset_mm=pos_offset,
        )

    def _get_selected_pages(self) -> List[int]:
        """Returns 0-indexed list of selected page indices according to range/filtering options."""
        if not self.current_file_path or self.imported_doc_pages <= 0:
            return []
        mode = self.combo_page_range.currentData()
        custom_str = self.edit_custom_pages.text().strip()
        return parse_page_selection(mode, custom_str, self.imported_doc_pages)

    def _on_page_selection_changed(self):
        """Triggered when page range mode or custom input changes."""
        mode = self.combo_page_range.currentData()
        is_custom = (mode == "custom")
        self.edit_custom_pages.setEnabled(is_custom)

        self._update_total_print_pages_label()
        if self.current_file_path:
            pages = self._get_selected_pages()
            self.preview_widget.set_page_indices(pages)

    def _on_scaling_changed(self):
        """Triggered when scaling mode changes."""
        mode = self.combo_scaling.currentData()
        self.spin_scale.setEnabled(mode == "custom")
        self._on_settings_changed()

    def _on_snap_toggled(self, checked: bool):
        """Toggles magnetic snap-to-grid on preview canvas."""
        self.preview_widget.set_snap_to_grid(checked)

    def _on_canvas_position_changed(self, x_mm: float, y_mm: float):
        """Triggered while dragging document in canvas."""
        self.doc_offset_mm = (x_mm, y_mm)
        sign_x = "+" if x_mm >= 0 else ""
        sign_y = "+" if y_mm >= 0 else ""
        self.lbl_doc_position.setText(f"Posisi: X: {sign_x}{x_mm:.1f}, Y: {sign_y}{y_mm:.1f} mm")

    def _on_canvas_position_committed(self, x_mm: float, y_mm: float):
        """Triggered when mouse drag is released on canvas."""
        self._on_canvas_position_changed(x_mm, y_mm)
        if self.current_file_path:
            self.preview_widget.rasterizer = self._get_current_rasterizer()

    def _reset_doc_position(self):
        """Resets document position offset to center (0.0, 0.0 mm)."""
        self.doc_offset_mm = (0.0, 0.0)
        self.lbl_doc_position.setText("Posisi: X: 0.0, Y: 0.0 mm")
        self.preview_widget.set_position_offset(0.0, 0.0)
        if self.current_file_path:
            self._update_preview()

    def load_file(self, path: str):
        """Loads a document file into the preview and print system."""
        if not path or not os.path.exists(path):
            return
        self.current_file_path = os.path.abspath(path)
        self.lbl_selected_file.setText(os.path.basename(path))
        self.doc_offset_mm = (0.0, 0.0)
        self.lbl_doc_position.setText("Posisi: X: 0.0, Y: 0.0 mm")
        self.preview_widget.set_position_offset(0.0, 0.0)
        rasterizer = self._get_current_rasterizer()
        try:
            self.imported_doc_pages = rasterizer.get_page_count(self.current_file_path)
        except Exception:
            self.imported_doc_pages = 1
        self._update_total_print_pages_label()
        self._update_preview()

    def _select_file(self):
        """Open file dialog for PDF and image documents."""
        file_filter = "Dokumen Cetak (*.pdf *.png *.jpg *.jpeg *.bmp *.tiff);;Berkas PDF (*.pdf);;Gambar (*.png *.jpg *.jpeg)"
        path, _ = QFileDialog.getOpenFileName(self, "Pilih Berkas Dokumen", "", file_filter)
        if path:
            self.load_file(path)

    def _update_total_print_pages_label(self):
        """Calculates and displays total physical pages to be printed (selected pages * copies)."""
        copies = self.spin_copies.value()
        if self.current_file_path and self.imported_doc_pages > 0:
            selected_pages = self._get_selected_pages()
            n_selected = len(selected_pages)
            total_print_pages = n_selected * copies

            if copies > 1:
                detail_text = f"({copies} salinan × {n_selected} halaman terpilih)"
            else:
                detail_text = f"(1 salinan × {n_selected} halaman terpilih)"

            if n_selected != self.imported_doc_pages:
                detail_text += f" <span style='color: #777;'>[dari total {self.imported_doc_pages} hal. dokumen]</span>"

            self.lbl_total_print_pages.setText(
                f"Total halaman dicetak: <b>{total_print_pages} lembar</b><br>"
                f"<span style='color: #555555; font-size: 11px;'>{detail_text}</span>"
            )
            self.btn_print.setEnabled(n_selected > 0)
        else:
            self.lbl_total_print_pages.setText("Total halaman dicetak: <b>0 lembar</b>")
            self.btn_print.setEnabled(False)

    def _on_settings_changed(self):
        """Triggered when paper, resolution, margins, or scaling change."""
        if self.current_file_path:
            self._update_preview()

    def _update_preview(self):
        """Re-renders the document preview canvas."""
        if not self.current_file_path:
            return
        rasterizer = self._get_current_rasterizer()
        selected_pages = self._get_selected_pages()
        self.preview_widget.load_document(self.current_file_path, rasterizer, page_indices=selected_pages)

    def _update_queue_ui(self):
        """Updates the separate PrintQueueDialog and the status bar indicator."""
        self.queue_dialog.update_queue(self.queue_manager.jobs)
        active_jobs = [
            j for j in self.queue_manager.jobs
            if j.status in (JobStatus.QUEUED, JobStatus.RASTERIZING, JobStatus.PRINTING)
        ]
        self.btn_status_queue.setText(f"Antrean: {len(active_jobs)}")

    def _open_print_queue_dialog(self):
        """Opens the separate Print Queue dialog window."""
        self._update_queue_ui()
        self.queue_dialog.show()
        self.queue_dialog.raise_()
        self.queue_dialog.activateWindow()

    def _start_print_job(self):
        """Enqueues document print job and triggers processing."""
        if not self.current_file_path:
            return

        rasterizer = self._get_current_rasterizer()
        copies = self.spin_copies.value()
        reverse_order = bool(self.combo_order.currentData())
        selected_pages = self._get_selected_pages()
        if not selected_pages:
            QMessageBox.warning(self, "Peringatan", "Tidak ada halaman yang dipilih untuk dicetak.")
            return

        total_pages = len(selected_pages)

        # Enqueue job
        job = self.queue_manager.add_job(
            file_path=self.current_file_path,
            rasterizer=rasterizer,
            copies=copies,
            total_pages=total_pages,
            reverse_order=reverse_order,
            pages=selected_pages,
        )

        self._update_queue_ui()
        self.status_bar.showMessage(f"Tugas cetak {job.job_id} ({job.file_name}) ditambahkan ke antrean.")

        # Process next in queue
        self._process_next_job()

    def _process_next_job(self):
        """Executes the next waiting job in the queue if worker is idle."""
        if self.active_print_worker and self.active_print_worker.isRunning():
            return  # Printer is busy with active job

        job = self.queue_manager.get_next_queued_job()
        if not job:
            return

        job.status = JobStatus.RASTERIZING
        job.progress = 5
        self._update_queue_ui()

        self.progress_bar.setValue(5)
        self.progress_bar.setVisible(True)

        self.active_print_worker = PrintJobWorker(
            file_path=job.file_path,
            rasterizer=job.rasterizer,
            copies=job.copies,
            reverse_order=job.reverse_order,
            usb_device=self.usb_device,
            job_id=job.job_id,
            pages=job.pages,
        )
        self.active_print_worker.progress_updated.connect(self._on_print_progress)
        self.active_print_worker.job_finished.connect(self._on_print_finished)
        self.active_print_worker.start()

    def _on_ink_calibrated(self, bk: int, c: int, m: int, y: int):
        """Save manual calibration to persistent tracker."""
        self.ink_tracker.set_levels(bk, c, m, y)
        self.status_bar.showMessage(f"Level tangki tinta dikalibrasi: BK {bk}%, C {c}%, M {m}%, Y {y}%")

    def _on_print_progress(self, job_id: str, percent: int, msg: str):
        self.progress_bar.setValue(percent)
        self.status_bar.showMessage(f"[{job_id}] {msg}")

        for j in self.queue_manager.jobs:
            if j.job_id == job_id:
                j.progress = percent
                if percent >= 70:
                    j.status = JobStatus.PRINTING
                else:
                    j.status = JobStatus.RASTERIZING
                j.status_detail = msg
                break
        self._update_queue_ui()

    def _on_print_finished(self, job_id: str, success: bool, msg: str):
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"[{job_id}] {msg}")

        finished_job = None
        for j in self.queue_manager.jobs:
            if j.job_id == job_id:
                finished_job = j
                j.progress = 100 if success else j.progress
                j.status = JobStatus.COMPLETED if success else JobStatus.FAILED
                j.status_detail = msg
                break

        self._update_queue_ui()

        if success and finished_job:
            # Deduct ink dynamically based on printed page volume
            color_mode = self.combo_color.currentData()
            res = self.combo_dpi.currentData()
            self.ink_tracker.consume_print_job(
                finished_job.total_printed_pages,
                color_mode=color_mode,
                resolution=res,
            )
            new_levels = self.ink_tracker.get_levels()
            self.ink_widget.update_levels(
                new_levels["BK"], new_levels["C"], new_levels["M"], new_levels["Y"]
            )

        # Automatically pick up next waiting job in queue!
        self._process_next_job()

    def _on_cancel_job_requested(self, job_id: str):
        """Cancels specified print job (whether running or waiting in queue)."""
        if self.active_print_worker and self.active_print_worker.isRunning():
            if getattr(self.active_print_worker, "job_id", None) == job_id:
                self.active_print_worker.cancel()
                self.status_bar.showMessage(f"Membatalkan tugas aktif {job_id}...")

        cancelled_job = self.queue_manager.cancel_job(job_id)
        self._update_queue_ui()
        if cancelled_job:
            self.status_bar.showMessage(f"Tugas cetak {job_id} ({cancelled_job.file_name}) dibatalkan.")

    def _on_clear_queue_requested(self):
        """Cleans up completed, cancelled, and failed jobs from queue view."""
        self.queue_manager.clear_finished()
        self._update_queue_ui()
        self.status_bar.showMessage("Riwayat tugas selesai/dibatalkan telah dibersihkan.")

    def _sync_queue_status(self):
        """Periodically polls CUPS spooler to sync external jobs."""
        self.queue_manager.sync_cups_jobs()
        self._update_queue_ui()

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

            # Head cleaning consumes a small fraction of ink for flushing
            self.ink_tracker.consume_head_cleaning()
            new_levels = self.ink_tracker.get_levels()
            self.ink_widget.update_levels(
                new_levels["BK"], new_levels["C"], new_levels["M"], new_levels["Y"]
            )
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
