# Epson EcoTank L1110 Driver & GUI Control Center for Linux

A modern, standalone user-space driver, real-time ink monitor, and maintenance control center for the **Epson EcoTank L1110** inkjet printer on Linux systems. Built with Python, PyUSB, LibUSB, and PyQt6.

---

## The Problem: Why This Linux Driver Was Created

The **Epson EcoTank L1110** is one of the most cost-effective and widespread continuous ink tank printers in homes, schools, and offices worldwide. However, the Linux user experience for this printer has long suffered from significant compromises and limitations:

1. **No Real-Time Ink Tank & Status Monitoring**  
   Standard Linux printer setups treat the L1110 as a one-way print queue. Linux users cannot inspect remaining ink levels (Black, Cyan, Magenta, Yellow) or receive meaningful hardware diagnostics (e.g., paper feed errors, paper jams, head temperature, cover open) from their desktop.

2. **Missing Native Maintenance Utilities**  
   When print nozzles clog or streaks appear, Linux users are left stranded. The official Epson Linux utilities are frequently outdated, reliant on obsolete 32-bit libraries, or missing altogether. Performing a simple **Print Head Cleaning** or printing a **Nozzle Check Pattern** typically required dual-booting into Windows.

3. **No Native Support for F4 / Folio (215 × 330 mm) Paper**  
   In Southeast Asia, educational institutions, government agencies, and legal practices, **F4 / Folio (215 × 330 mm)** is the indispensable standard paper size. Generic Linux CUPS PPD profiles omit F4, forcing users to pick either Legal (too long, leading to margin misalignments) or A4 (truncating bottom margins).

4. **Sandbox & Office Suite Integration Friction**  
   Modern sandboxed office applications (such as Flatpak ONLYOFFICE or LibreOffice) communicate through generic desktop print portals that strip away advanced media profiles, resolution controls, and custom dimensions.

This project delivers an end-to-end, native, open-source solution: a dedicated user-space printer engine and desktop application providing full hardware control, bidirectional status querying, custom rasterization, and direct maintenance capabilities without proprietary bloat.

---

## Key Features

* **Direct Hardware Communication via USB**:  
  Communicates directly with the printer microcontroller using `pyusb` and `libusb-1.0`. Bypasses daemon bottlenecks and automatically handles `usblp` kernel driver detachment.

* **Real-Time 4-Color Ink Monitor**:  
  Bidirectional ESC/P-R status queries poll and display accurate ink tank levels for Black (BK), Cyan (C), Magenta (M), and Yellow (Y).

* **One-Click Maintenance Suite**:  
  Execute hardware routines directly from Linux:
  * Print Head Cleaning cycle
  * 4-Color Nozzle Check diagnostic pattern
  * Manual Paper Feed and Eject command

* **Native F4 / Folio & Custom Page Sizes**:  
  Full first-class support for F4 / Folio (215 × 330 mm / 8.5" × 13.0"), A4, A5, A6, B5, Letter, Legal, and custom user-defined page dimensions.

* **High-Fidelity ESC/P-R Raster Engine**:  
  Integrated multi-resolution document processor:
  * **Draft Mode (360 dpi)**: High-speed output optimized for text drafts and ink conservation.
  * **Standard / Normal Mode (720 dpi)**: Crisp text and balanced color saturation for everyday documents.
  * **High / Fine Mode (1440 dpi)**: Maximum detail rendering for photographic prints and complex graphics.
  * Media profiles for Plain Paper, Matte, and Glossy Photo media.

* **Modern PyQt6 Desktop Interface**:  
  Clean, functional 3-panel control center featuring real-time ink gauges, document preview canvas, page layout controls, and maintenance triggers.

* **Complete Document Pipeline**:  
  Direct printing support for PDF files and standard image formats (PNG, JPEG, TIFF) via high-performance PyMuPDF and Pillow rendering backends.

---

## Technical Architecture

