from functools import cmp_to_key

import pytest

from patch_agent.debversion import compare_versions, is_fixed, parse_version


@pytest.mark.parametrize("left,right,expected", [
    ("1.0", "1.0", 0),
    ("1.10", "1.9", 1),                          # numeric, not string, order
    ("1.02", "1.2", 0),                          # leading zeros ignored
    ("1:0.9", "2.0", 1),                         # epoch dominates
    ("0:1.0", "1.0", 0),                         # missing epoch is 0
    ("1.0~rc1", "1.0", -1),                      # tilde sorts before the end
    ("1.0", "1.0+deb12u1", -1),
    ("1.0a", "1.0", 1),
    ("1.0", "1.0.1", -1),
    ("1.0-0", "1.0", 0),                         # missing revision equals 0
    ("7.88.1-10", "7.88.1-10+deb12u1", -1),
    ("7.88.1-10+deb12u1", "7.88.1-10+deb12u2", -1),
    ("1.0-1+deb12u2", "1.0-1+deb12u10", -1),
    ("1.0-1~bpo12+1", "1.0-1", -1),
    ("3.0.9-1", "3.0.11-1~deb12u2", -1),
    ("1:1.0-1", "1:1.0-2", -1),
])
def test_compare_versions(left, right, expected):
    assert compare_versions(left, right) == expected
    assert compare_versions(right, left) == -expected


def test_tilde_ordering_matches_debian_policy():
    ordered = ["1.0~~", "1.0~~a", "1.0~", "1.0~rc1", "1.0", "1.0a"]
    assert sorted(reversed(ordered), key=cmp_to_key(compare_versions)) == ordered


def test_is_fixed():
    fixed = "3.0.11-1~deb12u2"
    assert is_fixed(fixed, fixed)
    assert is_fixed("3.0.15-1~deb12u1", fixed)
    assert is_fixed("1:1.0-1", fixed)            # a later epoch counts as newer
    assert not is_fixed("3.0.9-1", fixed)
    assert not is_fixed("3.0.11-1~deb12u1", fixed)


def test_parse_version_fields():
    version = parse_version("2:1.4.5-3+deb12u1")
    assert (version.epoch, version.upstream, version.revision) == (2, "1.4.5", "3+deb12u1")
    assert parse_version("1.0") == (0, "1.0", "")
    assert parse_version("1.0-2-3") == (0, "1.0-2", "3")   # last hyphen splits the revision


@pytest.mark.parametrize("bad", [
    "", " 1.0", "1.0 ", "1 .0", "abc", "-1", "x:1.0", ":1.0", "1.0-", "1.0:2", "1.0-a_b", None, 1.0,
])
def test_invalid_versions_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_version(bad)
    with pytest.raises(ValueError):
        compare_versions("1.0", bad)
