# Product Requirements Document (PRD)
## Epson L1110 Custom Driver & GUI Control Center for Linux

- **Nama Proyek**: Epson L1110 Driver & Print Center
- **Target Platform**: Linux (Ubuntu, Debian, Fedora, Arch Linux, Linux Mint)
- **Target Perangkat**: Printer Inkjet Epson EcoTank L1110 (USB Connection)
- **Status Dokumen**: DRAFT / APPROVED FOR PLANNING
- **Versi Dokumen**: 1.0.0

---

## 1. Pendahuluan & Latar Belakang

### 1.1 Masalah Saat Ini
Pengguna printer Epson L1110 di lingkungan Linux umumnya menghadapi kendala:
1. **Driver Resmi Terbatas**: Driver Epson bawaan Linux (`epson-inkjet-printer-escpr`) hanya menyediakan filter CUPS dasar tanpa utility GUI resmi seperti di Windows/macOS.
2. **Tidak Ada Pemantau Status & Tinta Asli**: Pengguna tidak dapat memantau status printer secara akurat (level tinta, peringatan error, paper jam, cover terbuka) melalui antarmuka visual modern.
3. **Fitur Maintenance Sulit Diakses**: Melakukan *head cleaning* dan *nozzle check* sering kali memerlukan command line rumit atau instalasi perkakas pihak ketiga yang usang.
4. **Dialog Cetak Tidak Terintegrasi**: Dialog cetak default Linux tidak memiliki fitur pratinjau warna dan pengaturan fine-tuning spesifik untuk head piezoelektrik Epson L1110.

### 1.2 Tujuan Proyek
Membangun solusi perangkat lunak cetak mandiri (*standalone*) dan/atau terintegrasi yang menyediakan:
* Driver komunikasi biner langsung (ESC/P-R via USB) ke hardware Epson L1110.
* Antarmuka grafis (GUI) modern, responsif, dan fungsional untuk kontrol cetak lengkap.
* Sistem pemantauan status dua arah (bidirectional query) untuk level tinta dan notifikasi error perangkat keras.
* Pusat perawatan printer (Maintenance Hub: Head Cleaning, Nozzle Check, Printhead Alignment).

---

## 2. Arsitektur Sistem

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CUSTOM GUI LAYER                              │
│  (PyQt6 / Native GUI Framework - Preview, Settings, Maintenance, Ink)   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       PRINT JOB & PIPELINE ENGINE                       │
│                                                                         │
│  ┌───────────────────────┐             ┌─────────────────────────────┐  │
│  │ Document Rasterizer   │             │   ESC/P-R Encoder           │  │
│  │ (PDF / Image Parser)  │ ──Bitmap──> │   - Run-length/PackBits     │  │
│  │ (MuPDF / Poppler)     │             │   - MicroWeave / Halftone   │  │
│  └───────────────────────┘             └──────────────┬──────────────┘  │
└───────────────────────────────────────────────────────┼─────────────────┘
                                                        │ Raw Byte Stream
                                                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       USB I/O & PROTOCOL SERVICE                        │
│                 (libusb-1.0 / PyUSB / Device Manager)                   │
│                                                                         │
│   • Bulk OUT: Pengiriman Print Job Stream & Maintenance Commands        │
│   • Bulk IN : Query Status Perangkat (Level Tinta, Paper Jam, Ready)    │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ USB Cable (Vendor 0x04b8)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       HARDWARE EPSON ECOTANK L1110                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Fitur Utama & Spesifikasi Fungsional

### 3.1 Modul Pengaturan Cetak (Print Configuration)
* **Pilihan Ukuran Kertas**:
  * A4 (210 x 297 mm) — default
  * Letter (8.5 x 11 inci)
  * Legal (8.5 x 14 inci)
  * Photo 4x6 / 10x15 cm
  * Custom Dimensions (User defined)
* **Jenis Media Kertas (Media Type)**:
  * Plain Paper (Kertas HVS Biasa)
  * Epson Matte
  * Epson Premium Glossy
  * Photo Paper Glossy
  * Envelope
