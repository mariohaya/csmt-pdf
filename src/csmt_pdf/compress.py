"""PDF compression using the system Ghostscript executable."""

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import tempfile


PRESETS = {"a little": "/printer", "somewhat": "/ebook", "a lot": "/screen"}


class CompressionError(Exception):
    """An expected, user-facing compression failure."""


@dataclass(frozen=True)
class CompressionResult:
    output: Path | None
    original_bytes: int
    compressed_bytes: int


def compress_pdf(filename: str | Path, level: str) -> CompressionResult:
    """Publish a smaller PDF beside the input without overwriting any file."""
    if level not in PRESETS:
        raise CompressionError("Choose a little, somewhat, or a lot.")
    source = Path(filename).expanduser().absolute()
    if not source.is_file():
        raise CompressionError(f"File not found: {source}")
    if source.suffix.lower() != ".pdf":
        raise CompressionError("Choose a file with a .pdf extension.")
    with source.open("rb") as stream:
        if b"%PDF-" not in stream.read(1024):
            raise CompressionError("This file does not appear to be a PDF.")
    gs = shutil.which("gs")
    if gs is None:
        raise CompressionError("Ghostscript is missing. Install it with: sudo pacman -S ghostscript")
    before = source.stat().st_size
    # Same filesystem allows atomic publication without overwriting existing files.
    with tempfile.TemporaryDirectory(prefix=".csmt-pdf-", dir=source.parent) as directory:
        candidate = Path(directory) / "compressed.pdf"
        completed = subprocess.run(
            [gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.7",
             f"-dPDFSETTINGS={PRESETS[level]}", "-dNOPAUSE", "-dBATCH",
             "-dSAFER", "-dPDFSTOPONERROR", "-q",
             f"-sOutputFile={candidate}", "-f", str(source)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, errors="replace", check=False,
        )
        if completed.returncode != 0:
            raise CompressionError("Ghostscript could not process this PDF. It may be damaged or password-protected.")
        if not candidate.is_file() or candidate.stat().st_size == 0:
            raise CompressionError("Ghostscript did not produce a PDF.")
        with candidate.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise CompressionError("Ghostscript did not produce a valid PDF header.")
        after = candidate.stat().st_size
        if after >= before:
            return CompressionResult(None, before, after)
        counter = 0
        while True:
            suffix = "" if counter == 0 else f"_{counter}"
            output = source.with_name(f"{source.stem}_compressed{suffix}.pdf")
            try:
                os.link(candidate, output)
                break
            except FileExistsError:
                counter += 1
        return CompressionResult(output, before, after)
