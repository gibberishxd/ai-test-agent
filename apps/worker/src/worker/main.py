"""Worker entry point.

Phase 0: a placeholder that proves the Python side runs.
Phase 1 replaces this with the deterministic checker (console errors, failed requests,
HTTP 4xx/5xx, axe-core violations, screenshots).
"""

import os


def target_url() -> str:
    """The site the worker will test. Defaults to the local demo app."""
    return os.environ.get("DEMO_URL", "http://localhost:5173")


def main() -> None:
    print(f"[worker] ready. Target: {target_url()} (Phase 1 adds the checker)")


if __name__ == "__main__":
    main()
