"""Every DKP-8-SIMULATION-001 provision is mapped; references resolve; the CLI runs."""
from pathlib import Path

from dkp8 import traceability as T
from dkp8.__main__ import main

ROOT = Path(__file__).resolve().parents[2]


def test_every_registry_provision_is_traced_with_a_valid_status():
    assert set(T.registry_ids()) == set(T.MATRIX) and len(T.MATRIX) == 48
    assert all(row["status"] in T.STATUSES for row in T.MATRIX.values())
    assert all(row["remaining"] for row in T.MATRIX.values() if row["status"] != "IMPLEMENTED_AND_TESTED")


def test_references_resolve_and_tests_exist():
    for row in T.MATRIX.values():
        assert all(T.resolve(ref) for ref in row["implementation"]), row
        assert all((ROOT / t).is_file() for t in row["tests"]), row


def test_markdown_lists_every_provision():
    text = T.markdown()
    assert all(rid in text for rid in T.registry_ids())


def test_cli(tmp_path, capsys):
    assert main(["catalog"]) == 0
    assert main(["trace", "--md", str(tmp_path / "t.md")]) == 0 and (tmp_path / "t.md").read_text(encoding="utf-8")
    assert main(["workbench", "--out", str(tmp_path / "wb")]) == 0
    assert "DKP-5-HABITAT-001" in (tmp_path / "wb" / "WORKBENCH.md").read_text(encoding="utf-8")
    assert main(["status"]) == 0 and '"authorities": 0' in capsys.readouterr().out
