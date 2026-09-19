# Epson L1110 Custom Driver & Print Center for Linux

Aplikasi driver dan pusat kontrol antarmuka grafis (GUI) mandiri (*standalone*) untuk printer inkjet **Epson EcoTank L1110** pada sistem operasi Linux. 

Proyek ini dirancang untuk mengatasi keterbatasan utilitas printer bawaan Linux dengan menyediakan kontrol penuh langsung via protokol biner USB (**ESC/P-R**), pemantau level tinta 4 warna real-time, pratinjau dokumen interaktif, serta modul pemeliharaan hardware (*Head Cleaning* & *Nozzle Check*).

---

## 📑 Dokumentasi Utama
* 📄 [**Product Requirements Document (PRD)**](./PRD.md): Spesifikasi lengkap fungsionalitas, wireframe layout GUI, dan arsitektur teknis.
* 📋 [**Implementation Planning & Roadmap**](./PLANNING.md): Tahapan eksekusi dari pembacaan USB biner, mesin rasterizer, hingga pembuatan antarmuka PyQt6.

---

## ✨ Fitur Unggulan

1. **Komunikasi Biner USB Mandiri**:
   * Menggunakan pustaka `pyusb` dan `libusb-1.0` untuk mengakses USB endpoint printer secara langsung tanpa ketergantungan pada daemon CUPS.
2. **Pemantau Status & Level Tinta Real-Time**:
   * Melakukan kueri dua arah (*bidirectional status query*) ke mikrokontroler Epson untuk membaca estimasi level tangki tinta (Black, Cyan, Magenta, Yellow) serta deteksi status fisik (Paper Out, Paper Jam, Cover Open).
3. **Pusat Pemeliharaan (Maintenance Suite)**:
   * Menjalankan prosedur *Print Head Cleaning* langsung dari antarmuka GUI.
   * Mencetak pola uji *Nozzle Check Pattern* 4 warna standar.
   * Perintah manual *Paper Feed & Eject*.
4. **Pratinjau & Pengaturan Cetak Fleksibel**:
   * Rendering halaman PDF dan gambar langsung di kanvas antarmuka.
   * Kontrol ukuran kertas (A4, Letter, Photo 4x6, Custom), pemilihan resolusi (Draft 360 dpi, Standard 720 dpi, High 1440 dpi), dan mode warna (Color / Grayscale).

---

## 🛠️ Kebutuhan Sistem & Prasyarat

* **OS**: Linux (Kernel 5.x / 6.x)
* **Python**: Versi 3.10 atau lebih baru
* **Paket Sistem**:
  ```bash
  sudo apt install libusb-1.0-0-dev python3-pyqt6 poppler-utils
  ```
* **Paket Python**:
  ```bash
  pip install pyusb pymupdf pillow
  ```

---

## 🚀 Izin Akses USB (Udev Configuration)

Agar aplikasi dapat mengakses perangkat USB Epson L1110 tanpa hak akses `root` (`sudo`), pasang aturan `udev`:

```bash
# Tambahkan aturan udev untuk Vendor ID Seiko Epson (0x04b8)
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="04b8", MODE="0666"' | sudo tee /etc/udev/rules.d/99-epson-l1110.rules

# Muat ulang aturan udev
sudo udevadm control --reload-rules && sudo udevadm trigger
```

---

## 📂 Struktur Repositori

```
epson-l1110-driver/
├── PRD.md                       # Product Requirements Document
├── PLANNING.md                  # Tahapan Teknis & Timeline
├── README.md                    # Panduan Memulai Proyek
├── udev/                        # Konfigurasi perizinan USB Linux
├── src/
│   ├── core/                    # Low-level USB, ESC/P-R engine, & rasterizer
│   └── gui/                     # Antarmuka pengguna PyQt6 & custom widgets
└── tests/                       # Unit test & script pengujian hardware
```
