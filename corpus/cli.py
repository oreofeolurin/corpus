import json
import os
import sys
from typing import List, Optional

import typer

from . import __version__
from .capture import CaptureOptions, capture_video
from .doctor import diagnose_environment
from .inspect import inspect_artifact
from .clean import delete_artifact, list_artifacts
from .batch import run_batch
from .pack import PackConfig, pack_directory
from .remote_repo import fetch_repo_checkout
from .mcp.catalog import add_collection, remove_collection, load_catalog
app = typer.Typer(
    help=(
        "Corpus CLI: extract and package datasets from multiple sources for data science workflows. "
        "Includes YouTube capture (metadata/transcripts/screenshots), batch processing, packing directories, "
        "inspection, cleaning, and environment diagnostics."
    )
)

mcp_app = typer.Typer(help="MCP server and multi-collection registry")

@app.command(hidden=True)
def mcp_serve(
    source: Optional[str] = typer.Option(None, "--source", help="Optional path; omit to serve the catalog"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
) -> None:
    """Serve MCP over HTTP. Defaults to catalog mode when --source is not provided."""
    import uvicorn
    from .mcp.http_server import create_app

    app_ = create_app(source)
    uvicorn.run(app_, host=host, port=port, log_level="info")


@app.command(hidden=True)
def mcp_http(
    source: str = typer.Option(..., "--source", help="Path to corpus-out bundle or directory"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
) -> None:
    """Run HTTP MCP server (FastAPI)."""
    import uvicorn
    from .mcp.http_server import create_app
    from .mcp.catalog import add_collection, remove_collection, load_catalog

    app = create_app(source)
    uvicorn.run(app, host=host, port=port, log_level="info")


@app.command(hidden=True)
def mcp_add(
    id: str = typer.Option(..., "--id"),
    source: str = typer.Option(..., "--source"),
    name: Optional[str] = typer.Option(None, "--name"),
    type: str = typer.Option("auto", "--type"),
    tags: Optional[str] = typer.Option(None, "--tags", help="comma-separated"),
) -> None:
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    path = add_collection(id, source, name=name, type=type, tags=tag_list)
    typer.echo(path)


@app.command(hidden=True)
def mcp_rm(id: str = typer.Option(..., "--id")) -> None:
    path = remove_collection(id)
    typer.echo(path)


@app.command(hidden=True)
def mcp_ls(stats: bool = typer.Option(False, "--stats", help="Show collection statistics")) -> None:
    def format_bytes(bytes_val):
        if bytes_val >= 1024**3:
            return f"{bytes_val / (1024**3):.1f} GB"
        elif bytes_val >= 1024**2:
            return f"{bytes_val / (1024**2):.1f} MB"
        elif bytes_val >= 1024:
            return f"{bytes_val / 1024:.1f} KB"
        else:
            return f"{bytes_val} bytes"
    
    cat = load_catalog()
    for c in cat.collections:
        if stats:
            try:
                if c.type == "bundle" and os.path.exists(c.source):
                    size = os.path.getsize(c.source)
                    size_str = format_bytes(size)
                    typer.echo(f"{c.id:<20} {c.type:<8} {size_str:>10}  {c.source}")
                else:
                    typer.echo(f"{c.id:<20} {c.type:<8} {'N/A':>10}  {c.source}")
            except Exception:
                typer.echo(f"{c.id:<20} {c.type:<8} {'ERROR':>10}  {c.source}")
        else:
            typer.echo(f"{c.id:<20} {c.type:<8} {c.source}")

# Mount as `corpus mcp <subcommand>`
mcp_app.command("serve")(mcp_serve)
mcp_app.command("http")(mcp_http)
mcp_app.command("add")(mcp_add)
mcp_app.command("rm")(mcp_rm)
mcp_app.command("ls")(mcp_ls)

app.add_typer(mcp_app, name="mcp")


def server_loop(server):  # type: ignore[no-untyped-def]
    from .mcp.server import run_stdio
    return run_stdio(server)


@app.command()
def version() -> None:
    """Show version."""
    typer.echo(__version__)


@app.command()
def capture(
    url: str = typer.Option(..., "--url", help="YouTube watch URL"),
    out: str = typer.Option("artifacts/yt", "--out", help="Output base directory"),
    lang: str = typer.Option("en", "--lang", help="Subtitle language"),
    mode: str = typer.Option("interval", "--mode", help="interval|uniform|scene"),
    every: int = typer.Option(60, "--every", help="Interval seconds (interval mode)"),
    max_shots: int = typer.Option(60, "--max-shots", help="Max screenshots or count (uniform/scene)"),
    scene_thresh: float = typer.Option(0.3, "--scene-thresh", help="Scene threshold (scene mode)"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing files"),
    no_video: bool = typer.Option(False, "--no-video", help="Skip video download"),
    no_subs: bool = typer.Option(False, "--no-subs", help="Skip subtitles/transcript"),
    no_shots: bool = typer.Option(False, "--no-shots", help="Skip screenshots"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON summary to stdout"),
    no_index: bool = typer.Option(False, "--no-index", help="Disable writing index.json"),
) -> None:
    """Capture a YouTube video's metadata, transcript, and screenshots."""
    options = CaptureOptions(
        url=url,
        out_dir=out,
        lang=lang,
        mode=mode,
        every_seconds=every,
        max_screenshots=max_shots,
        scene_threshold=scene_thresh,
        overwrite=overwrite,
        skip_video=no_video,
        skip_subtitles=no_subs,
        skip_screenshots=no_shots,
        write_index=(not no_index),
    )
    try:
        summary = capture_video(options)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    if json_out:
        sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
    else:
        typer.echo(f"Captured {summary.get('id')} → {summary.get('out_dir')}")


@app.command()
def doctor(verbose: bool = typer.Option(False, "--verbose", help="Show more detail")) -> None:
    """Check environment for required tools and libraries."""
    res = diagnose_environment()
    if verbose:
        sys.stdout.write(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    else:
        for key, info in res.items():
            if isinstance(info, dict):
                status = info.get("present")
                version = info.get("version", "")
                typer.echo(f"{key}: {'OK' if status == 'true' else 'MISSING'} {version}")
            else:
                typer.echo(f"{key}: {info}")


@app.command()
def inspect(path: str = typer.Option(..., "--path", help="Artifact directory"), details: bool = typer.Option(False, "--details")) -> None:
    """Summarize an artifact directory."""
    res = inspect_artifact(path, details=details)
    sys.stdout.write(json.dumps(res, ensure_ascii=False, indent=2) + "\n")


@app.command()
def clean(
    out: str = typer.Option("artifacts/yt", "--out", help="Base output directory"),
    id: Optional[str] = typer.Option(None, "--id", help="Video ID to delete"),
    all: bool = typer.Option(False, "--all", help="Delete all artifacts"),
    yes: bool = typer.Option(False, "--yes", help="Confirm deletion without prompt"),
) -> None:
    """Delete artifacts by id or all under out dir."""
    if not id and not all:
        raise typer.BadParameter("Use --id or --all")
    targets: List[str]
    if id:
        targets = [id]
    else:
        targets = list_artifacts(out)
    if not yes:
        typer.echo(f"About to delete {len(targets)} item(s) under {out}. Use --yes to proceed.")
        raise typer.Exit(code=2)
    deleted = 0
    for vid in targets:
        if delete_artifact(out, vid):
            deleted += 1
    typer.echo(f"Deleted {deleted} artifacts")


@app.command()
def batch(
    file: Optional[str] = typer.Option(None, "--file", help="File with one URL per line"),
    stdin: bool = typer.Option(False, "--stdin", help="Read URLs from STDIN"),
    out: str = typer.Option("artifacts/yt", "--out", help="Output base directory"),
    concurrency: int = typer.Option(2, "--concurrency", help="Parallel workers"),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop on first error"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSONL to stdout"),
    # capture options
    lang: str = typer.Option("en", "--lang"),
    mode: str = typer.Option("interval", "--mode"),
    every: int = typer.Option(60, "--every"),
    max_shots: int = typer.Option(60, "--max-shots"),
    scene_thresh: float = typer.Option(0.3, "--scene-thresh"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    no_video: bool = typer.Option(False, "--no-video"),
    no_subs: bool = typer.Option(False, "--no-subs"),
    no_shots: bool = typer.Option(False, "--no-shots"),
) -> None:
    """Process multiple URLs."""
    urls: List[str] = []
    if file:
        with open(file, "r", encoding="utf-8") as f:
            urls.extend([line.strip() for line in f if line.strip()])
    if stdin:
        urls.extend([line.strip() for line in sys.stdin if line.strip()])
    if not urls:
        raise typer.BadParameter("No URLs provided (use --file or --stdin)")
    options = CaptureOptions(
        url="",
        out_dir=out,
        lang=lang,
        mode=mode,
        every_seconds=every,
        max_screenshots=max_shots,
        scene_threshold=scene_thresh,
        overwrite=overwrite,
        skip_video=no_video,
        skip_subtitles=no_subs,
        skip_screenshots=no_shots,
    )
    run_batch(urls, options, concurrency=concurrency, fail_fast=fail_fast, jsonl=json_out)


@app.command()
def pack(
    directory: str = typer.Argument("."),
    repo: Optional[str] = typer.Option(None, "--repo", help="GitHub repo URL; can include /tree/<ref> and subdir"),
    ref: Optional[str] = typer.Option(None, "--ref", help="Branch/tag/SHA; overrides URL ref"),
    out: str = typer.Option("corpus-out.txt", "--output", "-o"),
    include: List[str] = typer.Option([], "--include", "-i"),
    exclude: List[str] = typer.Option([], "--exclude", "-x"),
    compress: bool = typer.Option(False, "--compress", "-c"),
    max_compress: bool = typer.Option(False, "--max-compress", "-m"),
    gzip_out: bool = typer.Option(False, "--gzip", "-z"),
    base64_out: bool = typer.Option(False, "--base64", "-b"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    config_file: Optional[str] = typer.Option(None, "--config", help="cpack config file"),
    # index options
    write_index: bool = typer.Option(True, "--write-index", help="Prepend file index to output"),
    index_only: bool = typer.Option(False, "--index-only", help="Write only file index (no contents)"),
    index_style: str = typer.Option("flat", "--index-style", help="flat|tree|json"),
    index_output: Optional[str] = typer.Option(None, "--index-output", help="Write index to separate file"),
    index_include: List[str] = typer.Option([], "--index-include", help="Comma-sep metrics: size,lines,hash (hash N/A yet)"),
    index_depth: Optional[int] = typer.Option(None, "--index-depth", help="Limit tree depth for index"),
    # catalog options
    register_id: Optional[str] = typer.Option(None, "--register-id", help="After packing, add bundle to catalog with this id"),
    register_name: Optional[str] = typer.Option(None, "--register-name", help="Optional display name for catalog entry"),
    register_tags: Optional[str] = typer.Option(None, "--register-tags", help="Comma-separated tags for catalog entry"),
    stats: bool = typer.Option(False, "--stats", help="Show packing statistics"),
) -> None:
    """Pack files from a directory into a single corpus file."""
    input_dir = directory
    # If repo provided, fetch it and set input_dir accordingly
    if repo:
        root, url_subdir = fetch_repo_checkout(repo, ref=ref)
        input_dir = root
        if url_subdir:
            input_dir = os.path.join(root, url_subdir)

    cfg = PackConfig(
        input_dir=input_dir,
        output_file=out,
        include_globs=include,
        exclude_globs=exclude,
        verbose=verbose,
        compress=compress,
        max_compress=max_compress,
        gzip_out=gzip_out,
        base64_out=base64_out,
        write_index=write_index,
        index_only=index_only,
        index_style=index_style,
        index_output=index_output,
        index_include=index_include,
        index_depth=index_depth,
    )
    if config_file:
        from .pack import load_config_file

        file_cfg = load_config_file(config_file)
        # CLI overrides file config
        cfg = PackConfig(
            input_dir=cfg.input_dir or file_cfg.input_dir,
            output_file=cfg.output_file or file_cfg.output_file,
            include_globs=cfg.include_globs or file_cfg.include_globs,
            exclude_globs=cfg.exclude_globs or file_cfg.exclude_globs,
            verbose=cfg.verbose or file_cfg.verbose,
            compress=cfg.compress or file_cfg.compress,
            max_compress=cfg.max_compress or file_cfg.max_compress,
            gzip_out=cfg.gzip_out or file_cfg.gzip_out,
            base64_out=cfg.base64_out or file_cfg.base64_out,
        )
    out_path, stats = pack_directory(cfg)
    typer.echo(out_path)
    
    if stats and stats.get('files_processed', 0) > 0:
        def format_bytes(bytes_val):
            if bytes_val >= 1024**3:
                return f"{bytes_val / (1024**3):.1f} GB"
            elif bytes_val >= 1024**2:
                return f"{bytes_val / (1024**2):.1f} MB"
            elif bytes_val >= 1024:
                return f"{bytes_val / 1024:.1f} KB"
            else:
                return f"{bytes_val} bytes"
        
        total_size = format_bytes(stats['total_bytes'])
        bundle_size = format_bytes(stats['bundle_size'])
        typer.echo(f"📊 Stats: {stats['files_processed']} files, {total_size} → {bundle_size} ({stats['compression_ratio']:.1%} ratio)")
        if stats['files_skipped'] > 0:
            typer.echo(f"⚠️  Skipped: {stats['files_skipped']} files")
    # Optionally register in catalog as a bundle
    if register_name and not register_id:
        # derive a slug from name if id not provided
        slug = register_name.strip().lower()
        slug = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in slug)
        while "--" in slug:
            slug = slug.replace("--", "-")
        slug = slug.strip("-") or "bundle"
        register_id = slug
    if register_id:
        tag_list = [t.strip() for t in (register_tags or "").split(",") if t.strip()]
        try:
            add_collection(register_id, out_path, name=register_name, type="bundle", tags=tag_list)
            typer.echo(f"registered: {register_id}")
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"Warning: failed to register in catalog: {exc}", err=True)




if __name__ == "__main__":  # pragma: no cover
    app()

def main() -> None:  # console_scripts entrypoint
    app()


