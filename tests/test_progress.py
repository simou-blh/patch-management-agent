from pathlib import Path

import pytest

from scripts.update_progress import END, ROOT, START, main, updated_readme


def sample_plan(done=0):
    return "\n".join(
        f"<!-- sprint:{sprint}:start -->\n" + "\n".join(
            f"- [{'x' if task < done else ' '}] Checkpoint {task}"
            + (" Evidence: merged PR and verification record" if task < done else "")
            for task in range(5)) + f"\n<!-- sprint:{sprint}:end -->"
        for sprint in range(1, 5))


@pytest.mark.parametrize("done", [0, 1, 3, 5])
def test_bar_percentages_and_surrounding_content(done):
    original = f"User introduction\n{START}\nstale\n{END}\nUser architecture link\n"
    result = updated_readme(original, sample_plan(done))
    bar = "█" * (done * 4) + "░" * (20 - done * 4)
    assert result.count(f"[{bar}]") == 4
    assert result.count(f"{done * 20:>3}%  {done}/5") == 4
    assert result.startswith(f"User introduction\n{START}\n")
    assert result.endswith(f"{END}\nUser architecture link\n")
    assert updated_readme(result, sample_plan(done)) == result


@pytest.mark.parametrize("plan", [
    sample_plan().replace("- [ ] Checkpoint 0\n", "", 1),
    sample_plan().replace("- [ ] Checkpoint 0", "- [x] Checkpoint 0", 1),
    sample_plan() + "\n<!-- sprint:1:start -->",
])
def test_invalid_source_is_rejected(plan):
    with pytest.raises(ValueError):
        updated_readme(f"{START}\n{END}", plan)


@pytest.mark.parametrize("readme", ["no markers", f"{END}\n{START}"])
def test_invalid_readme_markers_are_rejected(readme):
    with pytest.raises(ValueError):
        updated_readme(readme, sample_plan())


def test_check_does_not_write_and_update_is_repeatable(tmp_path):
    path = tmp_path / "README.md"
    original = f"Personal edit\n{START}\n{END}\n"
    path.write_text(original, encoding="utf-8")
    (tmp_path / "plan.md").write_text(sample_plan(1), encoding="utf-8")
    assert main(["--check"], root=tmp_path) == 1
    assert path.read_text(encoding="utf-8") == original
    assert main([], root=tmp_path) == 0
    assert main(["--check"], root=tmp_path) == 0


def test_repository_progress_is_current():
    assert main(["--check"], root=ROOT) == 0
