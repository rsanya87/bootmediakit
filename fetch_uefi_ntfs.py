#!/usr/bin/env python3
"""Fetch and verify the pinned upstream UEFI:NTFS partition image.

The 1 MiB image is distributed by the Rufus project. It contains the UEFI:NTFS
bootloader and filesystem driver files. We download it at install time rather
than silently shipping a mutable or unverified binary in the application.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

UPSTREAM_COMMIT = "acf7de640848ab249bedeb6feb59b33001f656b6"
UPSTREAM_URL = (
    "https://raw.githubusercontent.com/pbatard/rufus/"
    + UPSTREAM_COMMIT
    + "/res/uefi/uefi-ntfs.img"
)
EXPECTED_SIZE = 1_048_576
EXPECTED_GIT_BLOB_SHA1 = "ac50eed9730af847c43c145a5c17678f54128b33"


def git_blob_sha1(path: Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha1()
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: fetch_uefi_ntfs.py DESTINATION", file=sys.stderr)
        return 2
    destination = Path(sys.argv[1])
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.is_file():
        if (
            destination.stat().st_size == EXPECTED_SIZE
            and git_blob_sha1(destination) == EXPECTED_GIT_BLOB_SHA1
        ):
            print(f"UEFI:NTFS v2.8 image already verified: {destination}")
            return 0

    fd, temp_name = tempfile.mkstemp(
        prefix=".uefi-ntfs-", suffix=".download", dir=str(destination.parent)
    )
    os.close(fd)
    temporary = Path(temp_name)
    try:
        request = urllib.request.Request(
            UPSTREAM_URL,
            headers={"User-Agent": "BootMediaKit/0.1.2-alpha"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            with temporary.open("wb") as output:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())

        if temporary.stat().st_size != EXPECTED_SIZE:
            raise RuntimeError(
                f"Unexpected UEFI:NTFS image size: {temporary.stat().st_size}; "
                f"expected {EXPECTED_SIZE} bytes."
            )
        actual_hash = git_blob_sha1(temporary)
        if actual_hash != EXPECTED_GIT_BLOB_SHA1:
            raise RuntimeError(
                "UEFI:NTFS image integrity check failed. "
                "The file was not installed."
            )
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
        print(f"Verified UEFI:NTFS image installed: {destination}")
        return 0
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"UEFI:NTFS image download failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
