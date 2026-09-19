#!/usr/bin/env python3
"""
Epson EcoTank L1110 Driver & GUI Control Center.
Application Entry Point.
"""

import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from src.gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Epson L1110 Control Center")
    app.setOrganizationName("EpsonLinuxDriver")

    # Set clean native typography
    font = QFont()
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        window.load_file(sys.argv[1])
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
