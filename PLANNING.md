# Implementation Planning & Execution Roadmap
## Epson L1110 Custom Driver & GUI Control Center for Linux

Dokumen ini memetakan tahapan teknis, target capaian, dependensi, dan estimasi eksekusi pengembangan sistem driver dan antarmuka kontrol mandiri untuk Epson L1110.

---

## 1. Pilihan Teknologi (Tech Stack)

| Komponen | Teknologi Terpilih | Alasan Pemilihan |
| :--- | :--- | :--- |
| **Bahasa Utama** | Python 3.10+ / C++ Helper | Ekosistem GUI kuat, akses low-level USB cepat via PyUSB/libusb, proses parsing PDF matang. |
| **GUI Framework** | PyQt6 / PySide6 | Komponen grafis desktop native Linux, performa tinggi, thread-safe (`QThread`), rendering pratinjau fleksibel via `QGraphicsView` / `QPixmap`. |
| **Komunikasi USB** | `pyusb` + `libusb-1.0` | Komunikasi biner langsung ke endpoint bulk USB tanpa perlu modifikasi kernel module. |
| **PDF & Image Engine** | PyMuPDF (`fitz`) / Pillow | Render halaman PDF ke bitmap dengan presisi DPI tinggi, kecepatan rasterizing sangat cepat. |
| **ESC/P-R Engine** | Python ESC/P-R Generator + C Binding | Membungkus header Epson ESC/P-R, TIFF PackBits kompresi, dan pemisahan kanal CMYK/Grayscale. |

---

## 2. Rencana Tahapan Eksekusi (Phase by Phase)

### Fase 1: Eksplorasi Protokol & Hardware Communication PoC
* **Tujuan**: Memastikan host Linux dapat mendeteksi, mengklaim endpoint, membaca status printer, dan mengirim instruksi biner tanpa error perizinan.
* **Tugas Spesifik**:
  1. Deteksi USB ID: Identifikasi Vendor ID `0x04b8` dan Product ID Epson L1110 via `lsusb`.
  2. Setup Aturan Udev: Membuat file template `99-epson-l1110.rules` agar user Linux biasa dapat mengakses printer tanpa `sudo`.
  3. Menguji Pelepasan Driver Kernel: Script Python untuk melepaskan (*detach*) modul `usblp` secara dinamis saat aplikasi berjalan.
  4. Script Query Status: Mengirimkan perintah escape status query ke printer dan mem-parsing respons balasan biner (Status: Ready, Busy, Ink Level, Paper Out, Cover Open).
* **Deliverable Fase 1**: Script CLI `poc_status_check.py` yang berhasil menampilkan status koneksi dan level tinta printer di terminal.

---

### Fase 2: Mesin Render & Konversi ESC/P-R (Print Pipeline Engine)
* **Tujuan**: Mampu mengubah file dokumen (PDF / PNG / JPG) menjadi aliran data (*byte stream*) ESC/P-R valid yang dapat dicetak secara fisik.
* **Tugas Spesifik**:
  1. Modul Rasterizer:
     * Konversi halaman PDF ke raw RGB bitmap pada resolusi target (360 dpi untuk draft, 720 dpi untuk normal).
     * Color space conversion & dithering (Floyd-Steinberg / halftone error diffusion untuk pemisahan 4 kanal CMYK).
  2. ESC/P-R Formatter:
     * Penyusunan header job ESC/P-R (inisialisasi resolusi, panjang kertas, margin printable area).
     * Implementasi kompresi baris raster (*Run-length / PackBits compression*).
     * Penyusunan perintah footer job (Form Feed / Page Eject).
  3. Modul USB Data Streaming:
     * Pengiriman chunk data biner secara bertahap via `ep_out.write()` dengan penanganan buffer flow control.
* **Deliverable Fase 2**: Script CLI `print_test_page.py` yang berhasil mencetak 1 halaman uji ke printer fisik.

---

