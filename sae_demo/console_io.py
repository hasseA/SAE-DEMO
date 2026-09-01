"""Generic UTF-8 console/stdio configuration helper.

On Windows, Python's `sys.stdout`/`sys.stderr` text streams default to
the process's legacy ANSI code page (commonly cp1252), not UTF-8. That
default cannot represent many valid Unicode characters a model
response may contain -- for example U+2011 NON-BREAKING HYPHEN -- so a
plain `print()` of such text raises `UnicodeEncodeError`. The same
mismatch is also a common cause of "mojibake" (visibly corrupted
punctuation): bytes produced under one encoding assumption end up
displayed or captured under a different one.

This module does exactly one small, generic thing: reconfigure a
stream's *text encoding* to UTF-8, in place, using the standard
library's own `TextIOWrapper.reconfigure()` (Python 3.7+). It performs
no text inspection, filtering, normalization, or replacement of
model-returned content -- it changes how already-decoded `str` text is
*encoded on the way out*, nothing else. Any valid Python `str` can be
encoded as UTF-8 without loss, so under normal conditions this fix is
lossless for arbitrary Unicode output.

This module has no knowledge of, and no dependency on, any specific
scenario, provider, or memory content -- it is a general-purpose
console I/O helper usable by any script in this project.
"""

from __future__ import annotations

import sys
from typing import Optional, TextIO

# Used only as a defensive fallback for the (normally unreachable,
# since UTF-8 can represent every valid Unicode code point) case of a
# str containing something that cannot be UTF-8 encoded, such as a
# lone surrogate. This intentionally does not silently drop or
# ASCII-normalize content: unencodable data becomes a visible
# backslash escape sequence rather than being removed, replaced with
# "?", or causing a crash.
FALLBACK_ERROR_HANDLER = "backslashreplace"

UTF8_ENCODING = "utf-8"


def configure_utf8_stdio(
    *,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> None:
    """Reconfigure the given (or, by default, the real) stdout/stderr to UTF-8.

    Each stream is only touched if it exposes a `reconfigure` method
    (as a standard `io.TextIOWrapper` does) -- a stream that does not
    (for example, one already replaced with something else entirely)
    is left alone rather than raised on, since this helper's job is to
    make Unicode output *more* robust, never to make startup less
    robust.

    Passing explicit `stdout`/`stderr` (e.g. an `io.TextIOWrapper`
    wrapping an in-memory buffer) is how this function is exercised
    directly in tests, without touching the real process streams.
    """

    target_stdout = stdout if stdout is not None else sys.stdout
    target_stderr = stderr if stderr is not None else sys.stderr

    for stream in (target_stdout, target_stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        reconfigure(encoding=UTF8_ENCODING, errors=FALLBACK_ERROR_HANDLER)
