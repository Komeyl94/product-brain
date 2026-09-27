"""Self-check for the hub files pb sync manages: doc folders, .gitignore, README.

Run: python3 tests/test_pb_hub_files.py
"""

import json
import runpy
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    pb = runpy.run_path(str(ROOT / "bin/pb"), run_name="pb_under_test")
    with tempfile.TemporaryDirectory() as tmp:
        hub = Path(tmp)
        subprocess.run(["git", "init", "-q", str(hub)], check=True)
        subprocess.run(["git", "-C", str(hub), "remote", "add", "origin",
                        "ssh://git@git.example.com:2222/team/acme-brain.git"], check=True)
        shutil.copy(ROOT / "templates/brain.config.template.json", hub / "brain.config.json")
        cfg = pb["load_config"](hub)

        for _ in range(2):  # second run must change nothing
            pb["ensure_doc_folders"](hub, cfg, False)
            pb["ensure_exclusions"](hub, hub / "repos", hub / "graph", [], False)
            pb["write_readme"](hub, cfg, hub / "graph", False)

        for dtype in cfg["doc_types"]:
            assert (hub / "docs" / dtype / ".gitkeep").exists(), dtype
        assert (hub / ".gitignore").read_text(encoding="utf-8").count(".claude/settings.local.json") == 1

        readme = (hub / "README.md").read_text(encoding="utf-8")
        assert "{{" not in readme, "unfilled placeholder"
        assert "git clone ssh://git@git.example.com:2222/team/acme-brain.git" in readme
        assert "Open the `acme-brain` folder" in readme
        assert "| `docs/specs/` | What a feature should do and why |" in readme

        # the hub settings template must parse and carry the UTF-8 fix
        settings = json.loads((ROOT / "templates/hub-settings.template.json").read_text(encoding="utf-8"))
        assert settings["env"]["PYTHONUTF8"] == "1"
        for name in ("hub-mcp.template.json", "hub-settings.local.example.json"):
            text = (ROOT / "templates" / name).read_text(encoding="utf-8")
            json.loads(text)
            assert "${" not in text, f"{name}: .mcp.json can't expand ${{VAR}} from settings env"
    print("ok")


if __name__ == "__main__":
    main()
