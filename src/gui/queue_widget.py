"""
Dedicated Print Queue Dialog for Epson L1110 Control Center.
Displays active, waiting, and completed print jobs in a separate, clean window.
Strictly adheres to workspace rules (no badges/tags/pills, native widgets only).
"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QAbstractItemView,
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt, pyqtSignal
from typing import List

from ..core.print_queue import PrintJob, JobStatus


class PrintQueueDialog(QDialog):
    """Separate dedicated window/dialog for Print Queue."""

    cancel_requested = pyqtSignal(str)   # emits job_id
    clear_requested = pyqtSignal()
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Antrean Cetak (Print Queue) — Epson EcoTank L1110")
        self.resize(720, 360)
        self.setMinimumSize(580, 260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 1. Jobs Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Nama Dokumen", "Total Cetak", "Waktu", "Status"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f7f9fa;
                border: 1px solid #d0d7de;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #f0f2f5;
                color: #24292f;
                font-weight: bold;
                padding: 6px 8px;
                border: 1px solid #d0d7de;
                font-size: 12px;
            }
        """)

        # Column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.table)

        # 2. Control Toolbar
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)

        self.lbl_summary = QLabel("Antrean: 0 tugas aktif")
        self.lbl_summary.setStyleSheet("color: #555555; font-size: 12px;")
        bottom_layout.addWidget(self.lbl_summary)

        bottom_layout.addStretch()

        self.btn_cancel = QPushButton("Batalkan Tugas")
        self.btn_cancel.setToolTip("Batalkan tugas cetak yang dipilih")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        bottom_layout.addWidget(self.btn_cancel)

        self.btn_clear = QPushButton("Bersihkan Selesai")
        self.btn_clear.setToolTip("Hapus riwayat tugas yang sudah selesai atau dibatalkan")
        self.btn_clear.clicked.connect(self.clear_requested.emit)
        bottom_layout.addWidget(self.btn_clear)

        self.btn_refresh = QPushButton("Segarkan")
        self.btn_refresh.setToolTip("Perbarui status antrean sistem")
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        bottom_layout.addWidget(self.btn_refresh)

        self.btn_close = QPushButton("Tutup")
        self.btn_close.clicked.connect(self.close)
        bottom_layout.addWidget(self.btn_close)

        layout.addLayout(bottom_layout)

        # Connect selection change
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

    def update_queue(self, jobs: List[PrintJob]):
        """Renders the current jobs list into the table."""
        selected_job_id = self.get_selected_job_id()

        self.table.setRowCount(len(jobs))
        active_count = 0

        for row, job in enumerate(jobs):
            # ID
            item_id = QTableWidgetItem(job.job_id)
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # File Name
            item_name = QTableWidgetItem(job.file_name)
            item_name.setToolTip(job.file_path or job.file_name)

            # Pages / Copies
            order_suffix = " (Rev)" if job.reverse_order else ""
            pages_desc = f"{job.total_printed_pages} hal ({job.copies}x){order_suffix}"
            item_pages = QTableWidgetItem(pages_desc)
            item_pages.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Time
            item_time = QTableWidgetItem(job.created_at)
            item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Status with pure text and subtle color coding
            if job.status == JobStatus.PRINTING:
                status_text = f"Mencetak ({job.progress}%)" if job.progress > 0 else "Sedang Mencetak"
                if job.status_detail:
                    status_text += f" — {job.status_detail}"
                item_status = QTableWidgetItem(status_text)
                item_status.setForeground(QColor("#1a5fb4"))
                font = item_status.font()
                font.setBold(True)
                item_status.setFont(font)
                active_count += 1
            elif job.status == JobStatus.RASTERIZING:
                status_text = f"Meraster ({job.progress}%)"
                item_status = QTableWidgetItem(status_text)
                item_status.setForeground(QColor("#0066cc"))
                active_count += 1
            elif job.status == JobStatus.QUEUED:
                item_status = QTableWidgetItem("Menunggu Antrean")
                item_status.setForeground(QColor("#a05a00"))
                active_count += 1
            elif job.status == JobStatus.COMPLETED:
                item_status = QTableWidgetItem("Selesai")
                item_status.setForeground(QColor("#2e7d32"))
            elif job.status == JobStatus.CANCELLED:
                item_status = QTableWidgetItem("Dibatalkan")
                item_status.setForeground(QColor("#777777"))
            else:
                item_status = QTableWidgetItem(f"Gagal: {job.status_detail or 'Error'}")
                item_status.setForeground(QColor("#c01c28"))

            self.table.setItem(row, 0, item_id)
            self.table.setItem(row, 1, item_name)
            self.table.setItem(row, 2, item_pages)
            self.table.setItem(row, 3, item_time)
            self.table.setItem(row, 4, item_status)

            # Restore selection
            if selected_job_id and job.job_id == selected_job_id:
                self.table.selectRow(row)

        self.lbl_summary.setText(f"Antrean: {active_count} tugas aktif / {len(jobs)} total")
        self._on_selection_changed()

    def get_selected_job_id(self) -> str:
        """Returns the job_id of the currently selected row, or empty string."""
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            item = self.table.item(row, 0)
            if item:
                return item.text()
        return ""

    def _on_selection_changed(self):
        """Enable cancel button only when a cancellable job is selected."""
        job_id = self.get_selected_job_id()
        if not job_id:
            self.btn_cancel.setEnabled(False)
            return

        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            status_item = self.table.item(selected_rows[0].row(), 4)
            if status_item:
                text = status_item.text().lower()
                cancellable = ("mencetak" in text or "meraster" in text or "menunggu" in text)
                self.btn_cancel.setEnabled(cancellable)
                return
        self.btn_cancel.setEnabled(False)

    def _on_cancel_clicked(self):
        job_id = self.get_selected_job_id()
        if job_id:
            self.cancel_requested.emit(job_id)


# Backward compatibility alias
PrintQueueWidget = PrintQueueDialog
