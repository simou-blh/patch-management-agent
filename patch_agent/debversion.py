"""Debian version ordering (the dpkg algorithm), used for advisory matching.

Never compare package versions as strings or with PEP 440. Malformed versions
raise ValueError so an assessment can mark them uncertain instead of guessing.
"""

import re
from typing import NamedTuple

# [epoch:]upstream[-revision]. A colon is only valid in upstream after an epoch.
_SHAPE = re.compile(r"(?:([0-9]+):)?([0-9][A-Za-z0-9.+~:-]*)", re.ASCII)
_REVISION = re.compile(r"[A-Za-z0-9+.~]+", re.ASCII)


class DebianVersion(NamedTuple):
    epoch: int
    upstream: str
    revision: str


def parse_version(version: str) -> DebianVersion:
    """Split a Debian version, raising ValueError if it is not valid."""
    match = _SHAPE.fullmatch(version) if isinstance(version, str) else None
    if match is None:
        raise ValueError(f"invalid Debian version: {version!r}")
    epoch, rest = match.groups()
    if epoch is None and ":" in rest:
        raise ValueError(f"invalid Debian version (colon without epoch): {version!r}")
    upstream, hyphen, revision = rest.rpartition("-")
    if not hyphen:
        upstream, revision = rest, ""
    elif not upstream or not _REVISION.fullmatch(revision):
        raise ValueError(f"invalid Debian revision: {version!r}")
    return DebianVersion(int(epoch or 0), upstream, revision)


def _is_digit(char: str) -> bool:
    return "0" <= char <= "9"


def _order(char: str) -> int:
    """Sort weight of one non-digit character; '' is the end of the string."""
    if char == "":
        return 0
    if char == "~":
        return -1
    if char.isalpha():
        return ord(char)
    return ord(char) + 256


def _compare_part(left: str, right: str) -> int:
    """dpkg's verrevcmp: alternate non-digit and numeric runs."""
    i = j = 0
    while i < len(left) or j < len(right):
        while (i < len(left) and not _is_digit(left[i])) or (
            j < len(right) and not _is_digit(right[j])
        ):
            a = _order(left[i]) if i < len(left) else 0
            b = _order(right[j]) if j < len(right) else 0
            if a != b:
                return -1 if a < b else 1
            i += 1
            j += 1
        while i < len(left) and left[i] == "0":
            i += 1
        while j < len(right) and right[j] == "0":
            j += 1
        first_difference = 0
        while i < len(left) and _is_digit(left[i]) and j < len(right) and _is_digit(right[j]):
            if not first_difference:
                first_difference = ord(left[i]) - ord(right[j])
            i += 1
            j += 1
        if i < len(left) and _is_digit(left[i]):
            return 1
        if j < len(right) and _is_digit(right[j]):
            return -1
        if first_difference:
            return -1 if first_difference < 0 else 1
    return 0


def compare_versions(left: str, right: str) -> int:
    """Return -1, 0 or 1 like `dpkg --compare-versions` (left <, ==, > right)."""
    a, b = parse_version(left), parse_version(right)
    if a.epoch != b.epoch:
        return -1 if a.epoch < b.epoch else 1
    return _compare_part(a.upstream, b.upstream) or _compare_part(a.revision, b.revision)


def is_fixed(installed: str, fixed: str) -> bool:
    """True when the installed binary version is at or after the advisory's fixed version."""
    return compare_versions(installed, fixed) >= 0
