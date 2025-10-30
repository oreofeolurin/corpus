# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-01-30

### Added
- **YouTube Capture**: Download metadata, transcripts, and screenshots from YouTube videos
- **Directory Packing**: Package local directories into single bundles with compression options
- **GitHub Repository Packing**: Fetch and package remote GitHub repositories
- **MCP Server**: HTTP server for IDE integration with intelligent search capabilities
- **Multi-Collection Catalog**: YAML-based registry for managing multiple datasets
- **CLI Interface**: Complete command-line interface with `corpus` and `cpack` commands
- **File Indexing**: Generate structured metadata and human-readable indexes
- **Batch Processing**: Process multiple YouTube URLs concurrently
- **Environment Diagnostics**: `corpus doctor` command for dependency checking
- **Docker Support**: Containerized deployment with ffmpeg pre-installed
- **PyPI Distribution**: Available as `pip install corpus-cli`

### Features
- Universal search algorithm with intelligent scoring
- Support for multiple output formats (text, gzip, base64)
- Configurable include/exclude patterns
- Automatic file type detection and prioritization
- Cross-platform compatibility (macOS, Linux, Windows)
- Comprehensive error handling and logging

### Technical Details
- Python 3.9+ support
- Built with Typer for CLI, FastAPI for MCP server
- Uses yt-dlp for YouTube processing, ffmpeg for video processing
- Implements MCP (Multi-Codebase Protocol) for AI agent integration
