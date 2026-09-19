"""
Epson EcoTank 4-Color Ink Level Visualization Widget.
Displays real-time levels for Black (BK), Cyan (C), Magenta (M), and Yellow (Y).
Pure functional UI adhering to project anti-pattern rules (no arbitrary pills/badges).
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QGroupBox,
)
from PyQt6.QtCore import Qt


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
        self.bar.setValue(100)
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
        self.lbl_val = QLabel("100%")
        self.lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_val)

    def set_level(self, percentage: int):
        pct = max(0, min(100, percentage))
        self.bar.setValue(pct)
        self.lbl_val.setText(f"{pct}%")


class InkLevelWidget(QGroupBox):
    """Container displaying all 4 EcoTank reservoirs."""

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

        # Info note
        self.lbl_note = QLabel("Estimasi tangki kontinu Epson L1110")
        self.lbl_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_note.setStyleSheet("color: #666666; font-size: 11px;")
        main_layout.addWidget(self.lbl_note)

    def update_levels(self, bk: int, c: int, m: int, y: int):
        """Update tank percentages."""
        self.tank_bk.set_level(bk)
        self.tank_c.set_level(c)
        self.tank_m.set_level(m)
        self.tank_y.set_level(y)
