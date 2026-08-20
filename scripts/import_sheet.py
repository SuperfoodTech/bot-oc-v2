#!/usr/bin/env python3
"""Manual CLI wrapper for the application sheet importer."""

from core.import_sheet import run_import_sheet


def main():
    summary = run_import_sheet()
    print(summary)


if __name__ == "__main__":
    main()
