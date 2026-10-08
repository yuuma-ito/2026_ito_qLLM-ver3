"""Progress snapshots and Slack delivery without external requests."""
import json
import smtplib
import urllib.error

import pytest

from scripts import notify_progress as notify
from harness.run_state import RunTracker


@pytest.fixture
def experiment(tmp_path):
    config = {"experiment_id": "progress_test", "models": ["mock"],
              "tasks": ["T1_Bell"], "seeds": [0, 1],
              "conditions": ["baseline"], "output_dir": "results/progress_test"}
    output = tmp_path / config["output_dir"]
    output.mkdir(parents=True)
    return config, output, tmp_path


def row(seed, **kwargs):
    return {"experiment_id": "progress_test", "condition_id": "baseline",
            "model_spec": "mock", "task_id": "T1_Bell", "base_seed": seed,
            "L2": False, "rounds": [], **kwargs}


def write_rows(output, rows):
    (output / "raw.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_progress_ignores_partial_write_and_separates_api_from_code_failure(experiment):
    config, output, root = experiment
    write_rows(output, [row(0, rounds=[{"generation_error": "private error"}])])
    with (output / "raw.jsonl").open("a") as handle:
        handle.write('{"experiment_id":')
    progress = notify.snapshot(config, root)
    assert progress["recorded"] == 1
    assert progress["planned"] == 2
    assert progress["api_failures"] == 1
    assert progress["pending_write"]
    text = notify.message(progress, "Asia/Tokyo")
    assert "50.0%" in text
    assert "private error" not in text


def test_duplicate_and_other_experiment_cannot_inflate_completion(experiment):
    config, output, root = experiment
    write_rows(output, [row(0), row(0), row(1, experiment_id="other")])
    progress = notify.snapshot(config, root)
    assert progress["recorded"] == 1
    assert progress["duplicates"] == 1
    assert progress["unexpected"] == 1
    assert "未完了" in progress["state"]


def test_completed_code_failure_is_not_api_failure(experiment):
    config, output, root = experiment
    write_rows(output, [row(0, error_category="wrong_output"), row(1, L2=True)])
    progress = notify.snapshot(config, root)
    assert progress["api_failures"] == 0
    assert progress["passed_L2"] == progress["failed_L2"] == 1
    assert progress["state"] == "記録完了・検証待ち"
    (output / "automation_report.json").write_text('{"passed": true}')
    assert notify.snapshot(config, root)["state"] == "記録完了・自動検証成功"


def test_latest_follows_new_run_without_selecting_other_experiment(experiment):
    config, output, root = experiment
    source = root / "config.json"
    source.write_text(json.dumps(config))
    (output / "experiment_config.json").write_text(json.dumps(config))
    latest = dict(config, experiment_id="progress_test_20261007T123000Z")
    new = root / "results" / latest["experiment_id"]
    new.mkdir()
    (new / "experiment_config.json").write_text(json.dumps(latest))
    other = root / "results" / "other"
    other.mkdir()
    (other / "experiment_config.json").write_text('{"experiment_id": "other"}')
    assert notify.resolve_config(source, True, root) == latest
    assert notify.resolve_config(source, False, root) == config


def test_corrupt_complete_record_fails_instead_of_reporting_progress(experiment):
    config, output, root = experiment
    (output / "raw.jsonl").write_text("corrupt record\n")
    with pytest.raises(ValueError):
        notify.snapshot(config, root)


def test_send_checks_acknowledgement_and_keeps_url_out_of_errors(monkeypatch):
    webhook = "https://hooks.slack.com/services/test/test/private-test-value"
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return b"ok"
    def success(request, timeout):
        assert json.loads(request.data) == {"text": "進捗"}
        assert timeout == 15
        return Response()
    monkeypatch.setattr(notify.urllib.request, "urlopen", success)
    notify.send(webhook, "進捗")
    def failure(*args, **kwargs):
        raise urllib.error.URLError(webhook)
    monkeypatch.setattr(notify.urllib.request, "urlopen", failure)
    with pytest.raises(RuntimeError) as caught:
        notify.send(webhook, "進捗")
    assert webhook not in str(caught.value)
    with pytest.raises(ValueError):
        notify.send("https://example.com/services/test", "進捗")


def test_dry_run_needs_no_credentials_or_network(experiment, monkeypatch, capsys):
    config, _, root = experiment
    source = root / "config.json"
    source.write_text(json.dumps(config))
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(notify, "send", lambda *_: pytest.fail("Dry run sent a message"))
    assert notify.main(["--config", str(source), "--dry-run"]) == 0
    assert "未開始" in capsys.readouterr().out


@pytest.mark.parametrize("result", [
    {"ok": True, "channel": "D08MNC25KA8"},
    {"ok": False, "error": "channel_not_found"},
    {"ok": True, "channel": "DOTHER"},
])
def test_channel_delivery_requires_success_at_requested_destination(monkeypatch, result):
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, *args):
            return json.dumps(result).encode()
    def deliver(request, timeout):
        assert request.full_url == "https://slack.com/api/chat.postMessage"
        assert request.get_header("Authorization") == "Bearer test-token"
        assert json.loads(request.data)["channel"] == "D08MNC25KA8"
        return Response()
    monkeypatch.setattr(notify.urllib.request, "urlopen", deliver)
    if result == {"ok": True, "channel": "D08MNC25KA8"}:
        notify.send_to_channel("test-token", "D08MNC25KA8", "進捗")
    else:
        with pytest.raises(RuntimeError):
            notify.send_to_channel("test-token", "D08MNC25KA8", "進捗")


