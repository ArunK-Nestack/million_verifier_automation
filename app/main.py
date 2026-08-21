from __future__ import annotations

import argparse
from pathlib import Path

from app.config import settings
from app.services.batch_processor import BatchProcessor
from app.services.input_processor import prepare_csv


def check_config() -> None:
    settings.require_api_key()

    print("MillionVerifier Agent foundation is configured.")
    print(f"Bulk API base:        {settings.bulk_base_url}")
    print(f"Polling interval:     {settings.poll_interval_seconds} seconds (MillionVerifier status check)")
    print(f"Watch interval:       {settings.watch_interval_seconds} seconds (Input folder check when idle)")
    print(f"Auto-delete input:    {settings.delete_input_file}")
    print(f"Default Input Folder: {settings.default_input_dir}")
    print(f"Default Output Folder:{settings.default_output_dir}")


def prepare_file(file_path: str) -> None:
    result = prepare_csv(file_path)

    print()
    print("Input preparation completed.")
    print(f"Detected email column: {result.email_column}")
    print()
    print(f"Input rows:       {result.total_rows}")
    print(f"Blank emails:     {result.blank_emails}")
    print(f"Malformed emails: {result.malformed_emails}")
    print(f"Duplicates:       {result.duplicate_emails}")
    print(f"Unique emails:    {result.unique_emails}")
    print()
    print(f"Output: {result.output_file}")


def run_automation(
    input_dir: str | None = None,
    output_dir: str | None = None,
    continuous: bool = True,
    delete_input: bool = True,
) -> None:
    settings.require_api_key()

    in_path = Path(input_dir) if input_dir else settings.default_input_dir
    out_path = Path(output_dir) if output_dir else settings.default_output_dir

    processor = BatchProcessor(delete_input_file=delete_input)

    if continuous:
        processor.watch_and_process(input_dir=in_path, output_dir=out_path)
    else:
        processor.run_batch_once(input_dir=in_path, output_dir=out_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MillionVerifier Automation Agent — Continuous Folder-to-Folder Verification"
    )

    subparsers = parser.add_subparsers(dest="command")

    # Command: config
    subparsers.add_parser(
        "config",
        help="Check MillionVerifier configuration and default folders",
    )

    # Command: prepare
    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Prepare and clean a single CSV for verification",
    )
    prepare_parser.add_argument(
        "file",
        help="Path to the input CSV file",
    )

    # Command: watch / process
    watch_parser = subparsers.add_parser(
        "watch",
        help="Run continuous watcher on Input Folder (deletes input file after verification, categorizes to Output Folder)",
    )
    watch_parser.add_argument(
        "--input-dir",
        "-i",
        default=None,
        help=f"Path to input folder (default: {settings.default_input_dir})",
    )
    watch_parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help=f"Path to destination folder (default: {settings.default_output_dir})",
    )
    watch_parser.add_argument(
        "--keep-input",
        action="store_true",
        help="Do not delete the input file after processing",
    )

    # Command: process (alias, supports --once flag)
    process_parser = subparsers.add_parser(
        "process",
        help="Run verification (continuous by default, or --once)",
    )
    process_parser.add_argument(
        "--input-dir",
        "-i",
        default=None,
        help=f"Path to input folder (default: {settings.default_input_dir})",
    )
    process_parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help=f"Path to destination folder (default: {settings.default_output_dir})",
    )
    process_parser.add_argument(
        "--once",
        action="store_true",
        help="Process current files once and exit instead of continuously watching",
    )
    process_parser.add_argument(
        "--keep-input",
        action="store_true",
        help="Do not delete the input file after processing",
    )

    args = parser.parse_args()

    if args.command == "prepare":
        prepare_file(args.file)
        return

    if args.command == "config":
        check_config()
        return

    if args.command == "watch":
        run_automation(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            continuous=True,
            delete_input=not args.keep_input,
        )
        return

    if args.command == "process":
        run_automation(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            continuous=not args.once,
            delete_input=not args.keep_input,
        )
        return

    # Default behavior when run directly without subcommand: continuous watcher
    run_automation(continuous=True, delete_input=True)


if __name__ == "__main__":
    main()