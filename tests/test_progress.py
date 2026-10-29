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


def split_plan(done=1):
    parent = "- [ ] Checkpoint 0"
    heading = parent if done < 4 else "- [x] Checkpoint 0 Evidence: all four deliverables verified"
    children = "\n".join(
        f"  - [{'x' if step < done else ' '}] Deliverable {step}"
        + (" Evidence: merged PR and test record" if step < done else "")
        for step in range(4))
    return sample_plan().replace(parent, heading + "\n" + children, 1)


@pytest.mark.parametrize("done", [0, 1, 2, 3, 4])
def test_substeps_contribute_five_percent_without_double_counting(done):
    result = updated_readme(f"{START}\n{END}", split_plan(done))
    first_sprint = next(line for line in result.splitlines() if line.startswith("Sprint 1"))
    bar = "█" * done + "░" * (20 - done)
    assert f"[{bar}] {done * 5:>3}%  {int(done == 4)}/5 full checkpoints" in first_sprint
    other_sprints = [line for line in result.splitlines()
                     if line.startswith("Sprint ") and not line.startswith("Sprint 1")]
    assert len(other_sprints) == 3
    assert all(line.endswith("]   0%  0/5 full checkpoints") for line in other_sprints)


@pytest.mark.parametrize("plan", [
    split_plan().replace("  - [ ] Deliverable 3\n", "", 1),
    split_plan().replace("  - [ ] Deliverable 3", "  - [ ] Deliverable 3\n  - [ ] Extra", 1),
    split_plan().replace("  - [x] Deliverable 0 Evidence: merged PR and test record", "  - [x] Deliverable 0", 1),
    split_plan().replace("- [ ] Checkpoint 0", "- [x] Checkpoint 0 Evidence: prematurely accepted", 1),
    split_plan(4).replace("- [x] Checkpoint 0 Evidence: all four deliverables verified", "- [ ] Checkpoint 0", 1),
    split_plan().replace("  - [ ] Deliverable 3", "    - [ ] Deliverable 3", 1),
    split_plan().replace("  - [ ] Deliverable 3", "  - [q] Deliverable 3", 1),
    sample_plan().replace("<!-- sprint:1:start -->", "<!-- sprint:1:start -->\n  - [ ] Orphan", 1),
])
def test_invalid_partial_progress_is_rejected(plan):
    with pytest.raises(ValueError):
        updated_readme(f"{START}\n{END}", plan)
