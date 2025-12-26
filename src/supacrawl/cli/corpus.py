"""Corpus management commands (snapshots, chunks, compression)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from supacrawl.cli._common import app
from supacrawl.config import default_corpora_dir
from supacrawl.corpus.compress import compress_snapshot, extract_archive
from supacrawl.exceptions import SupacrawlError
from supacrawl.prep.chunker import chunk_snapshot




@app.command("list-snapshots", help="List snapshots for a site.")
@click.argument("site_name")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing corpora/ folder.",
)
def list_snapshots(site_name: str, base_path: Path | None) -> None:
    """
    List all snapshots for a site with metadata.

    Args:
        site_name: Name of the site.
        base_path: Optional base directory containing corpora/ folder.
    """
    import json

    from supacrawl.corpus.symlink import LATEST_SYMLINK_NAME

    corpora_dir = default_corpora_dir(base_path)
    site_dir = corpora_dir / site_name

    if not site_dir.exists():
        click.echo(f"No snapshots found for site: {site_name}")
        return

    snapshots = []
    for item in site_dir.iterdir():
        # Skip the 'latest' symlink
        if item.name == LATEST_SYMLINK_NAME:
            continue
        if not item.is_dir():
            continue

        manifest_path = item / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text())
            status = manifest.get("status", "unknown")
            total_pages = manifest.get("total_pages", 0)
            created_at = manifest.get("created_at", "unknown")

            # Check for chunks
            chunks_path = item / "chunks.jsonl"
            if chunks_path.exists():
                chunk_count = sum(1 for _ in chunks_path.read_text().splitlines())
            else:
                chunk_count = None

            snapshots.append(
                {
                    "id": item.name,
                    "status": status,
                    "pages": total_pages,
                    "chunks": chunk_count,
                    "created_at": created_at,
                }
            )
        except Exception:
            continue

    # Sort by snapshot ID descending (most recent first)
    snapshots.sort(key=lambda s: s["id"], reverse=True)

    if not snapshots:
        click.echo(f"No snapshots found for site: {site_name}")
        return

    # Print table
    for snap in snapshots:
        chunks_str = f"{snap['chunks']:>4}" if snap["chunks"] is not None else "   -"
        click.echo(
            f"{snap['id']}  {snap['status']:<10}  {snap['pages']:>4} pages  "
            f"{chunks_str} chunks  {snap['created_at']}"
        )

@app.command("chunk", help="Chunk a snapshot into JSONL output.")
@click.argument("site_id")
@click.argument("snapshot_id")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing sites/ and corpora/ folders.",
)
@click.option(
    "--max-chars",
    type=int,
    default=1200,
    show_default=True,
    help="Approximate maximum characters per chunk.",
)
@click.option(
    "--summarize",
    is_flag=True,
    default=False,
    help="Add summaries to chunks using LLM. Requires LLM env vars (LLM_PROVIDER, LLM_MODEL).",
)
def chunk(
    site_id: str,
    snapshot_id: str,
    base_path: Path | None,
    max_chars: int,
    summarize: bool,
) -> None:
    """
    Chunk snapshot pages into JSONL records.

    Args:
        site_id: Site identifier.
        snapshot_id: Snapshot identifier.
        base_path: Optional base directory containing corpora/ folder.
        max_chars: Maximum characters per chunk. Defaults to 1200.
        summarize: Whether to add summaries to chunks using LLM.

    Raises:
        click.ClickException: If the snapshot is not found or chunking fails.
    """
    corpora_dir = default_corpora_dir(base_path)
    snapshot_path = corpora_dir / site_id / snapshot_id
    if not snapshot_path.exists():
        msg = f"Snapshot not found at {snapshot_path}. Check that the site_id and snapshot_id are correct."
        click.echo(f"Error: {msg}", err=True)
        raise SystemExit(1)

    try:
        output_path = asyncio.run(
            chunk_snapshot(
                snapshot_path,
                max_chars=max_chars,
                summarize=summarize,
            )
        )
        # Count chunks
        chunk_count = sum(1 for _ in output_path.read_text().splitlines())
        click.echo(f"Generated {chunk_count} chunks")
        # Show output path - respect base_path
        if base_path is None:
            if snapshot_id == "latest":
                click.echo(f"Output: corpora/{site_id}/latest/chunks.jsonl")
            else:
                click.echo(f"Output: corpora/{site_id}/{snapshot_id}/chunks.jsonl")
        else:
            if snapshot_id == "latest":
                click.echo(f"Output: {base_path}/corpora/{site_id}/latest/chunks.jsonl")
            else:
                click.echo(
                    f"Output: {base_path}/corpora/{site_id}/{snapshot_id}/chunks.jsonl"
                )
    except SupacrawlError as exc:
        click.echo(
            f"Error: {exc.message} [correlation_id={exc.correlation_id}]", err=True
        )
        raise SystemExit(1) from exc

@app.command("compress", help="Compress a snapshot for archival.")
@click.argument("site_id")
@click.argument("snapshot_id")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Base directory containing corpora/ folder.",
)
@click.option(
    "--mode",
    type=click.Choice(["archive", "gzip", "none"]),
    default="archive",
    show_default=True,
    help="Compression mode: 'archive' creates .tar.gz, 'gzip' compresses each file.",
)
@click.option(
    "--keep-originals",
    is_flag=True,
    default=False,
    help="Keep original files after compression.",
)
def compress(
    site_id: str,
    snapshot_id: str,
    base_path: Path | None,
    mode: str,
    keep_originals: bool,
) -> None:
    """
    Compress a snapshot for archival or transfer.

    Args:
        site_id: Site identifier.
        snapshot_id: Snapshot identifier.
        base_path: Optional base directory containing corpora/ folder.
        mode: Compression mode (archive, gzip, none).
        keep_originals: If True, keep original files.
    """
    corpora_dir = default_corpora_dir(base_path)
    snapshot_path = corpora_dir / site_id / snapshot_id

    if not snapshot_path.exists():
        click.echo(f"Error: Snapshot not found at {snapshot_path}", err=True)
        raise SystemExit(1)

    try:
        output_path = compress_snapshot(
            snapshot_path,
            mode=mode,  # type: ignore[arg-type]
            remove_originals=not keep_originals,
        )
        if mode == "archive":
            click.echo(f"Archive created: {output_path}")
        elif mode == "gzip":
            click.echo(f"Files compressed in: {output_path}")
        else:
            click.echo("No compression applied.")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc

@app.command("extract", help="Extract a compressed snapshot archive.")
@click.argument("archive_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--target-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Directory to extract to. Defaults to archive location.",
)
def extract(archive_path: Path, target_dir: Path | None) -> None:
    """
    Extract a compressed snapshot archive.

    Args:
        archive_path: Path to the .tar.gz archive.
        target_dir: Optional target directory for extraction.
    """
    try:
        output_path = extract_archive(archive_path, target_dir)
        click.echo(f"Extracted to: {output_path}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc
