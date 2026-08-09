import pytest
from meeting_intelligence.cli.main import main


@pytest.mark.parametrize("argument,expected", [("--help", "meeting-process"), ("--version", "0.1.0")])
def test_cli_options(argument: str, expected: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([argument])
    assert exc.value.code == 0
    assert expected in capsys.readouterr().out

