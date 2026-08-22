from __future__ import annotations

import argparse
from pathlib import Path


def get_dir_size_and_count(directory: Path) -> tuple[int, int]:
    """Returns (file_count, total_bytes) for all files in directory."""
    if not directory.exists() or not directory.is_dir():
        return 0, 0

    count = 0
    total_bytes = 0
    for p in directory.iterdir():
        if p.is_file():
            count += 1
            total_bytes += p.stat().st_size
    return count, total_bytes


def format_bytes(num_bytes: int) -> str:
    """Formats bytes into human readable string (KB, MB, GB)."""
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} TB"


def clean_directory(directory: Path) -> tuple[int, int]:
    """Deletes all files in the given directory, leaving the directory itself."""
    if not directory.exists() or not directory.is_dir():
        return 0, 0

    deleted_count = 0
    deleted_bytes = 0

    for file_path in directory.iterdir():
        if file_path.is_file():
            try:
                size = file_path.stat().st_size
                file_path.unlink()
                deleted_count += 1
                deleted_bytes += size
                print(f"  -> Deleted: {file_path.name} ({format_bytes(size)})")
            except Exception as exc:
                print(f"  -> Error deleting {file_path.name}: {exc}")

    return deleted_count, deleted_bytes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean MillionVerifier local cache folders (prepared/ and results/)"
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt and clean immediately",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    prepared_dir = base_dir / "prepared"
    results_dir = base_dir / "results"

    prep_count, prep_bytes = get_dir_size_and_count(prepared_dir)
    res_count, res_bytes = get_dir_size_and_count(results_dir)

    total_files = prep_count + res_count
    total_bytes = prep_bytes + res_bytes

    print("=" * 70)
    print(" MillionVerifier Cache Cleaner")
    print("=" * 70)
    print(f"prepared/ : {prep_count} file(s) ({format_bytes(prep_bytes)})")
    print(f"results/  : {res_count} file(s) ({format_bytes(res_bytes)})")
    print(f"Total     : {total_files} file(s) ({format_bytes(total_bytes)})")
    print("=" * 70)

    if total_files == 0:
        print("Cache is already empty. No files to clean.")
        return

    if not args.yes:
        try:
            confirm = input("Are you sure you want to clean all cached files? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                print("Cache cleaning cancelled.")
                return
        except EOFError:
            pass

    print("\nCleaning 'prepared/' folder...")
    del_prep_count, del_prep_bytes = clean_directory(prepared_dir)

    print("\nCleaning 'results/' folder...")
    del_res_count, del_res_bytes = clean_directory(results_dir)

    total_del_files = del_prep_count + del_res_count
    total_del_bytes = del_prep_bytes + del_res_bytes

    print("\n" + "=" * 70)
    print(f"Cleanup Complete! Removed {total_del_files} file(s), freed {format_bytes(total_del_bytes)} of disk space.")
    print("=" * 70)


if __name__ == "__main__":
    main()