### Fase 3: Modul Pemeliharaan Perangkat (Maintenance Engine)
* **Tujuan**: Mengimplementasikan seluruh perintah operasional bawaan Epson untuk perawatan fisik head printer.
* **Tugas Spesifik**:
  1. Perintah *Head Cleaning*: Mengirim paket biner siklus pembersihan head tinta.
  2. Perintah *Nozzle Check Pattern*: Menghasilkan dan mengirimkan pola garis uji nozzle 4 warna standar.
  3. Perintah *Paper Feed & Eject*: Menggerakkan motor penarik kertas untuk membersihkan macet atau mengeluarkan kertas kosong.
* **Deliverable Fase 3**: Modul Python `epson_maintenance.py` yang mengeksekusi aksi-aksi pemeliharaan secara handal.

---

### Fase 4: Pengembangan GUI Desktop Kustom (PyQt6 Application)
* **Tujuan**: Membangun antarmuka desktop modern yang mudah digunakan, informatif, dan responsif.
* **Tugas Spesifik**:
  1. Window & Layout Structure:
     * Sesuai aturan desain (tanpa badge/tag/pill acak; fokus pada fungsionalitas murni).
     * Panel Kiri: Kontrol pengaturan cetak (file picker, combo box ukuran kertas, jenis kertas, DPI radio button, jumlah copies).
     * Panel Tengah: Kanvas pratinjau dokumen interaktif dengan navigasi halaman dan zoom.
     * Panel Kanan / Tab Terpisah: Visualisator meteran 4 tangki tinta EcoTank (Black, Cyan, Magenta, Yellow) dan tombol aksi cepat pemeliharaan.
  2. Multithreading & Asynchronous Worker:
     * Menggunakan `QThread` untuk proses rasterizing dan transmisi data USB agar antarmuka GUI tidak membeku (*no freeze/hang*) saat dokumen besar dicetak.
     * Progress bar transmisi real-time yang akurat.
  3. Error Handling Dialog:
     * Tampilan pesan ramah pengguna jika kertas habis, kabel terputus, atau cover printer terbuka.
* **Deliverable Fase 4**: Aplikasi desktop lengkap `epson-print-center` yang dapat dijalankan langsung.

---

### Fase 5: Pengemasan, Distribusi, & Dokumentasi
* **Tujuan**: Memudahkan deployment dan penggunaan di komputer Linux pengguna akhir.
* **Tugas Spesifik**:
  1. Pembuatan desktop launcher shortcut (`.desktop` file) beserta ikon aplikasi.
  2. Script installer otomatis (`setup.sh`) yang menginstal dependensi sistem (`python3-pyqt6`, `python3-usb`, `libusb-1.0-0`), mengonfigurasi aturan `udev`, dan mendaftarkan aplikasi.
  3. Dokumentasi lengkap cara penggunaan dan panduan penyelesaian masalah (*troubleshooting*).
* **Deliverable Fase 5**: Paket aplikasi siap pakai lengkap dengan panduan instalasi.

---

## 3. Struktur Direktori Proyek

```
epson-l1110-driver/
├── PRD.md                       # Product Requirements Document
├── PLANNING.md                  # Rencana Implementasi & Roadmap
├── README.md                    # Panduan Instalasi & Penggunaan
├── udev/
│   └── 99-epson-l1110.rules     # Aturan izin akses port USB non-root
├── src/
│   ├── __init__.py
│   ├── main.py                  # Titik masuk utama aplikasi (Entry Point)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── usb_device.py        # Komunikasi low-level USB (PyUSB / libusb)
│   │   ├── protocol_escpr.py    # Generator instruksi biner ESC/P-R
│   │   ├── rasterizer.py        # Rendering PDF/gambar ke bitmap & halftone
│   │   └── maintenance.py       # Kontrol head cleaning & nozzle check
│   └── gui/
│       ├── __init__.py
│       ├── main_window.py       # Antarmuka utama aplikasi
│       ├── preview_widget.py    # Widget kanvas pratinjau dokumen
│       ├── ink_widget.py        # Widget visualisasi level 4 tangki tinta
│       └── worker_thread.py     # Thread asynchronous pengiriman cetak
└── tests/
    ├── test_usb_detect.py       # Pengujian koneksi printer
    └── test_raster.py           # Pengujian render dokumen
```
