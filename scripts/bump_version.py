#!/usr/bin/env python3
"""
Version bumping script for corpus-packer.

Usage:
    python scripts/bump_version.py patch    # 0.1.0 -> 0.1.1
    python scripts/bump_version.py minor    # 0.1.0 -> 0.2.0
    python scripts/bump_version.py major    # 0.1.0 -> 1.0.0
    python scripts/bump_version.py 0.2.5    # Set specific version
"""

import re
import sys
from pathlib import Path

def get_current_version():
    """Get current version from pyproject.toml"""
    pyproject_path = Path("pyproject.toml")
    content = pyproject_path.read_text()
    match = re.search(r'version = "([^"]+)"', content)
    if match:
        return match.group(1)
    raise ValueError("Could not find version in pyproject.toml")

def bump_version(current_version, bump_type):
    """Bump version based on type"""
    parts = [int(x) for x in current_version.split('.')]
    
    if bump_type == "major":
        parts[0] += 1
        parts[1] = 0
        parts[2] = 0
    elif bump_type == "minor":
        parts[1] += 1
        parts[2] = 0
    elif bump_type == "patch":
        parts[2] += 1
    else:
        # Assume it's a specific version
        return bump_type
    
    return ".".join(map(str, parts))

def update_version(new_version):
    """Update version in pyproject.toml"""
    pyproject_path = Path("pyproject.toml")
    content = pyproject_path.read_text()
    
    # Update version
    content = re.sub(
        r'version = "[^"]+"',
        f'version = "{new_version}"',
        content
    )
    
    pyproject_path.write_text(content)
    print(f"Updated version to {new_version} in pyproject.toml")

def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    
    bump_type = sys.argv[1]
    
    try:
        current_version = get_current_version()
        print(f"Current version: {current_version}")
        
        new_version = bump_version(current_version, bump_type)
        print(f"New version: {new_version}")
        
        update_version(new_version)
        
        print(f"\nNext steps:")
        print(f"1. git add pyproject.toml")
        print(f"2. git commit -m 'Bump version to {new_version}'")
        print(f"3. git tag -a v{new_version} -m 'Release version {new_version}'")
        print(f"4. git push origin main --tags")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
