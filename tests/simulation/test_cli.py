"""CLI: runs end to end, exits 0, survives a console that cannot print Unicode (v1 crashed on cp1252)."""

import io
import sys

from simulation.run_prevention_simulation import main


def test_smoke_cli(tmp_path, capsys):
    rc = main(["--smoke", "--output-dir", str(tmp_path / "smoke")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "result_id:" in out
    assert (tmp_path / "smoke" / "run_manifest.json").exists()


def test_cli_output_is_ascii(tmp_path, capsys):
    main(["--smoke", "--output-dir", str(tmp_path / "s")])
    capsys.readouterr().out.encode("ascii")


def test_cli_on_cp1252_console(tmp_path, monkeypatch):
    buf = io.BytesIO()
    stream = io.TextIOWrapper(buf, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stream)
    assert main(["--smoke", "--output-dir", str(tmp_path / "c")]) == 0
    stream.flush()


def test_cli_requires_a_config(capsys):
    assert main([]) == 1
