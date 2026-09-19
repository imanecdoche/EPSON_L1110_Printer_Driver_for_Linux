"""
Interactive Document Preview Widget for Epson L1110 Control Center.
Displays high-fidelity rendered pages with pagination, zoom controls,
interactive document drag-and-drop positioning, safe area margin guidelines,
and magnetic snap-to-grid alignment.
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
    QFrame,
)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QFont, QTransform
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal
from typing import Optional, List, Tuple
from PIL import Image

from ..core.rasterizer import DocumentRasterizer


def pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    """Convert PIL RGB Image to PyQt6 QPixmap."""
    rgb_img = pil_img.convert("RGB")
    data = rgb_img.tobytes("raw", "RGB")
    qimg = QImage(data, rgb_img.width, rgb_img.height, rgb_img.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


class InteractiveCanvas(QWidget):
    """
    Interactive Document & Paper Canvas with:
    - Physical paper rendering with drop-shadow
    - Interactive drag-and-drop document repositioning
    - Real-time Safe Area Guidelines for margins (with danger-red boundary detection)
    - Magnetic Snapping: Center axis (horizontal & vertical), Margin edges, and precision grid
    - Negative scale (mirroring) rendering
    """

    offset_changed = pyqtSignal(float, float)  # (x_mm, y_mm)
    offset_committed = pyqtSignal(float, float)  # (x_mm, y_mm)

    PREVIEW_DPI = 120

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

        self.has_document: bool = False
        self.raw_doc_pixmap: Optional[QPixmap] = None
        self.raw_size_mm: Tuple[float, float] = (210.0, 297.0)
        self.paper_size_mm: Tuple[float, float] = (215.0, 330.0)
        self.margins_mm: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self.scaling_mode: str = "fit"
        self.scale_factor: float = 1.0
        self.offset_mm: List[float] = [0.0, 0.0]
        self.zoom_factor: float = 1.0
        self.snap_to_grid: bool = True

        # Drag state
        self.is_dragging: bool = False
        self.drag_start_pos: QPoint = QPoint()
        self.drag_start_offset: List[float] = [0.0, 0.0]

        # Active snap indicator state
        self.snapped_center_x: bool = False
        self.snapped_center_y: bool = False

        # Geometry caches
        self._doc_rect: QRect = QRect()
        self._paper_rect: QRect = QRect()
        self._safe_rect: QRect = QRect()

    def update_document(
        self,
        doc_pixmap: QPixmap,
        raw_size_mm: Tuple[float, float],
        paper_size_mm: Tuple[float, float],
        margins_mm: Tuple[float, float, float, float],
        scaling_mode: str,
        scale_factor: float,
        offset_mm: List[float],
        zoom_factor: float,
    ):
        """Updates document data and triggers layout recomputation."""
        self.has_document = True
        self.raw_doc_pixmap = doc_pixmap
        self.raw_size_mm = raw_size_mm
        self.paper_size_mm = paper_size_mm
        self.margins_mm = margins_mm
        self.scaling_mode = scaling_mode
        self.scale_factor = scale_factor
        self.offset_mm = list(offset_mm)
        self.zoom_factor = zoom_factor

        self.updateGeometry()
        self.update()

    def set_zoom(self, zoom: float):
        """Updates zoom level and refreshes geometry."""
        self.zoom_factor = zoom
        self.updateGeometry()
        self.update()

    def set_snap_to_grid(self, enabled: bool):
        """Toggles magnetic snap-to-grid behavior."""
        self.snap_to_grid = enabled
        self.update()

    def set_offset(self, offset_x_mm: float, offset_y_mm: float):
        """Programmatically sets the position offset."""
        self.offset_mm = [offset_x_mm, offset_y_mm]
        self.update()

    def sizeHint(self) -> QSize:
        if not self.has_document:
            return QSize(450, 550)
        paper_w_px = int(round((self.paper_size_mm[0] / 25.4) * self.PREVIEW_DPI * self.zoom_factor))
        paper_h_px = int(round((self.paper_size_mm[1] / 25.4) * self.PREVIEW_DPI * self.zoom_factor))
        return QSize(paper_w_px + 60, paper_h_px + 60)

    def _compute_layout(self):
        """Calculates paper sheet, safe area margin rect, and document page rect."""
        if not self.has_document:
            return

        w_px = int(round((self.paper_size_mm[0] / 25.4) * self.PREVIEW_DPI * self.zoom_factor))
        h_px = int(round((self.paper_size_mm[1] / 25.4) * self.PREVIEW_DPI * self.zoom_factor))

        origin_x = max(20, (self.width() - w_px) // 2)
        origin_y = max(20, (self.height() - h_px) // 2)

        self._paper_rect = QRect(origin_x, origin_y, w_px, h_px)

        # Margins in pixels
        m_top_px = int(round((max(0.0, self.margins_mm[0]) / 25.4) * self.PREVIEW_DPI * self.zoom_factor))
        m_bot_px = int(round((max(0.0, self.margins_mm[1]) / 25.4) * self.PREVIEW_DPI * self.zoom_factor))
        m_left_px = int(round((max(0.0, self.margins_mm[2]) / 25.4) * self.PREVIEW_DPI * self.zoom_factor))
        m_right_px = int(round((max(0.0, self.margins_mm[3]) / 25.4) * self.PREVIEW_DPI * self.zoom_factor))

        printable_w = max(10, w_px - m_left_px - m_right_px)
        printable_h = max(10, h_px - m_top_px - m_bot_px)

        self._safe_rect = QRect(origin_x + m_left_px, origin_y + m_top_px, printable_w, printable_h)

        # Document dimensions
        raw_w_px = (self.raw_size_mm[0] / 25.4) * self.PREVIEW_DPI * self.zoom_factor
        raw_h_px = (self.raw_size_mm[1] / 25.4) * self.PREVIEW_DPI * self.zoom_factor

        if self.scaling_mode == "fit":
            ratio = raw_w_px / max(1.0, raw_h_px)
            p_ratio = printable_w / max(1.0, printable_h)
            if ratio > p_ratio:
                doc_w = printable_w
                doc_h = max(5, int(round(printable_w / ratio)))
            else:
                doc_h = printable_h
                doc_w = max(5, int(round(printable_h * ratio)))
        elif self.scaling_mode == "actual":
            doc_w = max(5, int(round(raw_w_px)))
            doc_h = max(5, int(round(raw_h_px)))
        elif self.scaling_mode == "custom":
            mult = abs(self.scale_factor) if abs(self.scale_factor) >= 0.05 else 0.2
            doc_w = max(5, int(round(raw_w_px * mult)))
            doc_h = max(5, int(round(raw_h_px * mult)))
        else:
            doc_w = printable_w
            doc_h = printable_h

        # User offset
        off_x_px = int(round((self.offset_mm[0] / 25.4) * self.PREVIEW_DPI * self.zoom_factor))
        off_y_px = int(round((self.offset_mm[1] / 25.4) * self.PREVIEW_DPI * self.zoom_factor))

        base_x = origin_x + m_left_px + (printable_w - doc_w) // 2
        base_y = origin_y + m_top_px + (printable_h - doc_h) // 2

        self._doc_rect = QRect(base_x + off_x_px, base_y + off_y_px, doc_w, doc_h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 1. Canvas neutral background
        painter.fillRect(self.rect(), QColor("#e6e6e6"))

        if not self.has_document:
            painter.setPen(QColor("#666666"))
            painter.setFont(QFont("Sans", 11))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Pilih dokumen PDF atau gambar untuk melihat pratinjau")
            return

        self._compute_layout()

        # 2. Paper drop shadow
        shadow_rect = self._paper_rect.adjusted(3, 3, 3, 3)
        painter.fillRect(shadow_rect, QColor(0, 0, 0, 25))

        # 3. Paper white sheet
        painter.fillRect(self._paper_rect, QColor(255, 255, 255))
        painter.setPen(QPen(QColor("#bbbbbb"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._paper_rect)

        # 4. Grid lines on paper (if snap to grid is active)
        if self.snap_to_grid and (self.is_dragging or self.zoom_factor >= 0.8):
            grid_step = int(round((10.0 / 25.4) * self.PREVIEW_DPI * self.zoom_factor))
            if grid_step >= 12:
                grid_pen = QPen(QColor("#f2f3f5"), 1, Qt.PenStyle.DotLine)
                painter.setPen(grid_pen)
                gx = self._paper_rect.left() + grid_step
                while gx < self._paper_rect.right():
                    painter.drawLine(gx, self._paper_rect.top(), gx, self._paper_rect.bottom())
                    gx += grid_step
                gy = self._paper_rect.top() + grid_step
                while gy < self._paper_rect.bottom():
                    painter.drawLine(self._paper_rect.left(), gy, self._paper_rect.right(), gy)
                    gy += grid_step

        # 5. Render Document Pixmap
        if self.raw_doc_pixmap and not self.raw_doc_pixmap.isNull():
            if self.scaling_mode == "custom" and self.scale_factor < 0:
                t = QTransform()
                t.scale(-1, 1)
                mirrored = self.raw_doc_pixmap.transformed(t)
                painter.drawPixmap(self._doc_rect, mirrored)
            else:
                painter.drawPixmap(self._doc_rect, self.raw_doc_pixmap)

        # 6. Safe Area Margin Guideline
        is_inside_safe = self._safe_rect.contains(self._doc_rect)
        if self.is_dragging:
            guideline_color = QColor("#0969da") if is_inside_safe else QColor("#cf222e")
            safe_pen = QPen(guideline_color, 1.5, Qt.PenStyle.DashLine)
            painter.setPen(safe_pen)
            painter.drawRect(self._safe_rect)

            painter.setFont(QFont("Sans", 8, QFont.Weight.Bold))
            painter.setPen(guideline_color)
            status_txt = "Safe Area Margin" if is_inside_safe else "! Melebihi Batas Margin !"
            painter.drawText(self._safe_rect.left() + 6, self._safe_rect.top() + 14, status_txt)
        else:
            # Subtle static margin border
            painter.setPen(QPen(QColor("#d0d7de"), 1, Qt.PenStyle.DotLine))
            painter.drawRect(self._safe_rect)

        # 7. Guidelines & Snapping Aids during Drag
        if self.is_dragging:
            # Document selection border
            border_color = QColor("#0969da") if is_inside_safe else QColor("#cf222e")
            painter.setPen(QPen(border_color, 1.5, Qt.PenStyle.SolidLine))
            painter.drawRect(self._doc_rect)

            center_pen = QPen(QColor("#1f883d"), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(center_pen)
            painter.setFont(QFont("Sans", 8))

            # Vertical center snap guide
            if self.snapped_center_x:
                cx = self._paper_rect.left() + self._paper_rect.width() // 2
                painter.drawLine(cx, self._paper_rect.top(), cx, self._paper_rect.bottom())
                painter.drawText(cx + 4, self._paper_rect.top() + 14, "Tengah X (Center)")

            # Horizontal center snap guide
            if self.snapped_center_y:
                cy = self._paper_rect.top() + self._paper_rect.height() // 2
                painter.drawLine(self._paper_rect.left(), cy, self._paper_rect.right(), cy)
                painter.drawText(self._paper_rect.left() + 6, cy - 4, "Tengah Y (Center)")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.has_document:
            if self._doc_rect.contains(event.pos()) or self._paper_rect.contains(event.pos()):
                self.is_dragging = True
                self.drag_start_pos = event.pos()
                self.drag_start_offset = list(self.offset_mm)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.update()

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            px_per_mm = (self.PREVIEW_DPI * self.zoom_factor) / 25.4
            dx_mm = (event.pos().x() - self.drag_start_pos.x()) / px_per_mm
            dy_mm = (event.pos().y() - self.drag_start_pos.y()) / px_per_mm

            new_x = self.drag_start_offset[0] + dx_mm
            new_y = self.drag_start_offset[1] + dy_mm

            self.snapped_center_x = False
            self.snapped_center_y = False

            if self.snap_to_grid:
                SNAP_THRESH = 3.0  # mm

                # Center snap
                if abs(new_x) < SNAP_THRESH:
                    new_x = 0.0
                    self.snapped_center_x = True

                if abs(new_y) < SNAP_THRESH:
                    new_y = 0.0
                    self.snapped_center_y = True

                # Margin edge snap
                spare_w_mm = ((self._safe_rect.width() - self._doc_rect.width()) / px_per_mm) / 2.0
                if not self.snapped_center_x:
                    if abs(new_x - (-spare_w_mm)) < SNAP_THRESH:
                        new_x = -spare_w_mm
                    elif abs(new_x - spare_w_mm) < SNAP_THRESH:
                        new_x = spare_w_mm
                    else:
                        new_x = round(new_x / 2.0) * 2.0  # 2mm grid step

                spare_h_mm = ((self._safe_rect.height() - self._doc_rect.height()) / px_per_mm) / 2.0
                if not self.snapped_center_y:
                    if abs(new_y - (-spare_h_mm)) < SNAP_THRESH:
                        new_y = -spare_h_mm
                    elif abs(new_y - spare_h_mm) < SNAP_THRESH:
                        new_y = spare_h_mm
                    else:
                        new_y = round(new_y / 2.0) * 2.0

            self.offset_mm = [new_x, new_y]
            self.update()
            self.offset_changed.emit(new_x, new_y)
        else:
            if self.has_document and self._doc_rect.contains(event.pos()):
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging:
            self.is_dragging = False
            self.snapped_center_x = False
            self.snapped_center_y = False
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._doc_rect.contains(event.pos()) else Qt.CursorShape.ArrowCursor)
            self.update()
            self.offset_committed.emit(self.offset_mm[0], self.offset_mm[1])


class PreviewWidget(QGroupBox):
    """Container for interactive document preview, pagination, scaling, and canvas dragging."""

    position_offset_changed = pyqtSignal(float, float)
    position_offset_committed = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__("Pratinjau Dokumen Cetak", parent)

        self.current_file: Optional[str] = None
        self.rasterizer: Optional[DocumentRasterizer] = None
        self.current_page: int = 0
        self.total_pages: int = 0
        self.page_indices: Optional[List[int]] = None
        self.zoom_factor: float = 1.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(6)

        # Scrollable interactive canvas
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: #e6e6e6; border: 1px solid #cccccc;")

        self.canvas = InteractiveCanvas(self)
        self.canvas.offset_changed.connect(self.position_offset_changed)
        self.canvas.offset_committed.connect(self.position_offset_committed)
        self.scroll_area.setWidget(self.canvas)
        layout.addWidget(self.scroll_area)

        # Navigation & Zoom Bar: [<] 1/100 [>] | [-] [+] [Fit] [1:1]
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(6)
        nav_layout.addStretch()

        self.btn_prev = QPushButton("<")
        self.btn_prev.setFixedWidth(36)
        self.btn_prev.setEnabled(False)
        self.btn_prev.setToolTip("Halaman Sebelumnya")
        self.btn_prev.clicked.connect(self.prev_page)
        nav_layout.addWidget(self.btn_prev)

        self.lbl_page = QLabel("0/0")
        self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_page.setMinimumWidth(50)
        nav_layout.addWidget(self.lbl_page)

        self.btn_next = QPushButton(">")
        self.btn_next.setFixedWidth(36)
        self.btn_next.setEnabled(False)
        self.btn_next.setToolTip("Halaman Berikutnya")
        self.btn_next.clicked.connect(self.next_page)
        nav_layout.addWidget(self.btn_next)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        nav_layout.addWidget(sep)

        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setFixedWidth(36)
        self.btn_zoom_out.setEnabled(False)
        self.btn_zoom_out.setToolTip("Perkecil (-)")
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        nav_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setFixedWidth(36)
        self.btn_zoom_in.setEnabled(False)
        self.btn_zoom_in.setToolTip("Perbesar (+)")
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        nav_layout.addWidget(self.btn_zoom_in)

        self.btn_fit = QPushButton("Fit")
        self.btn_fit.setFixedWidth(46)
        self.btn_fit.setEnabled(False)
        self.btn_fit.setToolTip("Pas Ukuran Jendela")
        self.btn_fit.clicked.connect(self.fit_to_window)
        nav_layout.addWidget(self.btn_fit)

        self.btn_1to1 = QPushButton("1:1")
        self.btn_1to1.setFixedWidth(46)
        self.btn_1to1.setEnabled(False)
        self.btn_1to1.setToolTip("Ukuran Asli 100%")
        self.btn_1to1.clicked.connect(self.actual_size)
        nav_layout.addWidget(self.btn_1to1)

        nav_layout.addStretch()

        layout.addLayout(nav_layout)

    def load_document(self, file_path: str, rasterizer: DocumentRasterizer, page_indices: Optional[List[int]] = None):
        """Loads and renders the document with optional page subset."""
        is_same_file = (self.current_file == file_path)
        self.current_file = file_path
        self.rasterizer = rasterizer
        if not is_same_file:
            self.current_page = 0
            self.zoom_factor = 1.0

        try:
            doc_pages = rasterizer.get_page_count(file_path)
            if page_indices is not None and len(page_indices) > 0:
                self.page_indices = page_indices
                self.total_pages = len(page_indices)
            else:
                self.page_indices = list(range(doc_pages))
                self.total_pages = doc_pages

            if self.current_page >= self.total_pages:
                self.current_page = max(0, self.total_pages - 1)

            self._render_current_page()
            self.btn_zoom_in.setEnabled(True)
            self.btn_zoom_out.setEnabled(True)
            self.btn_fit.setEnabled(True)
            self.btn_1to1.setEnabled(True)
        except Exception as e:
            self.lbl_page.setText("0/0")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.btn_zoom_in.setEnabled(False)
            self.btn_zoom_out.setEnabled(False)
            self.btn_fit.setEnabled(False)
            self.btn_1to1.setEnabled(False)

    def set_page_indices(self, page_indices: List[int]):
        """Updates active subset of pages without resetting entire document."""
        if not page_indices or not self.current_file:
            return
        self.page_indices = page_indices
        self.total_pages = len(page_indices)
        if self.current_page >= self.total_pages:
            self.current_page = max(0, self.total_pages - 1)
        self._render_current_page()

    def set_snap_to_grid(self, enabled: bool):
        """Toggles magnetic snapping on canvas."""
        self.canvas.set_snap_to_grid(enabled)

    def set_position_offset(self, offset_x: float, offset_y: float):
        """Sets position offset on canvas."""
        self.canvas.set_offset(offset_x, offset_y)

    def _render_current_page(self):
        """Extracts source page and physical dimensions, updating the interactive canvas."""
        if not self.current_file or not self.rasterizer:
            return

        actual_page = self.page_indices[self.current_page] if self.page_indices else self.current_page

        raw_pil = self.rasterizer.get_raw_page_image(self.current_file, page_number=actual_page, dpi=self.canvas.PREVIEW_DPI)
        raw_size_mm = self.rasterizer.get_document_page_size_mm(self.current_file, page_number=actual_page)
        pix = pil_to_qpixmap(raw_pil)

        self.canvas.update_document(
            doc_pixmap=pix,
            raw_size_mm=raw_size_mm,
            paper_size_mm=(self.rasterizer.paper.width_mm, self.rasterizer.paper.height_mm),
            margins_mm=self.rasterizer.margins_mm,
            scaling_mode=self.rasterizer.scaling_mode,
            scale_factor=self.rasterizer.scale_factor,
            offset_mm=list(self.rasterizer.position_offset_mm),
            zoom_factor=self.zoom_factor,
        )

        self.lbl_page.setText(f"{self.current_page + 1}/{self.total_pages}")
        self.btn_prev.setEnabled(self.current_page > 0)
        self.btn_next.setEnabled(self.current_page < self.total_pages - 1)

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
            self.canvas.set_zoom(self.zoom_factor)

    def zoom_out(self):
        if self.zoom_factor > 0.4:
            self.zoom_factor -= 0.2
            self.canvas.set_zoom(self.zoom_factor)

    def fit_to_window(self):
        if not self.rasterizer:
            return
        viewport_h = max(200, self.scroll_area.viewport().height() - 40)
        paper_h_base_px = (self.rasterizer.paper.height_mm / 25.4) * self.canvas.PREVIEW_DPI
        self.zoom_factor = max(0.2, min(2.5, viewport_h / paper_h_base_px))
        self.canvas.set_zoom(self.zoom_factor)

    def actual_size(self):
        """Reset zoom factor to 1.0 (100% original scale)."""
        self.zoom_factor = 1.0
        self.canvas.set_zoom(1.0)


