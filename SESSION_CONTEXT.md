# Sesi Konteks Proyek (Session Context Handover)
## Epson L1110 Custom Driver & GUI Control Center for Linux

- **Waktu Penyimpanan**: 2026-09-19 15:32 WIB
- **Tujuan Dokumen**: Melestarikan konteks kerja, arsitektur keputusan, dan status sesi percakapan agar agen/akun berikutnya dapat langsung melanjutkan tanpa kehilangan arah.
- **Lokasi Repositori**: `/media/fatihfarhat/New Volume1/PROJECTS/epson-l1110-driver`
- **Cabang Git Aktif**: `main`

---

## 1. Riwayat Diskusi & Kebutuhan Pengguna

1. **Pertanyaan Awal**:
   * Pengguna menanyakan apakah memungkinkan membuat driver printer sendiri dengan GUI custom di Linux untuk printer **Epson EcoTank L1110**.
2. **Hasil Analisis Teknis**:
   * **Sangat Memungkinkan**. Printer Epson L1110 menggunakan bahasa perintah raster **ESC/P-R** melalui port USB.
   * Direkomendasikan arsitektur *standalone user-space driver* berbasis `pyusb` / `libusb-1.0` + GUI PyQt6, dengan integrasi modul rendering PDF/Image (MuPDF / Poppler).
3. **Instruksi Pengguna**:
   * Membuat perencanaan (*planning*) dan PRD aplikasi driver + GUI.
   * Menyimpan repositori proyek di folder proyek standar: `/media/fatihfarhat/New Volume1/PROJECTS/epson-l1110-driver`.
   * Mencatat konteks sesi saat ini karena pengguna akan beralih akun.

---

## 2. Aturan Workspace & Kepatuhan Khusus

* **Aturan Global Proyek**: Telah ditambahkan aturan nomor **115** pada `.agents/RULES.md`:
  * *Direktori Proyek*: `/media/fatihfarhat/New Volume1/PROJECTS/epson-l1110-driver`
  * *Tujuan*: Driver dan GUI kustom untuk Epson L1110 di Linux (perencanaan, PRD, pipeline cetak, status & ink monitor, maintenance).
  * *Larangan Mutlak Desain*: Patuh penuh pada `ai-anti-patterns.md` — **Dilarang membuat badge/tag/pill tanpa perintah eksplisit, dan dilarang membuat komponen apa pun di luar instruksi**. Antarmuka harus murni fungsional (panel, input, kanvas pratinjau, meter bar tinta, tombol aksi).

---

## 3. Berkas & Artefak yang Sudah Dibuat

1. [**PRD.md**](./PRD.md):
   * Spesifikasi fungsional: Pengaturan cetak (kertas, resolusi 360/720/1440 dpi, CMYK/B&W), pratinjau dokumen interaktif, pemantau status & 4 tangki tinta (BK, C, M, Y), pusat pemeliharaan (*Head Cleaning*, *Nozzle Check*, *Paper Eject*).
   * Spesifikasi arsitektur: Document $\rightarrow$ Rasterizer $\rightarrow$ ESC/P-R $\rightarrow$ USB Bulk Out/In $\rightarrow$ Epson L1110.
   * Wireframe layout antarmuka 3 panel.
2. [**PLANNING.md**](./PLANNING.md):
   * Roadmap 5 Fase:
     * **Fase 1**: Eksplorasi USB & PoC Deteksi Hardware (`pyusb`, status check).
     * **Fase 2**: Pipeline Rasterizer Dokumen & Kompresi ESC/P-R (*PackBits*).
     * **Fase 3**: Modul Pemeliharaan (*Head Cleaning* & *Nozzle Pattern*).
     * **Fase 4**: Antarmuka Desktop PyQt6 dengan `QThread` non-blocking worker.
     * **Fase 5**: Packaging, konfigurasi udev, dan pengujian akhir.
3. [**README.md**](./README.md):
   * Dokumentasi pengenalan proyek, prasyarat sistem, dan panduan instalasi.
4. [**udev/99-epson-l1110.rules**](./udev/99-epson-l1110.rules):
   * Konfigurasi hak akses USB non-root untuk Vendor ID Seiko Epson (`0x04b8`).

Seluruh berkas awal telah di-commit ke Git lokal (`commit: 4e9395d`).

---

## 4. Langkah Selanjutnya (Next Steps untuk Akun / Sesi Baru)

Saat sesi dibuka kembali dengan akun baru, langkah kerja yang siap dieksekusi adalah:
1. **Verifikasi Sambungan USB Perangkat**:
   * Jalankan `lsusb` untuk memverifikasi Product ID spesifik printer Epson L1110 yang tercolok.
2. **Setup Lingkungan Virtual Python & Dependensi**:
   * Menyiapkan dependensi: `pyusb`, `PyQt6`, `pymupdf`, `pillow`.
3. **Eksekusi Fase 1 (Hardware PoC)**:
   * Buat script `src/core/usb_device.py` atau `tests/test_usb_detect.py` untuk menguji deteksi printer, pelepasan driver `usblp`, dan pembacaan query status (koneksi & level tinta).
4. **Mulai Implementasi GUI Prototype (Fase 4 Skeleton)**:
   * Membangun kerangka jendela PyQt6 sesuai wireframe PRD.