* **Kualitas Cetak (Print Quality & Resolution)**:
  * *Draft / Fast* (360 x 360 dpi) — hemat tinta, cepat
  * *Standard / Normal* (720 x 720 dpi) — dokumen teks & grafis standar
  * *High / Fine* (1440 x 720 dpi) — dokumen presentasi / warna pekat
  * *Best / Photo* (5760 x 1440 dpi optimized) — cetak foto beresolusi tinggi
* **Mode Warna**:
  * Full Color (CMYK Process)
  * Grayscale / Black & White Only
* **Orientasi & Skala**:
  * Portrait / Landscape
  * Fit to Printable Area / 100% Actual Size / Custom Scaling %
  * Number of Copies & Collated checkbox

### 3.2 Modul Pratinjau Interaktif (Live Preview Area)
* Render dokumen secara real-time berdasarkan pengaturan orientasi, margin, dan skala.
* Navigasi multi-halaman (First, Prev, Next, Last, Page Selector: `1-5, 8`).
* Indikator garis batas cetak aman (*printable margin guide*).
* Tombol aksi: Zoom In, Zoom Out, Reset View, Rotasi 90 derajat.

### 3.3 Modul Pemantauan Status & Level Tinta (Status & Ink Monitor)
* **Koneksi Real-Time**:
  * Deteksi otomatis status koneksi kabel USB printer (*Connected*, *Offline*, *Busy / Printing*, *Error*).
* **Indikator Level Tinta (4 Tangki EcoTank)**:
  * Black (BK - 003)
  * Cyan (C - 003)
  * Magenta (M - 003)
  * Yellow (Y - 003)
  * Disajikan dalam bentuk meteran bar vertikal terkalibrasi dengan persentase angka.
* **Deteksi Kode Error Hardware**:
  * Penutup atas terbuka (*Cover Open*).
  * Kertas habis atau macet (*Out of Paper* / *Paper Jam*).
  * Ink pad waste counter nearing limit / service required.

### 3.4 Modul Pemeliharaan Printer (Maintenance Tools)
* **Print Head Cleaning**: Mengirimkan instruksi pembersihan nozzle head ke printer dengan visualisasi progress bar estimasi waktu.
* **Nozzle Check Pattern**: Mencetak pola garis uji nozzle 4 warna untuk mendeteksi nozzle yang tersumbat (*clogged*).
* **Power Ink Flushing**: Perintah pengisian tinta intensif (dengan konfirmasi keamanan pengguna).
* **Paper Feed & Eject**: Mengeluarkan atau memajukan kertas secara manual.
* **Head Alignment Calibration**: Halaman cetak pola penyelarasan vertikal dan horizontal.

### 3.5 Modul Manajemen Antrean Cetak (Job Manager)
* Status pencetakan aktif: Persentase halaman terkirim, kecepatan transmisi data USB.
* Tombol pembatalan darurat (*Cancel Print Job*) yang langsung mengirimkan sinyal flush/reset ke printer dan membuang sisa buffer data.

---

## 4. Spesifikasi Desain GUI (Antarmuka Pengguna)

### 4.1 Prinsip Desain
* **Struktur Bersih & Fungsional**: Mengutamakan hierarki data yang jelas, tombol aksi tegas, dan kontrol terorganisasi rapi.
* **Kepatuhan Aturan Desain**: Sesuai instruksi mutlak, dilarang menambahkan badge, tag, atau pill acak yang tidak memiliki fungsi struktural. Seluruh elemen merupakan kontrol fungsional murni (input field, radio group, dropdown select, meter progress, dan button).