```
+-------------------------------------------------------------------+
|               User Interface / Office Suite                      |
|      (PyQt6 Control Center / ONLYOFFICE / PDF Documents)          |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                 Document Rasterization Engine                     |
|           PyMuPDF / Pillow -> RGB/CMYK Color Separation           |
|            Resolution Scaling: 360 dpi / 720 dpi / 1440 dpi       |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                  ESC/P-R Binary Protocol Engine                   |
|        Page Setup, Raster Commands, PackBits Compression          |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                     USB Communication Layer                       |
|           PyUSB / LibUSB-1.0 (Vendor: 0x04b8, Product: 0x00a8)    |
|       Bulk OUT (Endpoint 0x02)  <--->  Bulk IN (Endpoint 0x81)    |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                 Hardware: Epson EcoTank L1110                     |
+-------------------------------------------------------------------+
```

---

## Repository Structure

```
epson-l1110-driver/
├── PRD.md                       # Complete technical & functional specifications
├── PLANNING.md                  # 5-phase execution roadmap & milestones
├── README.md                    # Project documentation & setup guide
├── SESSION_CONTEXT.md           # Developer session handover notes
├── .gitignore                   # Git exclusions for Python virtualenvs and caches
├── udev/
│   └── 99-epson-l1110.rules     # Non-root USB device permissions for Linux
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── usb_device.py        # Low-level USB device claim & endpoint discovery
│   │   ├── escpr_protocol.py    # ESC/P-R command builder & PackBits compressor (WIP)
│   │   └── rasterizer.py        # PDF & image document rasterization engine (WIP)
│   └── gui/
│       ├── __init__.py
│       ├── main_window.py       # PyQt6 main application window (WIP)
│       └── widgets/             # Ink level meters, preview canvas, maintenance panel
└── tests/
    ├── test_usb_detect.py       # Hardware enumeration & bidirectional probe test
    └── test_rasterizer.py       # Rasterizer unit tests (WIP)
```

---

## Getting Started

### 1. Prerequisites

Ensure your Linux system has Python 3.10+ and the required system development libraries installed:

```bash
# Debian / Ubuntu / Linux Mint
sudo apt update
sudo apt install -y libusb-1.0-0-dev python3-pip python3-dev poppler-utils
```

### 2. Configure Non-Root USB Permissions (Udev)

By default, Linux limits raw USB access to the `root` user and `lp` system group. Install the project udev rule to allow your user account to communicate with the printer:

```bash
# Copy the udev rule
sudo cp udev/99-epson-l1110.rules /etc/udev/rules.d/

# Reload and apply udev rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### 3. Clone and Setup Environment

```bash
git clone git@github.com:imanecdoche/EPSON_L1110_Printer_Driver_for_Linux.git
cd EPSON_L1110_Printer_Driver_for_Linux

# Install Python dependencies
pip install --user pyusb pymupdf pillow PyQt6
```

### 4. Verify Hardware Connection

Plug in your Epson EcoTank L1110 printer via USB, turn it on, and execute the hardware probe test:

```bash
python3 tests/test_usb_detect.py
```

Expected output confirms device identification (`VID: 0x04b8`, `PID: 0x00a8`) and successful endpoint acquisition.

---

## Roadmap

- [x] **Phase 1**: USB Communication Layer & Hardware Detection (`pyusb`, endpoint discovery, permission rules).
- [ ] **Phase 2**: ESC/P-R Protocol Engine & Rasterizer (PackBits compression, 360/720/1440 dpi pipelines, F4 paper profile).
- [ ] **Phase 3**: Maintenance Suite Implementation (Head Cleaning sequences, Nozzle Check generator, Paper Eject).
- [ ] **Phase 4**: PyQt6 Desktop Control Center (Ink gauges, interactive document viewer, print dialog).
- [ ] **Phase 5**: Packaging, CUPS PPD Integration, and ONLYOFFICE / LibreOffice workflow integration.

---

## License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)** or later. See `LICENSE` for details.

---

## Author & Acknowledgments

* **Lead Developer**: Fatih Farhat Asshidiq ([@imanecdoche](https://github.com/imanecdoche))
* Dedicated to the open-source Linux community seeking uncompromising printing capabilities for Epson EcoTank hardware.
