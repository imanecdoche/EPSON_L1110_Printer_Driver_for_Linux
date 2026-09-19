"""
Print Queue Manager for Epson L1110 Driver.
Tracks local and system (CUPS) print jobs, managing sequential execution,
progress reporting, and cancellation.
"""

import time
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class JobStatus(str, Enum):
    QUEUED = "Menunggu Antrean"
    RASTERIZING = "Meraster Dokumen..."
    PRINTING = "Sedang Mencetak..."
    COMPLETED = "Selesai"
    CANCELLED = "Dibatalkan"
    FAILED = "Gagal"


@dataclass
class PrintJob:
    """Represents a single print job in the queue."""
    job_id: str
    file_path: str
    file_name: str
    rasterizer: any
    copies: int
    total_pages: int
    reverse_order: bool = False
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    created_at: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))
    is_cups_external: bool = False
    cups_job_id: Optional[str] = None
    status_detail: str = ""

    @property
    def total_printed_pages(self) -> int:
        return max(1, self.total_pages * self.copies)


class PrintQueueManager:
    """Manages sequential queue of print jobs and synchronizes with CUPS spooler."""

    def __init__(self, cups_printer: str = "EPSON-L1110-Series"):
        self.cups_printer = cups_printer
        self.jobs: List[PrintJob] = []
        self._counter = 1

    def add_job(
        self,
        file_path: str,
        rasterizer: any,
        copies: int,
        total_pages: int,
        reverse_order: bool = False,
    ) -> PrintJob:
        """Enqueues a new document print job."""
        job_id = f"#{self._counter}"
        self._counter += 1
        file_name = os.path.basename(file_path) if file_path else "Dokumen Tanpa Nama"

        job = PrintJob(
            job_id=job_id,
            file_path=file_path,
            file_name=file_name,
            rasterizer=rasterizer,
            copies=copies,
            total_pages=total_pages,
            reverse_order=reverse_order,
            status=JobStatus.QUEUED,
            status_detail="Menunggu antrean eksekusi",
        )
        self.jobs.append(job)
        return job

    def get_next_queued_job(self) -> Optional[PrintJob]:
        """Returns the first waiting local print job."""
        for job in self.jobs:
            if job.status == JobStatus.QUEUED and not job.is_cups_external:
                return job
        return None

    def get_active_job(self) -> Optional[PrintJob]:
        """Returns the currently active printing job, if any."""
        for job in self.jobs:
            if job.status in (JobStatus.RASTERIZING, JobStatus.PRINTING):
                return job
        return None

    def cancel_job(self, job_id: str) -> Optional[PrintJob]:
        """Marks a job as cancelled, and cancels CUPS job if external."""
        for job in self.jobs:
            if job.job_id == job_id:
                if job.is_cups_external and job.cups_job_id:
                    try:
                        subprocess.run(
                            ["cancel", job.cups_job_id],
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                    except Exception:
                        pass
                job.status = JobStatus.CANCELLED
                job.status_detail = "Dibatalkan oleh pengguna"
                return job
        return None

    def clear_finished(self):
        """Removes completed, cancelled, and failed jobs from the queue."""
        self.jobs = [
            j for j in self.jobs
            if j.status in (JobStatus.QUEUED, JobStatus.RASTERIZING, JobStatus.PRINTING)
        ]

    def sync_cups_jobs(self):
        """Discovers any external jobs queued in CUPS for EPSON-L1110-Series."""
        try:
            res = subprocess.run(
                ["lpstat", "-o", self.cups_printer],
                capture_output=True,
                text=True,
                check=False,
            )
            output = res.stdout.strip()
            current_cups_ids = set()

            if output:
                for line in output.splitlines():
                    parts = line.split()
                    if parts:
                        cups_id = parts[0]  # e.g. EPSON-L1110-Series-42
                        current_cups_ids.add(cups_id)

                        # Check if this external job is already known
                        exists = any(j.cups_job_id == cups_id for j in self.jobs)
                        if not exists:
                            owner = parts[1] if len(parts) > 1 else "user"
                            size_info = f"{parts[2]} bytes" if len(parts) > 2 else ""
                            c_job = PrintJob(
                                job_id=cups_id,
                                file_path="",
                                file_name=f"Tugas Sistem CUPS ({owner})",
                                rasterizer=None,
                                copies=1,
                                total_pages=1,
                                reverse_order=False,
                                status=JobStatus.PRINTING if "printing" in line.lower() else JobStatus.QUEUED,
                                is_cups_external=True,
                                cups_job_id=cups_id,
                                status_detail=size_info or "Mengantre di spooler sistem",
                            )
                            self.jobs.append(c_job)

            # Auto-complete or remove CUPS jobs that have left the spooler
            for j in list(self.jobs):
                if j.is_cups_external and j.cups_job_id not in current_cups_ids:
                    if j.status not in (JobStatus.CANCELLED, JobStatus.FAILED):
                        j.status = JobStatus.COMPLETED
                        j.status_detail = "Selesai dicetak oleh spooler"
        except Exception:
            pass
