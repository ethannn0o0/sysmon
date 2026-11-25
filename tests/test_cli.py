import json

from sysmon.cli import main


def test_json_to_stdout_with_filter(capsys):
    assert main(["--json", "-f", "python"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert all("python" in p["name"].lower() for p in data["processes"])


def test_json_to_file(tmp_path):
    out = tmp_path / "snap.json"
    assert main(["--json", "-n", "2", "-o", str(out)]) == 0
    assert "timestamp" in json.loads(out.read_text(encoding="utf-8"))


def test_output_requires_json():
    assert main(["-o", "x.json"]) == 2


def test_once_with_no_match_does_not_crash(capsys):
    assert main(["--once", "-f", "no-such-process-xyz"]) == 0
    assert "no matching processes" in capsys.readouterr().out
