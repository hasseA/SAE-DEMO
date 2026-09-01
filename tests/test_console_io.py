"""Offline tests for the UTF-8 console/stdio configuration helper.

No network calls, no real process stdout/stderr mutated in most tests
(a real `io.TextIOWrapper` around an in-memory buffer stands in for
"the console"). Only `test_default_targets_are_sys_stdout_and_sys_stderr`
touches the real streams, and it restores them via monkeypatch.
"""

import io

import pytest

from sae_demo.console_io import (
    FALLBACK_ERROR_HANDLER,
    UTF8_ENCODING,
    configure_utf8_stdio,
)


# Characters/strings this fix must round-trip correctly. cp1252 is
# used below to simulate Windows's legacy default text encoding.
NON_BREAKING_HYPHEN = "‑"  # U+2011 NON-BREAKING HYPHEN -- not in cp1252
CURLY_APOSTROPHE = "’"  # RIGHT SINGLE QUOTATION MARK -- present in cp1252
EM_DASH = "—"  # EM DASH -- present in cp1252
REPRESENTATIVE_NON_ASCII = "café naïve 日本語 Ångström"  # mixed scripts/diacritics

REQUIRED_STRINGS = {
    "non_breaking_hyphen": NON_BREAKING_HYPHEN,
    "curly_apostrophe": CURLY_APOSTROPHE,
    "em_dash": EM_DASH,
    "representative_non_ascii": REPRESENTATIVE_NON_ASCII,
}


def _cp1252_wrapper() -> io.TextIOWrapper:
    """A text stream simulating Python's Windows-default legacy encoding."""

    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")


# --- reproducing the reported bug, offline ----------------------------------

def test_non_breaking_hyphen_reproduces_unicode_encode_error_under_cp1252():
    """Confirms the reported failure mode exists (and why): U+2011 cannot
    be represented in cp1252, Windows's common legacy default encoding.
    This is the bug this stage fixes -- reproduced here without needing
    Windows or a live provider call.
    """

    stream = _cp1252_wrapper()
    with pytest.raises(UnicodeEncodeError):
        stream.write(NON_BREAKING_HYPHEN)
        stream.flush()


def test_curly_apostrophe_and_em_dash_do_not_raise_under_cp1252():
    """These two ARE representable in cp1252, so they don't raise --
    but (per the mojibake report) that doesn't mean they display
    correctly if the bytes are later read back under a different
    encoding. This test only documents that these two characters are
    not the UnicodeEncodeError-reproduction case; the mojibake risk is
    addressed by moving to UTF-8 everywhere, tested below.
    """

    stream = _cp1252_wrapper()
    stream.write(CURLY_APOSTROPHE)
    stream.write(EM_DASH)
    stream.flush()  # must not raise


# --- the fix itself -----------------------------------------------------

@pytest.mark.parametrize("label,text", sorted(REQUIRED_STRINGS.items()))
def test_configured_stream_can_encode_required_characters_without_error(label, text):
    stream = _cp1252_wrapper()
    configure_utf8_stdio(stdout=stream, stderr=_cp1252_wrapper())

    # Must not raise -- this is the direct fix for the reported
    # UnicodeEncodeError.
    stream.write(text)
    stream.flush()


@pytest.mark.parametrize("label,text", sorted(REQUIRED_STRINGS.items()))
def test_configured_stream_round_trips_text_exactly(label, text):
    """The encoded bytes, read back as UTF-8, must equal the original
    text exactly -- no substitution, no normalization, no loss. This is
    the "preserve exact assistant text" / "no destructive replacement"
    requirement, verified at the encoding boundary.
    """

    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252", newline="")
    configure_utf8_stdio(stdout=stream, stderr=_cp1252_wrapper())

    stream.write(text)
    stream.flush()

    raw_bytes = buffer.getvalue()
    assert raw_bytes.decode(UTF8_ENCODING) == text


def test_configure_sets_utf8_encoding_and_documented_error_handler():
    stream = _cp1252_wrapper()
    assert stream.encoding.lower() != "utf-8"

    configure_utf8_stdio(stdout=stream, stderr=_cp1252_wrapper())

    assert stream.encoding.lower() == "utf-8"
    assert stream.errors == FALLBACK_ERROR_HANDLER


def test_full_sentence_with_mixed_required_characters_round_trips():
    """A single combined string exercising every required character
    together, as a model response realistically would.
    """

    sentence = (
        f"Well{NON_BREAKING_HYPHEN}intentioned plans{EM_DASH}"
        f"the kind that don{CURLY_APOSTROPHE}t survive contact with "
        f"reality{EM_DASH}rarely account for {REPRESENTATIVE_NON_ASCII}."
    )

    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252", newline="")
    configure_utf8_stdio(stdout=stream, stderr=_cp1252_wrapper())

    stream.write(sentence)
    stream.flush()

    assert buffer.getvalue().decode(UTF8_ENCODING) == sentence


# --- robustness of the helper itself -------------------------------------

def test_stream_without_reconfigure_is_left_alone_not_raised_on():
    class _NoReconfigure:
        pass

    # Must not raise even though neither fake stream supports
    # reconfigure() -- this helper must never make startup less robust.
    configure_utf8_stdio(stdout=_NoReconfigure(), stderr=_NoReconfigure())


def test_reconfigure_is_called_with_utf8_and_fallback_handler_on_both_streams():
    calls = []

    class _RecordingStream:
        def reconfigure(self, *, encoding, errors):
            calls.append({"encoding": encoding, "errors": errors})

    configure_utf8_stdio(stdout=_RecordingStream(), stderr=_RecordingStream())

    assert len(calls) == 2
    for call in calls:
        assert call == {"encoding": UTF8_ENCODING, "errors": FALLBACK_ERROR_HANDLER}


def test_default_targets_are_sys_stdout_and_sys_stderr(monkeypatch):
    calls = []

    class _RecordingStream:
        def reconfigure(self, *, encoding, errors):
            calls.append((encoding, errors))

    fake_stdout = _RecordingStream()
    fake_stderr = _RecordingStream()
    monkeypatch.setattr("sys.stdout", fake_stdout)
    monkeypatch.setattr("sys.stderr", fake_stderr)

    configure_utf8_stdio()

    assert len(calls) == 2
    assert all(call == (UTF8_ENCODING, FALLBACK_ERROR_HANDLER) for call in calls)


def test_only_stdout_can_be_targeted_independently_of_stderr():
    stdout_calls = []
    stderr_calls = []

    class _StdoutStream:
        def reconfigure(self, *, encoding, errors):
            stdout_calls.append((encoding, errors))

    class _StderrStream:
        def reconfigure(self, *, encoding, errors):
            stderr_calls.append((encoding, errors))

    configure_utf8_stdio(stdout=_StdoutStream(), stderr=_StderrStream())

    assert len(stdout_calls) == 1
    assert len(stderr_calls) == 1
