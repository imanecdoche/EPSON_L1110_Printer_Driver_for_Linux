---
type: bug
topic: Epson L1110 Empty Paper Spooling Fix and CUPS Driver Filter Pipeline
date: 2026-09-19
tags: [epson-l1110, cups, printing, escpr, rasterizer]
---

## Summary
Fixed continuous empty paper spooling loop by eliminating rogue CRLF bytes from raster bands and replacing raw bypass (`-o raw`) with high-fidelity PDF rendering piped through the official Epson CUPS filter (`epson-escpr`).

## Context
When clicking Print in the GUI, the Epson EcoTank L1110 continuously pulled and ejected blank sheets repeatedly without depositing any ink.

## Decision / Finding
1. `src/core/escpr_protocol.py` appended `\r\n` to every raster row (8,400+ CRLFs per page).
2. `src/gui/worker_thread.py` submitted raw bytes via `lp -d EPSON-L1110-Series -o raw`.
3. Bypassing CUPS filters forced the printer into plain ASCII text mode, where each `\r\n` advanced the feed mechanism by 1 line (1/6 inch), triggering automatic form feeds every ~66 lines (~140 blank pages).
4. The system has official Seiko Epson driver packages installed (`epson-inkjet-printer-escpr 1.8.8-1`) with filter `/opt/epson-inkjet-printer-escpr/cups/lib/filter/epson-escpr-wrapper`.
5. Solution:
   - Render document pages with user margins, scaling (fit/actual/custom), and drag offset into high-fidelity PDF via `DocumentRasterizer.generate_print_pdf()`.
   - Submit through CUPS standard queue with `PageSize`, `MediaType`, `Ink`, and `fit-to-page=false` WITHOUT `-o raw`.

## Rationale
The EcoTank L1110 requires genuine ESC/P-R packets with proper micro-stepping, multi-size ink drop matrices, and nozzle head sweeps. Only the official Seiko Epson filter or a full ESC/P-R compiler can generate these. Sending raw unformatted raster dumps bypasses CUPS and breaks paper feeding.

## Consequences
- Printing works reliably with physical ink deposition.
- No wasted paper or uncontrolled spooling loops.
- Custom margins, scaling modes, and interactive drag positioning are preserved 1:1 onto physical paper.

## References
- `.agents/RULES.md` Rule 128
- `src/core/rasterizer.py`
- `src/gui/worker_thread.py`
- Commit `d848a91`
