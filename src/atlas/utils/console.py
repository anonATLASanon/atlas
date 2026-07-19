from __future__ import annotations

import sys
from typing import Any, TextIO

import typer


def _safe_text(value: Any, stream: TextIO) -> str:
    text = str(value)
    encoding = stream.encoding or "utf-8"
    try:
        text.encode(encoding)
        return text
    except UnicodeEncodeError:
        return text.encode(encoding, errors="ignore").decode(encoding)


def safe_print(
    *values: Any,
    sep: str = " ",
    end: str = "\n",
    file: TextIO | None = None,
    flush: bool = False,
) -> None:
    stream = file or sys.stdout
    text = sep.join(str(value) for value in values)
    print(_safe_text(text, stream), end=end, file=stream, flush=flush)


def safe_echo(
    message: Any = "",
    *,
    err: bool = False,
    color: bool | None = None,
) -> None:
    stream = sys.stderr if err else sys.stdout
    typer.echo(_safe_text(message, stream), err=err, color=color)
