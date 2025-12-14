"""Compression utilities for corpus snapshots."""

from __future__ import annotations

import gzip
import logging
import shutil
import tarfile
from pathlib import Path
from typing import Literal

from web_scraper.exceptions import generate_correlation_id
from web_scraper.utils import log_with_correlation

LOGGER = logging.getLogger(__name__)

CompressionMode = Literal["gzip", "archive", "none"]


def compress_file(file_path: Path) -> Path:
    """
    Compress a single file with gzip.

    Args:
        file_path: Path to the file to compress.

    Returns:
        Path to the compressed file (.gz extension added).
    """
    output_path = file_path.with_suffix(file_path.suffix + ".gz")

    with file_path.open("rb") as f_in:
        with gzip.open(output_path, "wb", compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)

    return output_path


def decompress_file(gz_path: Path) -> Path:
    """
    Decompress a gzipped file.

    Args:
        gz_path: Path to the .gz file.

    Returns:
        Path to the decompressed file.
    """
    if not gz_path.suffix == ".gz":
        raise ValueError(f"Expected .gz file, got: {gz_path}")

    output_path = gz_path.with_suffix("")

    with gzip.open(gz_path, "rb") as f_in:
        with output_path.open("wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    return output_path


def compress_snapshot(
    snapshot_path: Path,
    mode: CompressionMode = "archive",
    remove_originals: bool = True,
) -> Path:
    """
    Compress a snapshot directory.

    Args:
        snapshot_path: Path to the snapshot directory.
        mode: Compression mode:
            - "gzip": Compress each file individually (.gz)
            - "archive": Create a single .tar.gz archive
            - "none": No compression
        remove_originals: If True, remove original files after compression.

    Returns:
        Path to the compressed output (archive file or snapshot directory).
    """
    correlation_id = generate_correlation_id()

    if mode == "none":
        log_with_correlation(
            LOGGER,
            logging.INFO,
            "Compression disabled, no changes made",
            correlation_id=correlation_id,
            snapshot_path=str(snapshot_path),
        )
        return snapshot_path

    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    if mode == "archive":
        return _create_archive(snapshot_path, remove_originals, correlation_id)
    elif mode == "gzip":
        return _compress_files(snapshot_path, remove_originals, correlation_id)
    else:
        raise ValueError(f"Unknown compression mode: {mode}")


def _create_archive(
    snapshot_path: Path,
    remove_originals: bool,
    correlation_id: str,
) -> Path:
    """Create a .tar.gz archive of the snapshot."""
    archive_path = snapshot_path.with_suffix(".tar.gz")

    log_with_correlation(
        LOGGER,
        logging.INFO,
        f"Creating archive: {archive_path}",
        correlation_id=correlation_id,
        archive_path=str(archive_path),
    )

    # Calculate original size
    original_size = sum(f.stat().st_size for f in snapshot_path.rglob("*") if f.is_file())

    with tarfile.open(archive_path, "w:gz", compresslevel=9) as tar:
        # Add all files with relative paths
        for file_path in snapshot_path.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(snapshot_path.parent)
                tar.add(file_path, arcname=arcname)

    compressed_size = archive_path.stat().st_size
    ratio = (1 - compressed_size / original_size) * 100 if original_size else 0

    log_with_correlation(
        LOGGER,
        logging.INFO,
        f"Archive created: {original_size} -> {compressed_size} ({ratio:.1f}% reduction)",
        correlation_id=correlation_id,
        original_size=original_size,
        compressed_size=compressed_size,
        reduction_percent=round(ratio, 1),
    )

    if remove_originals:
        shutil.rmtree(snapshot_path)
        log_with_correlation(
            LOGGER,
            logging.INFO,
            "Removed original snapshot directory",
            correlation_id=correlation_id,
        )

    return archive_path


def _compress_files(
    snapshot_path: Path,
    remove_originals: bool,
    correlation_id: str,
) -> Path:
    """Compress each file in the snapshot individually."""
    files_compressed = 0
    original_size = 0
    compressed_size = 0

    for file_path in snapshot_path.rglob("*"):
        if file_path.is_file() and not file_path.suffix == ".gz":
            original_size += file_path.stat().st_size
            gz_path = compress_file(file_path)
            compressed_size += gz_path.stat().st_size
            files_compressed += 1

            if remove_originals:
                file_path.unlink()

    ratio = (1 - compressed_size / original_size) * 100 if original_size else 0

    log_with_correlation(
        LOGGER,
        logging.INFO,
        f"Compressed {files_compressed} files ({ratio:.1f}% reduction)",
        correlation_id=correlation_id,
        files_compressed=files_compressed,
        reduction_percent=round(ratio, 1),
    )

    return snapshot_path


def extract_archive(archive_path: Path, target_dir: Path | None = None) -> Path:
    """
    Extract a .tar.gz archive.

    Args:
        archive_path: Path to the .tar.gz archive.
        target_dir: Directory to extract to. Defaults to archive parent.

    Returns:
        Path to the extracted snapshot directory.
    """
    if not archive_path.suffix == ".gz" or not archive_path.stem.endswith(".tar"):
        raise ValueError(f"Expected .tar.gz file, got: {archive_path}")

    if target_dir is None:
        target_dir = archive_path.parent

    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(path=target_dir)

    # Return the extracted directory (snapshot name without .tar.gz)
    snapshot_name = archive_path.stem[:-4]  # Remove .tar
    return target_dir / snapshot_name

