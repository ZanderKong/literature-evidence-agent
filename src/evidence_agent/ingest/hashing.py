"""SHA-256 file hashing utilities."""

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Calculate SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Calculate SHA-256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()


def verify_copy_hash(original: Path, copy: Path) -> bool:
    """Verify that two files have the same SHA-256."""
    return sha256_file(original) == sha256_file(copy)