def test_explicit_channel_cannot_fall_back_to_webhook(experiment, monkeypatch, capsys):
    config, _, root = experiment
    source = root / "config.json"
    source.write_text(json.dumps(config))
    monkeypatch.setattr(notify, "load_dotenv", lambda *_: None)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/test/test/test")
    monkeypatch.setattr(notify, "send", lambda *_: pytest.fail("Wrong destination via webhook"))
    assert notify.main(["--config", str(source), "--channel", "D08MNC25KA8"]) == 1
    assert "SLACK_BOT_TOKEN" in capsys.readouterr().err


@pytest.fixture
def mail_settings(monkeypatch):
    settings = {"SLACK_EMAIL_TO": "slack-forward@example.invalid",
                "EMAIL_FROM": "sender@example.invalid", "SMTP_HOST": "smtp.example.invalid",
                "SMTP_PORT": "587", "SMTP_SECURITY": "starttls",
                "SMTP_USERNAME": "sender@example.invalid", "SMTP_PASSWORD": "private-test-password"}
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    return settings


@pytest.mark.parametrize("security", ["starttls", "ssl"])
def test_email_encrypts_before_authentication_and_sends_one_recipient(mail_settings, monkeypatch, security):
    monkeypatch.setenv("SMTP_SECURITY", security)
    monkeypatch.delenv("SMTP_PORT")
    events = []
    class SMTP:
        def __init__(self, host, port, timeout, **kwargs):
            assert host == mail_settings["SMTP_HOST"]
            assert port == (465 if security == "ssl" else 587)
            assert timeout == 30
            self.encrypted = "context" in kwargs
            if self.encrypted:
                assert kwargs["context"].check_hostname
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def ehlo(self):
            events.append("ehlo")
        def starttls(self, *, context):
            assert context.check_hostname
            self.encrypted = True
            events.append("starttls")
        def login(self, username, password):
            assert self.encrypted
            assert username == mail_settings["SMTP_USERNAME"]
            assert password == mail_settings["SMTP_PASSWORD"]
            events.append("login")
        def send_message(self, mail, *, from_addr, to_addrs):
            assert events[-1] == "login"
            assert from_addr == mail_settings["EMAIL_FROM"]
            assert to_addrs == [mail_settings["SLACK_EMAIL_TO"]]
            assert "進捗" in mail.get_content()
            assert str(mail["Subject"]) == "実験進捗: test"
            assert mail["Message-ID"]
            events.append("sent")
            return {}
    monkeypatch.setattr(notify.smtplib, "SMTP", SMTP)
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", SMTP)
    notify.send_email("進捗", "test")
    if security == "starttls":
        assert events == ["ehlo", "starttls", "ehlo", "login", "sent"]


@pytest.mark.parametrize("failure", ["authentication", "connection"])
def test_email_errors_do_not_expose_credentials(mail_settings, monkeypatch, failure):
    def failed(*args, **kwargs):
        secret = mail_settings["SMTP_PASSWORD"]
        if failure == "authentication":
            raise smtplib.SMTPAuthenticationError(535, secret.encode())
        raise OSError(secret)
    monkeypatch.setattr(notify.smtplib, "SMTP", failed)
    with pytest.raises(RuntimeError) as caught:
        notify.send_email("進捗", "test")
    assert mail_settings["SMTP_PASSWORD"] not in str(caught.value)


