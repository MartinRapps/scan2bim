"""Unified CLI entry-point helper.

Standardises the ``if __name__ == '__main__': try/except`` idiom used across
the pipeline scripts so that caught exceptions exit with a formatted
``SystemExit`` message (and non-zero status) instead of a bare traceback or a
silent ``print("Error")+return``.
"""

from __future__ import annotations

from typing import Callable, Tuple, Type


def run_main(main_fn: Callable[[], object], catch: Tuple[Type[BaseException], ...] = (OSError, ValueError)) -> None:
    """Run ``main_fn`` and exit with ``"Error: <message>"`` on a caught exception."""
    try:
        main_fn()
    except catch as error:
        raise SystemExit(f"Error: {error}")
