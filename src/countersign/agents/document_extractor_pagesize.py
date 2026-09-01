"""The page size the json-content response does not report.

A box only becomes evidence once it is a fraction of its page, and /build returns
boxes in PDF points and no page size whatsoever. So the size is read from the file
itself, and only when the file states it unambiguously: one MediaBox shared by every
page, no CropBox that disagrees with it, no rotation. Anything else returns nothing
and the spans keep no box, which is the honest outcome rather than a box divided by a
number that was guessed.
"""

import re
import zlib
from typing import Final

MAX_STREAMS_INSPECTED: Final[int] = 64
MAX_STREAM_BYTES: Final[int] = 4_000_000
_NUMBER = rb"([-+]?[0-9]*\.?[0-9]+)"
_MEDIA_BOX = re.compile(rb"/MediaBox\s*\[\s*" + rb"\s+".join([_NUMBER] * 4) + rb"\s*\]")
_CROP_BOX = re.compile(rb"/CropBox\s*\[\s*" + rb"\s+".join([_NUMBER] * 4) + rb"\s*\]")
_ROTATE = re.compile(rb"/Rotate\s+([-+]?\d+)")
_STREAM = re.compile(rb"stream\r?\n(.*?)endstream", re.DOTALL)


def page_size_from_pdf(content: bytes) -> tuple[float, float] | None:
    """The one page size that applies to the whole document, or nothing.

    Modern writers hide the page tree inside compressed object streams, so those are
    inflated before the search; a file whose pages disagree in size or that carries a
    rotation is refused, because mapping a size to the right page needs a real PDF
    parser and a wrong denominator is worse than an absent box.
    """
    searchable = [content, *_inflated_streams(content)]
    sizes = {size for blob in searchable for size in _sizes(blob, _MEDIA_BOX)}
    if len(sizes) != 1:
        return None
    size = sizes.pop()
    crops = {crop for blob in searchable for crop in _sizes(blob, _CROP_BOX)}
    if crops and crops != {size}:
        return None
    if any(_is_rotated(blob) for blob in searchable):
        return None
    return size


def _sizes(content: bytes, pattern: re.Pattern[bytes]) -> set[tuple[float, float]]:
    found: set[tuple[float, float]] = set()
    for match in pattern.finditer(content):
        try:
            left, bottom, right, top = (float(value) for value in match.groups())
        except ValueError:
            continue
        width, height = abs(right - left), abs(top - bottom)
        if width > 0 and height > 0:
            found.add((round(width, 4), round(height, 4)))
    return found


def _is_rotated(content: bytes) -> bool:
    return any(int(match.group(1)) % 360 != 0 for match in _ROTATE.finditer(content))


def _inflated_streams(content: bytes) -> list[bytes]:
    """Inflate what inflates and ignore what does not: image and font streams are not
    zlib data, and a failure here only means one fewer place to look."""
    inflated: list[bytes] = []
    for match in _STREAM.finditer(content):
        if len(inflated) >= MAX_STREAMS_INSPECTED:
            break
        blob = match.group(1)
        if len(blob) > MAX_STREAM_BYTES:
            continue
        try:
            inflated.append(zlib.decompress(blob))
        except zlib.error:
            continue
    return inflated
