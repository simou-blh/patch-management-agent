from scripts.check_artifacts import (
    ROOT,
    check_compose,
    check_playbooks,
    check_schemas,
    main,
)


def test_committed_artifacts_pass():
    assert main(root=ROOT) == 0


def test_invalid_schema_json_is_reported(tmp_path):
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas/broken.json").write_text("{not json", encoding="utf-8")
    problems = check_schemas(tmp_path)
    assert any("broken.json" in problem for problem in problems)


def test_compose_requires_digest_pinned_image(tmp_path):
    (tmp_path / "compose.yml").write_text(
        "services:\n"
        "  semaphore:\n"
        "    image: semaphoreui/semaphore:latest\n"
        "    ports: ['127.0.0.1:3000:3000']\n"
        "    environment:\n"
        "      SEMAPHORE_ADMIN_PASSWORD: ${SEMAPHORE_ADMIN_PASSWORD:?required}\n"
        "      SEMAPHORE_ACCESS_KEY_ENCRYPTION: ${SEMAPHORE_ACCESS_KEY_ENCRYPTION:?required}\n"
        "  semaphore-mcp:\n"
        "    profiles: [upstream]\n",
        encoding="utf-8",
    )
    problems = check_compose(tmp_path)
    assert any("digest-pinned" in problem for problem in problems)


def test_mutation_module_in_read_only_playbook_is_reported(tmp_path):
    folder = tmp_path / "playbooks"
    folder.mkdir()
    (folder / "inspect.yml").write_text(
        "---\n"
        "- name: Inspect\n"
        "  hosts: all\n"
        "  tasks:\n"
        "    - name: Change packages\n"
        "      ansible.builtin.apt:\n"
        "        name: curl\n",
        encoding="utf-8",
    )
    problems = check_playbooks(tmp_path)
    assert any("read-only" in problem for problem in problems)
