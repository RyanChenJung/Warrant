"""Fetch the pinned LiveSQLBench-Base-Lite release into the data directory and check its checksums.

    uv run python -m warrant.data.fetch            # fetch and check against the recorded checksums
    uv run python -m warrant.data.fetch --record   # fetch and (re)write the checksum file

The checksum file sits next to the configuration, with the suffix `.sha256`, and is committed.
"""

import argparse
from pathlib import Path

from warrant.data.release import Release, fetch, read_checksums, write_checksums

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "livesqlbench-base-lite.yaml"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--record", action="store_true", help="write the checksum file instead of checking it")
    args = parser.parse_args(argv)

    release = Release.from_yaml(args.config)
    checksum_file = args.config.with_suffix(".sha256")
    dest = release.local_dir()
    if args.record:
        write_checksums(checksum_file, fetch(release, dest))
        print(f"Fetched {len(release.files())} files into {dest}; checksums written to {checksum_file}")
    else:
        fetch(release, dest, expected=read_checksums(checksum_file))
        print(f"{len(release.files())} files in {dest} match {checksum_file}")


if __name__ == "__main__":
    main()