### 4.2 Wireframe Layout Konsep

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ Epson L1110 Print & Maintenance Center                                        [ - ] [ X ] │
├───────────────────────────────────────────────────────────────────────────────────────────┤
│ [ Tab: Cetak Dokumen ]  [ Tab: Status & Tinta ]  [ Tab: Pemeliharaan (Maintenance) ]       │
├──────────────────────────┬─────────────────────────────────────┬──────────────────────────┤
│ PANEL PENGATURAN CETAK   │ PRATINJAU DOKUMEN (PREVIEW)         │ STATUS & LEVEL TINTA     │
│                          │                                     │                          │
│ File Dokumen:            │ ┌─────────────────────────────────┐ │ Status: Siap Mencetak    │
│ [ dokumen_laporan.pdf  ] │ │                                 │ │ Model : Epson L1110 USB  │
│ [ Pilih File... ]        │ │                                 │ │ Port  : /dev/usb/lp0     │
│                          │ │          [ DOKUMEN ]            │ │                          │
│ Kertas & Ukuran:         │ │                                 │ │ Level Tinta Estimasi:    │
│ [ A4 (210 x 297 mm)   v] │ │                                 │ │  BK     C     M     Y    │
│                          │ │                                 │ │ ┌──┐  ┌──┐  ┌──┐  ┌──┐   │
│ Jenis Kertas:            │ │                                 │ │ │  │  │  │  │  │  │  │   │
│ [ Kertas Biasa (Plain)v] │ │                                 │ │ │██│  │██│  │██│  │██│   │
│                          │ └─────────────────────────────────┘ │ │██│  │██│  │██│  │██│   │
│ Kualitas Cetak:          │ Kontrol Halaman:                    │ └──┘  └──┘  └──┘  └──┘   │
│ ( ) Draft (360 dpi)      │ [ << ] [ < ] Hal 1 / 4 [ > ] [ >> ] │  85%   90%   65%   70%   │
│ (•) Standar (720 dpi)    │ [ Fit Window ] [ 100% ] [ Rotate ]  ├──────────────────────────┤
│ ( ) Tinggi (1440 dpi)    │                                     │ AKSI CEPAT               │
│                          │ Progress Transmisi:                 │ [ Uji Nozzle (Check)   ] │
│ Mode Warna:              │ [====================       ] 65%   │ [ Pembersihan Head     ] │
│ (•) Berwarna  ( ) Hitam  │                                     │                          │
│                          │                                     │                          │
│ Jumlah Salinan: [ 1 ]    │                                     │                          │
├──────────────────────────┴─────────────────────────────────────┴──────────────────────────┤
│ [ Batal Cetak ]                                                    [ CETAK SEKARANG >> ]  │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Spesifikasi Teknis & Komunikasi Perangkat

### 5.1 Identitas Hardware USB
* **Vendor ID (VID)**: `0x04b8` (Seiko Epson Corp.)
* **Product ID (PID)**: `0x1142` (atau sesuai serial revisi L1110)
* **USB Class**: `0x07` (Printer Device Class)
* **Interface**: Interface 0, Alternate Setting 0
  * Bulk OUT Endpoint: `0x01` (Host ke Printer — Print data stream)
  * Bulk IN Endpoint: `0x82` (Printer ke Host — Device status response)

### 5.2 Bahasa Perintah Cetak (Page Description Language)
* **Bahasa**: Epson ESC/P-R (Epson Standard Code for Printers - Raster)
* **Inisialisasi Header**:
  * ESC `@` (Reset)
  * ESC `( G` (Enable ESC/P-R mode)
  * ESC `( U` (Unit setting / resolution)
  * ESC `( C` (Page length setting)
  * ESC `( c` (Page margin setting)
* **Raster Data Compression**: Run-length / PackBits compression per baris dot warna (Cyan, Magenta, Yellow, Black).

---

## 6. Persyaratan Non-Fungsional (NFR)

* **Performa**: Latensi rendering pratinjau halaman pertama di bawah 1,5 detik untuk file PDF 10 halaman standar.
* **Stabilitas Transmisi USB**: Buffer pengiriman data USB memiliki mekanisme auto-retry dan deteksi *buffer full* agar print job tidak terputus di tengah jalan.
* **Hak Akses Sistem**: Aplikasi menyediakan konfigurasi aturan `udev` (`/etc/udev/rules.d/99-epson-l1110.rules`) agar pengguna non-root dapat mengakses USB endpoint printer tanpa `sudo`.
* **Portabilitas**: Dapat dijalankan tanpa kompilasi kernel module khusus; berjalan sepenuhnya di *user-space*.
