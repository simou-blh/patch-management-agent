import asyncio

import pytest

from scripts.demo import run_demo


def test_visible_demo_exercises_real_mcp_and_operator_cli(tmp_path):
    folder = tmp_path / "demo"
    transcript = asyncio.run(run_demo(folder))
    assert len(transcript["reports"]) == 4
    assert (folder / "approvals.sqlite").is_file()
    assert (folder / "transcript.json").is_file()
    assert len(list(folder.glob("report-*.json"))) == 4
    assert all(report["jobs"] == [] for report in transcript["reports"])
    with pytest.raises(FileExistsError):
        asyncio.run(run_demo(folder))
