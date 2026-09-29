"""Small interactive menu and optional direct command interface."""

import argparse
import sys

from .compress import CompressionError, PRESETS, compress_pdf


COMMANDS = ("compress", "split", "merge", "trim")


def choose(prompt: str, choices: tuple[str, ...]) -> str:
    while True:
        answer = input(prompt).strip().lower()
        if answer in choices:
            return answer
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]
        print("Choose " + ", ".join(choices) + " (or its number).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A lean terminal PDF utility. Only compress is implemented.")
    parser.add_argument("command", nargs="?", choices=COMMANDS)
    parser.add_argument("file", nargs="?", help="PDF to compress")
    parser.add_argument("--level", choices=tuple(PRESETS), help="compression strength")
    args = parser.parse_args(argv)
    try:
        command = args.command
        if command is None:
            print("csmt-pdf\n  1. compress\n  2. split (coming soon)\n  3. merge (coming soon)\n  4. trim (coming soon)")
            command = choose("Choose a command: ", COMMANDS)
        if command != "compress":
            print(f"{command} is not implemented yet. Try compress.", file=sys.stderr)
            return 2
        filename = args.file
        if filename is None:
            filename = input("PDF file: ").strip()
            # Accept a pasted quoted path; subprocess itself never uses a shell.
            if len(filename) >= 2 and filename[0] == filename[-1] and filename[0] in "\"'":
                filename = filename[1:-1]
        if not filename:
            raise CompressionError("Enter a PDF filename.")
        level = args.level or choose("How much? (1. a little, 2. somewhat, 3. a lot): ", tuple(PRESETS))
        print("Compressing...")
        result = compress_pdf(filename, level)
        if result.output is None:
            print("This setting did not make the PDF smaller. No output saved; original unchanged.")
        else:
            saved = 100 * (1 - result.compressed_bytes / result.original_bytes)
            print(f"Compressed! Saved as: {result.output}")
            print(f"{result.original_bytes:,} → {result.compressed_bytes:,} bytes ({saved:.1f}% smaller)")
        return 0
    except (CompressionError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
