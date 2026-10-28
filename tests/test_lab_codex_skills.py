"""Check installation integrity without a network call or model invocation."""
import json
import subprocess

import pytest

from scripts import setup_lab_codex_skills as setup


@pytest.fixture
def bundle(tmp_path):
    stage, destination = tmp_path / "stage", tmp_path / "installed"
    entry = {
        "name": "example-review", "path": "plugins/example/skills/example-review",
        "description": "Review a supplied example using its accompanying local evidence.",
        "mode": "skill",
    }
    skill = stage / entry["name"]
    (skill / "scripts").mkdir(parents=True)
    (skill / "scripts/facts.py").write_text("print('local facts')\n")
    (skill / "SKILL.md").write_text(
        "---\nname: example-review\ndescription: Example original.\n---\n"
        "Read [facts](scripts/facts.py). Use ${CLAUDE_PLUGIN_ROOT}/skills/example-review.\n"
    )
    entry["source_skill_sha256"] = setup.digest(skill / "SKILL.md")
    lock = {"repo": "example/private-skills", "revision": "a" * 40, "skills": [entry]}
    adapter = "Read @SKILL_DIR@; siblings are in @SKILLS_ROOT@.\n"
    return stage, destination, entry, lock, adapter


def test_adapt_preserves_helpers_and_resolves_plugin_paths(bundle):
    stage, destination, entry, lock, adapter = bundle
    folder = stage / entry["name"]
    original_helper = (folder / "scripts/facts.py").read_bytes()
    setup.adapt_skill(folder, entry, lock, adapter, destination)
    text = (folder / "SKILL.md").read_text()
    assert "${CLAUDE_PLUGIN_ROOT}" not in text
    assert "@SKILL_DIR@" not in text
    assert str(destination / entry["name"]) in text
    assert "[facts](scripts/facts.py)" in text
    assert (folder / "scripts/facts.py").read_bytes() == original_helper
    setup.promote(stage, destination, lock, adapter)
    assert setup.installed_status(destination, lock, adapter)[0]["status"] == "installed"


def test_source_mismatch_is_rejected_before_rewriting(bundle):
    stage, destination, entry, lock, adapter = bundle
    entry["source_skill_sha256"] = "0" * 64
    before = (stage / entry["name"] / "SKILL.md").read_bytes()
    with pytest.raises(ValueError, match="hash mismatch"):
        setup.adapt_skill(stage / entry["name"], entry, lock, adapter, destination)
    assert (stage / entry["name"] / "SKILL.md").read_bytes() == before
    assert not destination.exists()


def test_reinstall_preserves_installed_files_and_detects_local_edits(bundle):
    stage, destination, entry, lock, adapter = bundle
    setup.adapt_skill(stage / entry["name"], entry, lock, adapter, destination)
    setup.promote(stage, destination, lock, adapter)
    installed = destination / entry["name"] / "SKILL.md"
    before = installed.stat().st_mtime_ns
    setup.promote(stage, destination, lock, adapter)
    assert installed.stat().st_mtime_ns == before
    installed.write_text(installed.read_text() + "\nUser edit.\n")
    assert setup.installed_status(destination, lock, adapter)[0]["status"] == "different_or_modified"
    with pytest.raises(ValueError, match="will not be overwritten"):
        setup.promote(stage, destination, lock, adapter)
    assert installed.read_text().endswith("User edit.\n")


def test_existing_unmanaged_skill_prevents_partial_install(bundle):
    stage, destination, entry, lock, adapter = bundle
    conflict = destination / "other-skill"
    conflict.mkdir(parents=True)
    (conflict / "SKILL.md").write_text("User's existing skill.")
    lock["skills"].append({**entry, "name": "other-skill"})
    setup.adapt_skill(stage / entry["name"], entry, lock, adapter, destination)
    with pytest.raises(ValueError, match="will not be overwritten"):
        setup.promote(stage, destination, lock, adapter)
    assert not (destination / entry["name"]).exists()
    assert (conflict / "SKILL.md").read_text() == "User's existing skill."


def test_filter_mode_does_not_claim_automatic_protection(bundle):
    stage, destination, entry, lock, adapter = bundle
    entry["mode"] = "guidance-only"
    setup.adapt_skill(stage / entry["name"], entry, lock, adapter, destination)
    assert "自動送信防止・自動匿名化は無効" in (stage / entry["name"] / "SKILL.md").read_text()


def test_dry_run_has_no_network_or_destination_writes(bundle, monkeypatch, tmp_path):
    stage, destination, entry, lock, adapter = bundle
    lock_file, adapter_file = tmp_path / "lock.json", tmp_path / "adapter.md"
    lock_file.write_text(json.dumps(lock))
    adapter_file.write_text(adapter)
    monkeypatch.setattr(setup, "LOCK", lock_file)
    monkeypatch.setattr(setup, "ADAPTER", adapter_file)
    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **k: pytest.fail("Unexpected network/tool call"))
    assert setup.main(["--dest", str(destination), "--dry-run"]) == 0
    assert setup.main(["--dest", str(destination), "--check"]) == 1
    assert not destination.exists()


def test_explicit_fetch_installs_pinned_old_revision_not_current_head(bundle, tmp_path):
    stage, destination, entry, lock, adapter = bundle
    repo = tmp_path / "upstream"
    original = (stage / entry["name"] / "SKILL.md").read_bytes()
    upstream_skill = repo / entry["path"]
    upstream_skill.mkdir(parents=True)
    (upstream_skill / "SKILL.md").write_bytes(original)
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    def commit(message):
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "--quiet", "-m", message], check=True)
    commit("original")
    lock["revision"] = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    (upstream_skill / "SKILL.md").write_text("newer, unapproved content")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    commit("newer")
    fetched = tmp_path / "fetched"
    setup.fetch_pinned_skills(lock, fetched, tmp_path / "checkout", repo.as_uri())
    assert (fetched / entry["name"] / "SKILL.md").read_bytes() == original
