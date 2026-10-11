"""The smoke command runs one question against the real model.

The test covers its wiring only: the client factory is replaced with a replay of a recorded
response, so the command makes no call.
"""

from warrant.agent import smoke
from warrant.agent.config import client as real_client


class FakeClient:
    def __init__(self, create):
        self.messages = type("Messages", (), {"create": staticmethod(create)})()


def test_the_smoke_command_answers_one_question_and_reports_its_usage(
    replay, write_line_config, tmp_path, monkeypatch, capsys
):
    create = replay("tool_use_sql", "answer")
    monkeypatch.setattr("warrant.agent.claude.client", lambda config: FakeClient(create))

    exit_code = smoke.main(
        ["--config", str(write_line_config), "--question", "open-orders", "--work-dir", str(tmp_path / "work")]
    )

    printed = capsys.readouterr().out
    assert exit_code == 0
    assert "open-orders" in printed
    assert "SELECT COUNT(*) FROM workorders WHERE status = 'OPEN'" in printed
    assert "2600" in printed  # input tokens across both calls
    assert len(create.calls) == 2


def test_the_smoke_command_rejects_a_question_the_configuration_does_not_name(write_line_config):
    exit_code = smoke.main(["--config", str(write_line_config), "--question", "no-such-question"])
    assert exit_code == 2


def test_the_smoke_command_reports_a_misconfigured_model_without_calling_it(
    write_line_config, monkeypatch, capsys
):
    """The committed configuration still carries a placeholder region, so this is the real path.

    The real client factory is put back: it refuses the region before building anything, so this
    still reaches no network.
    """
    monkeypatch.setattr("warrant.agent.claude.client", real_client)

    exit_code = smoke.main(["--config", str(write_line_config), "--question", "open-orders"])

    assert exit_code == 2
    assert "not an AWS region" in capsys.readouterr().out
