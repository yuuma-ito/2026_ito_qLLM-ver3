"""Install privately fetched lab skills with a small Codex compatibility layer.

The repository contains only the adapter and source metadata, never upstream text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "configs/lab_codex_skills.json"
ADAPTER = ROOT / "docs/codex/lab_skill_compatibility.md"
STAMP = ".lab-codex-source.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_hashes(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(folder)): digest(p)
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.name != STAMP and "__pycache__" not in p.parts
    }


def recipe_hash(lock: dict, adapter: str) -> str:
    payload = json.dumps(lock, sort_keys=True) + adapter
    return hashlib.sha256(payload.encode()).hexdigest()


def installed_status(destination: Path, lock: dict, adapter: str) -> list[dict]:
    statuses = []
    for entry in lock["skills"]:
        folder = destination / entry["name"]
        if not folder.exists():
            status = "missing"
        else:
            try:
                stamp = json.loads((folder / STAMP).read_text())
                valid = (
                    stamp["source_repo"] == lock["repo"]
                    and stamp["source_revision"] == lock["revision"]
                    and stamp["recipe_sha256"] == recipe_hash(lock, adapter)
                    and stamp["files_sha256"] == file_hashes(folder)
                )
                status = "installed" if valid else "different_or_modified"
            except (OSError, ValueError, KeyError):
                status = "unmanaged"
        statuses.append({"name": entry["name"], "status": status, "mode": entry["mode"]})
    return statuses


def adapt_skill(folder: Path, entry: dict, lock: dict, adapter: str, destination: Path) -> None:
    skill = folder / "SKILL.md"
    if digest(skill) != entry["source_skill_sha256"]:
        raise ValueError(f"Upstream SKILL.md hash mismatch: {entry['name']}")
    source = skill.read_text()
    match = re.match(r"\A---\n(.*?)\n---\n", source, re.S)
    if not match or not re.search(rf"^name:\s*{re.escape(entry['name'])}\s*$", match[1], re.M):
        raise ValueError(f"Invalid upstream skill metadata: {entry['name']}")
    # Relative sibling references (e.g. interim -> slide-review) remain intact.
    body = source[match.end():].replace("${CLAUDE_PLUGIN_ROOT}/skills", str(destination))
    body = body.replace("~/.claude/skills", str(destination))
    compatibility = adapter.replace("@SKILL_DIR@", str(destination / entry["name"]))
    compatibility = compatibility.replace("@SKILLS_ROOT@", str(destination))
    if entry["mode"] == "guidance-only":
        compatibility += (
            "\n### pii-filter の利用範囲\n\n"
            "この導入ではClaude専用フック・pii CLI・対応表の権限設定を移植していない。"
            "Codexへの自動送信防止・自動匿名化は無効であり、有効と説明しない。"
            "下の元文書にあるCLI実行手順はこの環境では実行しない。"
            "個人情報の保護を依頼されたら、まずこの制約を説明し、"
            "生の名簿や対応表を読まずに、別途ローカル匿名化の手段を整える。\n"
        )
    header = f"---\nname: {entry['name']}\ndescription: {json.dumps(entry['description'], ensure_ascii=False)}\n---\n"
    skill.write_text(header + compatibility + "\n\n<!-- Privately installed upstream instructions follow. -->\n" + body)
    agents = folder / "agents"
    agents.mkdir(exist_ok=True)
    metadata = agents / "openai.yaml"
    if metadata.exists():
        raise ValueError(f"Upstream already has Codex metadata; review before adapting: {entry['name']}")
    metadata.write_text(
        "interface:\n"
        f"  display_name: {json.dumps(entry['name'])}\n"
        f"  short_description: {json.dumps(entry['description'], ensure_ascii=False)}\n"
        f"  default_prompt: {json.dumps('Use $' + entry['name'] + ' for the requested material.')}\n"
    )
    stamp = {
        "source_repo": lock["repo"], "source_revision": lock["revision"],
        "source_path": entry["path"], "mode": entry["mode"],
        "recipe_sha256": recipe_hash(lock, adapter), "files_sha256": file_hashes(folder),
    }
    (folder / STAMP).write_text(json.dumps(stamp, ensure_ascii=False, indent=2) + "\n")


def promote(staged: Path, destination: Path, lock: dict, adapter: str) -> None:
    """Preflight every entry before touching any existing installation."""
    conflicts = [s for s in installed_status(destination, lock, adapter)
                 if s["status"] not in {"missing", "installed"}]
    if conflicts:
        raise ValueError("Existing skills will not be overwritten: " + ", ".join(s["name"] for s in conflicts))
    destination.mkdir(parents=True, exist_ok=True)
    for entry in lock["skills"]:
        final = destination / entry["name"]
        if final.exists():
            continue
        # Publish a complete directory; a failed copy never leaves a discoverable half-skill.
        with tempfile.TemporaryDirectory(prefix=".lab-skill-", dir=destination) as temp:
            prepared = Path(temp) / entry["name"]
            shutil.copytree(staged / entry["name"], prepared)
            prepared.rename(final)


def find_installer() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    return codex_home / "skills/.system/skill-installer/scripts/install-skill-from-github.py"


def fetch_pinned_skills(lock: dict, stage: Path, source: Path, repo_url: str | None = None) -> None:
    """Fallback for installer versions whose shallow clone cannot check out an old SHA."""
    url = repo_url or f"https://github.com/{lock['repo']}.git"
    subprocess.run(["git", "init", "--quiet", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "remote", "add", "origin", url], check=True)
    subprocess.run(["git", "-C", str(source), "fetch", "--quiet", "--depth", "1", "origin", lock["revision"]], check=True)
    subprocess.run(["git", "-C", str(source), "checkout", "--quiet", "--detach", "FETCH_HEAD"], check=True)
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != lock["revision"]:
        raise ValueError("Fetched revision does not match the pinned source.")
    for entry in lock["skills"]:
        folder = source / entry["path"]
        if not folder.resolve().is_relative_to(source.resolve()):
            raise ValueError("Skill path escapes the source checkout.")
        if folder.is_symlink() or any(p.is_symlink() for p in folder.rglob("*")):
            raise ValueError("Symbolic links are not supported in fetched skills.")
        if not (folder / "SKILL.md").is_file():
            raise ValueError(f"Skill source missing: {entry['name']}")
        shutil.copytree(folder, stage / entry["name"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=Path.home() / ".agents/skills")
    parser.add_argument("--installer", type=Path, default=find_installer())
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without network or writes")
    parser.add_argument("--check", action="store_true", help="Verify installed files without network or writes")
    args = parser.parse_args(argv)
    lock, adapter = json.loads(LOCK.read_text()), ADAPTER.read_text()
    destination = args.dest.expanduser().resolve()
    statuses = installed_status(destination, lock, adapter)
    if args.dry_run or args.check:
        print(json.dumps({"destination": str(destination), "skills": statuses}, ensure_ascii=False, indent=2))
        return 0 if args.dry_run or all(s["status"] == "installed" for s in statuses) else 1
    if all(s["status"] == "installed" for s in statuses):
        print("All lab skills are already installed and unchanged.")
        return 0
    if any(s["status"] not in {"missing", "installed"} for s in statuses):
        raise ValueError("Existing unmanaged/modified skills found; use --check and a separate --dest.")
    if not args.installer.is_file():
        raise ValueError("Codex skill-installer helper not found; specify --installer PATH.")
    cache = ROOT / ".cache/lab_codex_skills"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="install-", dir=cache) as temp:
        stage = Path(temp) / "skills"
        command = [sys.executable, str(args.installer), "--repo", lock["repo"],
                   "--ref", lock["revision"], "--method", "git", "--dest", str(stage),
                   "--path", *[s["path"] for s in lock["skills"]]]
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            # The helper may have copied some entries before failing. Only its
            # disposable staging tree is removed; installed skills are untouched.
            if stage.exists():
                shutil.rmtree(stage)
            print("Installer could not fetch the pinned version; trying an explicit SHA fetch.")
            fetch_pinned_skills(lock, stage, Path(temp) / "source")
        for entry in lock["skills"]:
            adapt_skill(stage / entry["name"], entry, lock, adapter, destination)
        promote(stage, destination, lock, adapter)
    print(json.dumps({"destination": str(destination), "skills": installed_status(destination, lock, adapter)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
