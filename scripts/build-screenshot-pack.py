#!/usr/bin/env python3
"""Rebuild Mosaic's contact sheet and deterministic screenshot ZIP."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile


BACKGROUND = "#24221f"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_sources(screenshot_dir: Path) -> list[Path]:
    sources: list[Path] = []
    for number in range(1, 15):
        matches = sorted(screenshot_dir.glob(f"{number:02d}-*.png"))
        if len(matches) != 1:
            names = ", ".join(path.name for path in matches) or "none"
            raise RuntimeError(
                f"expected exactly one {number:02d}-*.png in {screenshot_dir}; found {names}"
            )
        sources.append(matches[0])
    return sources


def run_magick(arguments: list[str], *, environment: dict[str, str]) -> None:
    subprocess.run(
        ["magick", *arguments],
        check=True,
        env=environment,
        stdout=subprocess.DEVNULL,
    )


def build_contact_sheet(sources: list[Path], output: Path) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "LC_ALL": "C",
            "MAGICK_THREAD_LIMIT": "1",
            "SOURCE_DATE_EPOCH": "315532800",
            "TZ": "UTC",
        }
    )

    desktop = output.parent / "desktop.png"
    mobile = output.parent / "mobile.png"
    run_magick(
        [
            "montage",
            *(str(path) for path in sources[:9]),
            "-thumbnail",
            "360x225",
            "-tile",
            "3x3",
            "-geometry",
            "+12+28",
            "-background",
            BACKGROUND,
            "-depth",
            "8",
            str(desktop),
        ],
        environment=environment,
    )
    run_magick(
        [
            "montage",
            *(str(path) for path in sources[9:]),
            "-thumbnail",
            "x240",
            "-tile",
            "3x2",
            "-geometry",
            "+12+28",
            "-background",
            BACKGROUND,
            "-depth",
            "8",
            str(mobile),
        ],
        environment=environment,
    )
    run_magick(
        [
            str(desktop),
            str(mobile),
            "-background",
            BACKGROUND,
            "-gravity",
            "west",
            "-append",
            "-depth",
            "8",
            "-strip",
            "-define",
            "png:compression-level=9",
            "-define",
            "png:compression-strategy=1",
            "-define",
            "png:exclude-chunks=date,time",
            str(output),
        ],
        environment=environment,
    )


def build_zip(files: list[Path], output: Path) -> None:
    with zipfile.ZipFile(output, "w") as archive:
        for path in files:
            info = zipfile.ZipInfo(path.name, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.extra = b""
            info.comment = b""
            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def parse_args() -> argparse.Namespace:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=repository / "artifacts",
        help="artifact root containing mosaic-screenshots/ (default: %(default)s)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify generated files are current without replacing them",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact_dir = args.artifacts_dir.resolve()
    screenshot_dir = artifact_dir / "mosaic-screenshots"
    if shutil.which("magick") is None:
        raise RuntimeError("ImageMagick 7's 'magick' executable is required")
    if not screenshot_dir.is_dir():
        raise RuntimeError(f"screenshot directory does not exist: {screenshot_dir}")

    sources = find_sources(screenshot_dir)
    source_hashes = {path: sha256(path) for path in sources}
    contact_sheet = screenshot_dir / "00-contact-sheet.png"
    zip_path = artifact_dir / "Mosaic-Screenshot-Pack.zip"

    with tempfile.TemporaryDirectory(prefix=".screenshot-pack-", dir=screenshot_dir) as temp:
        temp_dir = Path(temp)
        generated_contact = temp_dir / contact_sheet.name
        generated_zip = temp_dir / zip_path.name
        build_contact_sheet(sources, generated_contact)
        build_zip([generated_contact, *sources], generated_zip)

        if args.check:
            stale = [
                destination
                for generated, destination in (
                    (generated_contact, contact_sheet),
                    (generated_zip, zip_path),
                )
                if not destination.is_file() or sha256(generated) != sha256(destination)
            ]
            if stale:
                print(
                    "stale generated artifact(s): "
                    + ", ".join(str(path) for path in stale),
                    file=sys.stderr,
                )
                return 1
        else:
            os.replace(generated_contact, contact_sheet)
            os.replace(generated_zip, zip_path)

    changed_sources = [
        path for path, original_hash in source_hashes.items() if sha256(path) != original_hash
    ]
    if changed_sources:
        raise RuntimeError(
            "source screenshots changed unexpectedly: "
            + ", ".join(str(path) for path in changed_sources)
        )

    verb = "verified" if args.check else "rebuilt"
    print(f"{verb} {contact_sheet}  sha256={sha256(contact_sheet)}")
    print(f"{verb} {zip_path}  sha256={sha256(zip_path)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
