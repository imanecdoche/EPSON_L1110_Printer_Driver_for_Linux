"""
Epson EcoTank 4-Color Ink Level Visualization Widget.
Displays real-time levels for Black (BK), Cyan (C), Magenta (M), and Yellow (Y).
Includes direct calibration dialog to sync with physical EcoTank liquid height.
Pure functional UI adhering to project rules (no arbitrary pills/badges).
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QGroupBox,
    QPushButton,
    QDialog,
    QSpinBox,
    QSlider,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal


class SingleTankWidget(QWidget):
    """Visual meter for a single ink tank with vertical progress and percentage."""

    def __init__(self, color_name: str, code: str, hex_color: str, parent=None):
        super().__init__(parent)
        self.code = code
        self.hex_color = hex_color

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Tank title
        self.lbl_title = QLabel(f"<b>{code}</b>")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_title)

        # Vertical progress bar for tank
        self.bar = QProgressBar()
        self.bar.setOrientation(Qt.Orientation.Vertical)
        self.bar.setRange(0, 100)
        self.bar.setValue(85)
        self.bar.setFixedWidth(32)
        self.bar.setMinimumHeight(120)
        self.bar.setTextVisible(False)

        # Styling
        border_color = "#333333" if hex_color == "#fff100" else "#555555"
        self.bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {border_color};
                background-color: #f0f0f0;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {hex_color};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self.bar, alignment=Qt.AlignmentFlag.AlignCenter)

        # Value label
        self.lbl_val = QLabel("85%")
        self.lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_val)

    def set_level(self, percentage: int):
        pct = max(0, min(100, int(round(percentage))))
        self.bar.setValue(pct)
        self.lbl_val.setText(f"{pct}%")


class InkCalibrationDialog(QDialog):
    """Dialog to manually align digital gauges with physical transparent ink tanks."""

    def __init__(self, bk: int, c: int, m: int, y: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kalibrasi Level Tinta — EcoTank L1110")
        self.setFixedSize(420, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        lbl_desc = QLabel(
            "<b>Sinkronkan Level Tinta dengan Kondisi Fisik:</b><br>"
            "Sesuaikan persentase berikut agar sama persis dengan ketinggian "
            "cairan tinta yang Anda lihat pada jendela tangki depan printer Epson L1110."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #333333; font-size: 12px;")
        layout.addWidget(lbl_desc)

        # Controls for each color
        self.spins = {}
        colors = [
            ("Black (BK)", "BK", bk),
            ("Cyan (C)", "C", c),
            ("Magenta (M)", "M", m),
            ("Yellow (Y)", "Y", y),
        ]

        for label_text, key, val in colors:
            row = QHBoxLayout()
            lbl = QLabel(f"<b>{label_text}:</b>")
            lbl.setFixedWidth(110)
            row.addWidget(lbl)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(val)
            row.addWidget(slider)

            spin = QSpinBox()
            spin.setRange(0, 100)
            spin.setValue(val)
            spin.setSuffix("%")
            spin.setFixedWidth(65)
            row.addWidget(spin)

            # Sync slider and spinbox
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)

            self.spins[key] = spin
            layout.addLayout(row)

        layout.addSpacing(6)

        # Quick action: All 100% (Refilled)
        self.btn_refill = QPushButton("Semua 100% (Baru Isi Ulang Botol)")
        self.btn_refill.clicked.connect(self._set_all_full)
        layout.addWidget(self.btn_refill)

        layout.addStretch()

        # Dialog buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        self.btn_cancel = QPushButton("Batal")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Simpan & Terapkan")
        self.btn_save.setStyleSheet("font-weight: bold; background-color: #1a73e8; color: white; padding: 6px;")
        self.btn_save.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_save)

        layout.addLayout(btn_box)

    def _set_all_full(self):
        for s in self.spins.values():
            s.setValue(100)

    def get_calibrated_levels(self):
        return (
            self.spins["BK"].value(),
            self.spins["C"].value(),
            self.spins["M"].value(),
            self.spins["Y"].value(),
        )


class InkLevelWidget(QGroupBox):
    """Container displaying all 4 EcoTank reservoirs and calibration controls."""

    levels_changed = pyqtSignal(int, int, int, int)

    def __init__(self, parent=None):
        super().__init__("Status Tangki Tinta (EcoTank)", parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 12, 8, 8)
        main_layout.setSpacing(6)

        # Tanks layout
        tanks_layout = QHBoxLayout()
        tanks_layout.setSpacing(8)

        # Black, Cyan, Magenta, Yellow
        self.tank_bk = SingleTankWidget("Black", "BK", "#1a1a1a")
        self.tank_c = SingleTankWidget("Cyan", "C", "#00a0e9")
        self.tank_m = SingleTankWidget("Magenta", "M", "#e4007f")
        self.tank_y = SingleTankWidget("Yellow", "Y", "#e5c000")

        tanks_layout.addWidget(self.tank_bk)
        tanks_layout.addWidget(self.tank_c)
        tanks_layout.addWidget(self.tank_m)
        tanks_layout.addWidget(self.tank_y)

        main_layout.addLayout(tanks_layout)

        # Calibration button
        self.btn_calibrate = QPushButton("Kalibrasi / Set Level Tinta...")
        self.btn_calibrate.setStyleSheet("font-size: 11px; padding: 3px;")
        self.btn_calibrate.clicked.connect(self._open_calibration)
        main_layout.addWidget(self.btn_calibrate)

    def update_levels(self, bk: int, c: int, m: int, y: int):
        """Update tank percentages."""
        self.tank_bk.set_level(bk)
        self.tank_c.set_level(c)
        self.tank_m.set_level(m)
        self.tank_y.set_level(y)

    def _open_calibration(self):
        dlg = InkCalibrationDialog(
            bk=self.tank_bk.bar.value(),
            c=self.tank_c.bar.value(),
            m=self.tank_m.bar.value(),
            y=self.tank_y.bar.value(),
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            bk, c, m, y = dlg.get_calibrated_levels()
            self.update_levels(bk, c, m, y)
            self.levels_changed.emit(bk, c, m, y)