@pytest.mark.parametrize("key,value", [
    ("SLACK_EMAIL_TO", ""), ("SLACK_EMAIL_TO", "first@example.invalid,second@example.invalid"),
    ("EMAIL_FROM", "sender@example.invalid\nBcc: other@example.invalid"),
    ("SMTP_SECURITY", "plain"), ("SMTP_PASSWORD", ""),
])
def test_bad_email_settings_fail_before_connecting(mail_settings, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    monkeypatch.setattr(notify.smtplib, "SMTP", lambda *_a, **_k: pytest.fail("Invalid settings reached network"))
    with pytest.raises((RuntimeError, ValueError)):
        notify.send_email("進捗", "test")


def test_email_transport_ignores_slack_api_settings(experiment, monkeypatch, capsys):
    config, _, root = experiment
    source = root / "config.json"
    source.write_text(json.dumps(config))
    monkeypatch.setenv("SLACK_CHANNEL_ID", "D08MNC25KA8")
    monkeypatch.setattr(notify, "send_to_channel", lambda *_: pytest.fail("Email used Slack API"))
    sent = []
    monkeypatch.setattr(notify, "send_email", lambda text, experiment_id: sent.append((text, experiment_id)))
    assert notify.main(["--config", str(source), "--transport", "email"]) == 0
    assert len(sent) == 1
    assert "Slack delivery is not yet confirmed" in capsys.readouterr().out


def test_email_dry_run_does_not_send(experiment, monkeypatch):
    config, _, root = experiment
    source = root / "config.json"
    source.write_text(json.dumps(config))
    monkeypatch.setattr(notify, "send_email", lambda *_: pytest.fail("Dry run sent mail"))
    assert notify.main(["--config", str(source), "--transport", "email", "--dry-run"]) == 0


def test_overview_includes_running_other_family_even_when_events_disabled(experiment):
    config, output, root = experiment
    write_rows(output, [row(0)])
    (output / "experiment_config.json").write_text(json.dumps(config))
    quick = dict(config, experiment_id="quick", output_dir="results/quick")
    quick_output = root / quick["output_dir"]
    quick_output.mkdir()
    (quick_output / "experiment_config.json").write_text(json.dumps(quick))
    write_rows(quick_output, [row(0, experiment_id="quick"), row(1, experiment_id="quick")])
    (quick_output / "automation_report.json").write_text('{"passed": true}')
    with RunTracker(output, config["experiment_id"], root=root) as tracker:
        tracker.update(phase="generating", model="mock", task="T1_Bell", seed=0,
                       condition="baseline", notification_transport="none")
        text = notify.overview("Asia/Tokyo", root)
    assert "実行中: 1件" in text
    assert text.index("実験: progress_test") < text.index("実験: quick")
    assert "記録: 1/2" in text
    assert "現在の作業: モデル: mock・タスク: T1_Bell・seed: 0・条件: baseline" in text


def test_overview_reports_verified_failure_after_all_records_written(experiment):
    config, output, root = experiment
    (output / "experiment_config.json").write_text(json.dumps(config))
    write_rows(output, [row(0, rounds=[{"generation_error": "private"}]), row(1)])
    with RunTracker(output, config["experiment_id"], root=root) as tracker:
        tracker.finish("failed", phase="verifying", failure_type="RuntimeError")
    text = notify.overview("Asia/Tokyo", root)
    assert "実行中: 0件・未完了／要確認: 1件" in text
    assert "失敗（verifying）" in text
    assert "API接続・タイムアウト障害を含む記録: 1件" in text
    assert "終了・停止時刻:" in text
    assert "現在の作業:" not in text
    assert "private" not in text


def test_unknown_evaluation_error_is_not_counted_as_api_failure(experiment):
    config, output, root = experiment
    write_rows(output, [row(0, error_category="unknown_error", rounds=[
        {"error_category": "unknown_error", "error_message": "AttributeError: counts"}
    ])])
    progress = notify.snapshot(config, root)
    assert progress["api_failures"] == 0
    assert progress["unknown_failures"] == 1
    assert "要確認" in progress["state"]


def test_overview_includes_starting_run_before_saved_config(experiment):
    config, output, root = experiment
    with RunTracker(output, config["experiment_id"], root=root):
        text = notify.overview("Asia/Tokyo", root)
    assert "実行中: 1件" in text
    assert "progress_test" in text
    assert "保存設定作成前" in text


def test_overview_cli_dry_run_never_delivers(experiment, monkeypatch, capsys):
    _, _, root = experiment
    monkeypatch.setattr(notify, "ROOT", root)
    overview = notify.overview
    monkeypatch.setattr(notify, "overview", lambda timezone: overview(timezone, root))
    monkeypatch.setattr(notify, "deliver", lambda *_: pytest.fail("Dry run delivered"))
    assert notify.main(["--overview", "--transport", "email", "--dry-run"]) == 0
    assert "保存済みの実験はありません" in capsys.readouterr().out
