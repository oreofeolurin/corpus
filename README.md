## Corpus (Data extraction, packaging, and MCP serving)

Corpus is a Python CLI for extracting and packaging datasets, then serving them via MCP so LLMs can browse, search, and retrieve files. It supports YouTube capture, packing local directories or remote GitHub repos, a multi-collection catalog, and an HTTP MCP server.

Commands are exposed as `corpus` (primary) and `cpack` (packer alias).

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Command Reference](#command-reference)
- [Configuration](#configuration)
- [Output Formats](#output-formats)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Features

- **YouTube capture**: Fetch `yt-dlp` metadata, subtitles/transcripts, MP4, and screenshots via ffmpeg; emits `index.json` automatically.
- **Packer (cpack)**: Package directories or remote GitHub repos into a single bundle with a prepended human index and optional JSON sidecar; supports include/exclude globs, compression, gzip/base64.
- **Catalog**: Add bundles or directories as named collections and serve them together.
- **HTTP MCP server**: Expose collections to IDE agents (Cursor, etc.) with tools: `list_collections`, `list_files`, `get_file`, `search`.
- **Batch, inspect, clean, doctor** utilities.

## Installation

### From PyPI (recommended)

```bash
pipx install corpus-cli
```

### Build from Source

Clone the repository and install in development mode:

```bash
git clone https://github.com/oreofeolurin/corpus.git
cd corpus
make install-dev
```

This installs the package in editable mode with development dependencies.

### Standalone Binaries

Build a single-file executable:

```bash
make binary
./dist/corpus --help
```

Build distribution packages:

```bash
make build
# Creates dist/corpus_cli-*.whl and dist/corpus-cli-*.tar.gz
```

### Docker

Build and run with Docker:

```bash
docker build -t oreofeolurin/corpus:latest .
docker run --rm -v "$PWD/artifacts:/data" oreofeolurin/corpus:latest capture --url https://www.youtube.com/watch?v=VIDEO_ID --out /data
```

## Quick Start

```bash
# Check environment
corpus doctor

# Capture one video
corpus capture --url https://www.youtube.com/watch?v=VIDEO_ID --out artifacts/yt --mode scene --max-shots 100

# Inspect the results
corpus inspect --path artifacts/yt/VIDEO_ID --details

# Pack a directory into a single bundle (human index on top)
corpus pack -d artifacts/yt/VIDEO_ID -o artifacts/yt/VIDEO_ID/corpus-out.txt -i "**/*.txt" -i "**/*.info.json"

# Pack a remote GitHub repo subtree and register it in the catalog
corpus pack --repo https://github.com/temporalio/sdk-python/temporalio \
  -i "**/*.py" -o dist/temporal-sdk-python.txt \
  --register-name "Temporal SDK (Python)" --register-tags python,sdk

# Serve the catalog via HTTP MCP (default 127.0.0.1:8787)
corpus mcp serve

# Or point at a single bundle/dir (one-off)
corpus mcp serve --source dist/temporal-sdk-python.txt
```

## Command Reference

### corpus capture
Capture a YouTube video's metadata, transcript, and screenshots.

Flags:
- `--url` (required): YouTube watch URL
- `--out` (default `artifacts/yt`): Output base directory
- `--lang` (default `en`): Subtitle language
- `--mode` (`interval`|`uniform`|`scene`, default `interval`)
- `--every` (default `60`): Interval seconds for `interval`
- `--max-shots` (default `60`): Cap or count for `uniform`/`scene`
- `--scene-thresh` (default `0.3`): Scene detection threshold
- `--overwrite`: Overwrite existing files
- `--no-video`, `--no-subs`, `--no-shots`: Skip stages
- `--json`: Emit JSON summary to stdout

Output structure:

```
<out>/<video_id>/
  ├─ <video_id>.info.json
  ├─ <video_id>.<lang>.vtt (if available)
  ├─ <video_id>.txt (timestamped transcript)
  ├─ <video_id>.mp4
  └─ shots/
       ├─ shot_0001.jpg
       └─ ...
```

### corpus batch
Process multiple URLs with optional JSONL streaming.

Flags:
- `--file PATH` or `--stdin`
- `--out`, `--concurrency`, `--fail-fast`, plus capture flags
- `--json`: stream JSONL to stdout

### corpus pack (alias: cpack)
Pack files from directories or a GitHub repo into a single bundle, optionally registering in the catalog.

Flags:
- `-d/--dir`, `-o/--output`
- `--repo URL` (optional): GitHub URL; supports `/tree/<ref>` and subdirs
- `-i/--include GLOB` (repeatable), `-x/--exclude GLOB` (repeatable)
- `-c/--compress`, `-m/--max-compress`
- `-z/--gzip`, `-b/--base64` (requires `--gzip`)
- `-v/--verbose`
- `--config PATH`: load cpack YAML/JSON config; CLI overrides file
- `--write-index` (default true): prepend a human-readable index to the bundle
- `--index-output PATH` (JSON, Corpus v1 schema)
- `--register-id ID` (optional): register bundle in the catalog after pack
- `--register-name NAME`, `--register-tags t1,t2` (optional); if only name is provided, a slug ID is auto-generated

### corpus mcp (catalog and server)

- `corpus mcp add --id <id> --source <path> [--type auto|bundle|dir] [--name …] [--tags …]`
- `corpus mcp rm --id <id>`
- `corpus mcp ls`
- `corpus mcp serve [--source <path>] [--host 127.0.0.1] [--port 8787]`

MCP tools (HTTP):
- `list_collections` → lines of `<id>\t<type>\t<source>`
- `list_files {collection}` → file paths in the collection
- `get_file {collection, path, start?, end?}` → file content (optionally a line range)
- `search {collection, query, top_k?, case_sensitive?}` → `path:line: snippet`

### corpus inspect
Summarize an artifact directory (`--details` for metadata fields).

### corpus clean
Delete by `--id` under `--out` or everything with `--all` (guarded by `--yes`).

### corpus doctor
Check for `yt-dlp`, `ffmpeg`, `ffprobe`, and Python dependencies.

## Configuration

### Packer config (cpack)

You may use `cpack.yml`, `cpack.yaml`, or `cpack.json` in the input directory, or specify `--config`.

YAML example:

```yaml
inputDir: ./src
outputFile: output.txt
includeGlobs:
  - "**/*.py"
  - "**/*.md"
excludeGlobs:
  - "**/.git/**"
  - "**/node_modules/**"
verbose: true
compress: false
maxCompress: false
gzip: false
base64: false
```

JSON example:

```json
{
  "inputDir": "./src",
  "outputFile": "output.txt",
  "includeGlobs": ["**/*.py", "**/*.md"],
  "excludeGlobs": ["**/.git/**", "**/node_modules/**"],
  "verbose": true,
  "compress": false,
  "maxCompress": false,
  "gzip": false,
  "base64": false
}
```

## Output formats

Packer supports multiple formats:

1. Standard text (default)
2. Compressed whitespace (`--compress`)
3. Max-compressed with comment removal (`--max-compress`)
4. Gzipped bytes (`--gzip`)
5. Base64 of gzip (`--gzip --base64`)

## Examples

1) Interval capture; 1/min up to 20 shots:

```bash
corpus capture --url https://www.youtube.com/watch?v=VIDEO_ID \
  --out artifacts/yt --mode interval --every 60 --max-shots 20
```

2) Scene-based capture (approx 100 shots):

```bash
corpus capture --url https://www.youtube.com/watch?v=VIDEO_ID \
  --out artifacts/yt --mode scene --scene-thresh 0.3 --max-shots 100
```

3) Batch from file with JSONL output:

```bash
corpus batch --file urls.txt --out artifacts/yt --concurrency 4 --json
```

4) Packer include/exclude with compression and registration:

```bash
corpus pack -d artifacts/yt/VIDEO_ID -o artifacts/yt/VIDEO_ID/corpus-out.txt \
  -i "**/*.txt" -i "**/*.info.json" -x "**/shots/**" -c -v \
  --register-name "My Video Artifacts" --register-tags video,youtube
```

## Troubleshooting

- `ffmpeg not found`: install via Homebrew (`brew install ffmpeg`) or your OS package manager.
- `yt-dlp` issues / rate limits: provide cookies (`--cookies` via capture in future), use proxies (`--proxy` in future), or rerun later.
- Permissions: ensure the output directory is writable.
- Docker: use the provided Dockerfile to avoid local dependency issues.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for development, testing, and release guidelines.

## License

Licensed under the [MIT License](LICENSE).

