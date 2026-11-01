"""Cross-check against the real dpkg; skipped where dpkg is unavailable."""

import itertools
import shutil
import subprocess

import pytest

from patch_agent.debversion import compare_versions

pytestmark = pytest.mark.skipif(shutil.which("dpkg") is None, reason="dpkg is not installed")

VERSIONS = [
    "1.0", "1.0~rc1", "1.0~~", "1.0+deb12u1", "1.10", "1.9", "1.02", "1:0.9", "2.0-1",
    "2.0-1+deb12u1", "1.0-1~bpo12+1", "1.0-1+deb12u2", "1.0-1+deb12u10", "3.0.11-1~deb12u2",
    "3.0.9-1", "0.9.8zh-1", "7.88.1-10", "7.88.1-10+deb12u1", "1:1.0-1", "1:1.0-2",
]


def dpkg_compare(left, right):
    if subprocess.run(["dpkg", "--compare-versions", left, "lt", right]).returncode == 0:
        return -1
    if subprocess.run(["dpkg", "--compare-versions", left, "eq", right]).returncode == 0:
        return 0
    return 1


@pytest.mark.parametrize("left,right", list(itertools.product(VERSIONS, repeat=2)))
def test_matches_dpkg(left, right):
    assert compare_versions(left, right) == dpkg_compare(left, right)
