"""
Interactive Document Preview Widget for Epson L1110 Control Center.
Displays high-fidelity rendered pages with pagination and zoom controls.
Pure functional layout adhering to workspace guidelines.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QGroupBox,
)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt
from typing import Optional
from PIL import Image

from ..core.rasterizer import DocumentRasterizer


def pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    """Convert PIL RGB Image to PyQt6 QPixmap."""
    rgb_img = pil_img.convert("RGB")
    data = rgb_img.tobytes("raw", "RGB")
    qimg = QImage(data, rgb_img.width, rgb_img.height, rgb_img.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


class PreviewWidget(QGroupBox):
    """Container for interactive document preview and pagination."""

    def __init__(self, parent=None):
        super().__init__("Pratinjau Dokumen Cetak", parent)

        self.current_file: Optional[str] = None
        self.rasterizer: Optional[DocumentRasterizer] = None
        self.current_page: int = 0
        self.total_pages: int = 0
        self.zoom_factor: float = 1.0
        self.base_pixmap: Optional[QPixmap] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(6)

        # Scrollable image canvas
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: #e6e6e6; border: 1px solid #cccccc;")

        self.lbl_canvas = QLabel("Pilih dokumen PDF atau gambar untuk melihat pratinjau")
        self.lbl_canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_canvas.setStyleSheet("color: #666666; font-size: 13px;")
        self.scroll_area.setWidget(self.lbl_canvas)
        layout.addWidget(self.scroll_area)

        # Navigation & Zoom Bar
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(6)

        self.btn_prev = QPushButton("◀ Sebelumnya")
        self.btn_prev.setEnabled(False)
        self.btn_prev.clicked.connect(self.prev_page)
        nav_layout.addWidget(self.btn_prev)

        self.lbl_page = QLabel("Halaman 0 / 0")
        self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.lbl_page)

        self.btn_next = QPushButton("Berikutnya ▶")
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(self.next_page)
        nav_layout.addWidget(self.btn_next)

        nav_layout.addStretch()

        self.btn_zoom_out = QPushButton("Zoom -")
        self.btn_zoom_out.setEnabled(False)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        nav_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_in = QPushButton("Zoom +")
        self.btn_zoom_in.setEnabled(False)
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        nav_layout.addWidget(self.btn_zoom_in)

        self.btn_fit = QPushButton("Pas Ukuran")
        self.btn_fit.setEnabled(False)
        self.btn_fit.clicked.connect(self.fit_to_window)
        nav_layout.addWidget(self.btn_fit)

        layout.addLayout(nav_layout)

    def load_document(self, file_path: str, rasterizer: DocumentRasterizer):
        """Loads and renders the first page of the document."""
        self.current_file = file_path
        self.rasterizer = rasterizer
        self.current_page = 0
        self.zoom_factor = 1.0

        try:
            self.total_pages = rasterizer.get_page_count(file_path)
            self._render_current_page()
            self.btn_zoom_in.setEnabled(True)
            self.btn_zoom_out.setEnabled(True)
            self.btn_fit.setEnabled(True)
        except Exception as e:
            self.lbl_canvas.setText(f"Gagal memuat pratinjau: {e}")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)

    def _render_current_page(self):
        """Renders page via rasterizer and displays in canvas."""
        if not self.current_file or not self.rasterizer:
            return

        # Render preview at moderate DPI for smooth UI performance
        pil_img = self.rasterizer.render_preview_pixmap(
            self.current_file, page_number=self.current_page, preview_dpi=120
        )
        self.base_pixmap = pil_to_qpixmap(pil_img)
        self._apply_zoom()

        self.lbl_page.setText(f"Halaman {self.current_page + 1} / {self.total_pages}")
        self.btn_prev.setEnabled(self.current_page > 0)
        self.btn_next.setEnabled(self.current_page < self.total_pages - 1)

    def _apply_zoom(self):
        """Scales base pixmap and updates canvas label."""
        if not self.base_pixmap:
            return
        target_w = int(self.base_pixmap.width() * self.zoom_factor)
        target_h = int(self.base_pixmap.height() * self.zoom_factor)
        scaled = self.base_pixmap.scaled(
            target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.lbl_canvas.setPixmap(scaled)

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render_current_page()

    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._render_current_page()

    def zoom_in(self):
        if self.zoom_factor < 2.5:
            self.zoom_factor += 0.2
            self._apply_zoom()

    def zoom_out(self):
        if self.zoom_factor > 0.4:
            self.zoom_factor -= 0.2
            self._apply_zoom()

    def fit_to_window(self):
        if not self.base_pixmap:
            return
        area_h = max(200, self.scroll_area.viewport().height() - 20)
        self.zoom_factor = area_h / self.base_pixmap.height()
        self._apply_zoom()
