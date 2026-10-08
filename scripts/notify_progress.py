"""Read experiment progress and send one Slack notification (for cron/timers)."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import html
import json
import os
from pathlib import Path
import smtplib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from harness.experiment import expected_keys, has_api_failure, load_config, record_key, validate_config
from harness.run_state import observation, read_state

ROOT = Path(__file__).resolve().parent.parent
ACTIVE = {"running", "stalled", "heartbeat_stale"}


def resolve_config(path: Path, latest: bool, root: Path = ROOT):
    config = load_config(path)
    if latest:
        prefix = config["experiment_id"]
        candidates = []
        for saved in (root / "results").glob("*/experiment_config.json"):
            candidate = load_config(saved)
            experiment_id = candidate.get("experiment_id", "")
            if experiment_id == prefix or experiment_id.startswith(prefix + "_"):
                candidates.append(saved)
        if candidates:
            path = max(candidates, key=lambda p: (p.stat().st_mtime_ns, str(p)))
            config = load_config(path)
    return config


def snapshot(config: dict, root: Path = ROOT):
    plan = validate_config(config)
    output = root / config.get("output_dir", f"results/{config['experiment_id']}")
    raw = output / "raw.jsonl"
    expected = expected_keys(plan)
    rows = []
    pending_write = False
    if raw.exists():
        # A writer flushes after each newline. Ignore an unfinished final write.
        with raw.open("rb") as handle:
            for line in handle:
                if not line.endswith(b"\n"):
                    pending_write = True
                    break
                if line.strip():
                    rows.append(json.loads(line))
    counts = Counter(record_key(row) for row in rows)
    unique = {}
    for row in rows:
        key = record_key(row)
        if key in expected:
            unique[key] = row
    duplicates = sum(n - 1 for n in counts.values())
    unexpected = sum(n for key, n in counts.items() if key not in expected)
    api_failures = sum(has_api_failure(row, include_unknown=False) for row in unique.values())
    unknown_failures = sum(has_api_failure(row) and not has_api_failure(row, include_unknown=False)
                           for row in unique.values())
    passed = sum(row.get("L2") is True for row in unique.values())
    complete = set(unique) == expected and not (duplicates or unexpected or pending_write)
    state = "未開始" if not raw.exists() else "未完了（実行中・中断の判別なし）"
    if complete:
        state = "記録完了・検証待ち"
    report_path = output / "automation_report.json"
    if complete and report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        state = "記録完了・自動検証成功" if report.get("passed") is True else "記録完了・自動検証失敗"
    runtime = read_state(output, root)
    runtime_status = None
    if runtime and runtime["experiment_id"] == plan["experiment_id"]:
        status = observation(runtime)
        runtime_status = status
        labels = {"running": "実行中", "interrupted": "中断", "failed": "失敗",
                  "completed": "完了", "stalled": "実行中・長時間進捗なし",
                  "heartbeat_stale": "実行中・状態更新の停滞"}
        state = labels[status] + "（" + runtime.get("phase", "unknown") + "）"
        if status == "completed" and runtime.get("published"):
            state += "・プッシュ成功"
    if api_failures or unknown_failures or duplicates or unexpected:
        state += "／要確認"
    return {
        "experiment_id": plan["experiment_id"], "state": state,
        "planned": len(expected), "recorded": len(unique), "passed_L2": passed,
        "failed_L2": sum(row.get("L2") is False for row in unique.values()),
        "api_failures": api_failures, "duplicates": duplicates,
        "unknown_failures": unknown_failures,
        "unexpected": unexpected, "pending_write": pending_write,
        "runtime_status": runtime_status, "runtime": runtime if runtime_status else None,
        "last_update": datetime.fromtimestamp(raw.stat().st_mtime).astimezone() if raw.exists() else None,
    }


def message(progress: dict, timezone: str):
    zone = ZoneInfo(timezone)
    recorded, planned = progress["recorded"], progress["planned"]
    percent = 100 * recorded / planned if planned else 0
    updated = progress["last_update"]
    lines = [
        f"実験進捗 {datetime.now(zone):%Y-%m-%d %H:%M %Z}",
        f"実験: {html.escape(progress['experiment_id'])}",
        f"状態: {progress['state']}",
        f"記録: {recorded}/{planned} ({percent:.1f}%)・残り {planned - recorded}件",
        f"L2成功: {progress['passed_L2']}件・L2失敗: {progress['failed_L2']}件",
        f"API接続・タイムアウト障害を含む記録: {progress['api_failures']}件",
        f"未分類の評価エラーを含む記録: {progress.get('unknown_failures', 0)}件",
        f"重複: {progress['duplicates']}件・予定外: {progress['unexpected']}件",
        "最終記録更新: " + (updated.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S %Z") if updated else "なし"),
        "※記録件数だけではプッシュ成功を判断できません。",
    ]
    runtime = progress.get("runtime")
    if runtime:
        details = [f"段階: {runtime.get('phase', 'unknown')}"]
        if progress.get("runtime_status") in ACTIVE:
            fields = (("model", "モデル"), ("task", "タスク"),
                      ("seed", "seed"), ("condition", "条件"))
            work = [f"{label}: {html.escape(str(runtime[key]))}" for key, label in fields if key in runtime]
            if work:
                details.append("現在の作業: " + "・".join(work))
        for key, label in (("heartbeat_at", "状態更新"), ("progress_at", "作業進捗更新"),
                           ("finished_at", "終了・停止時刻")):
            if key in runtime:
                details.append(label + ": " + datetime.fromtimestamp(runtime[key], zone).strftime("%Y-%m-%d %H:%M:%S %Z"))
        if runtime.get("failure_type"):
            details.append("停止種別: " + html.escape(runtime["failure_type"]))
        lines[3:3] = details
    return "\n".join(lines)


def overview(timezone: str, root: Path = ROOT):
    """Include live runs and unresolved results across all experiment families."""
    candidates = {}
    results = (root / "results").resolve()
    for saved in results.glob("*/experiment_config.json"):
        config = load_config(saved)
        output = (root / config.get("output_dir", f"results/{config['experiment_id']}")).resolve()
        if output != saved.parent:
            continue
        candidates[output] = snapshot(config, root)
    # A starting run may not have written its saved configuration yet.
    starting = []
    for path in sorted((root / ".cache" / "run_states").glob("*.json")):
        runtime = json.loads(path.read_text(encoding="utf-8"))
        output = Path(runtime["output"]).resolve()
        if not output.is_relative_to(results) or output in candidates:
            continue
        status = observation(runtime)
        if status in ACTIVE:
            starting.append(f"実験: {html.escape(runtime['experiment_id'])}\n状態: {status}"
                            f"\n段階: {runtime.get('phase', 'unknown')}\n記録: 保存設定作成前")
    progresses = list(candidates.values())
    active = [p for p in progresses if p["runtime_status"] in ACTIVE]
    attention = [p for p in progresses if p not in active and (
        p["runtime_status"] in {"failed", "interrupted"} or p["recorded"] < p["planned"]
        or p["api_failures"] or p["unknown_failures"] or p["duplicates"] or p["unexpected"] or p["pending_write"]
        or p["state"] in {"記録完了・検証待ち", "記録完了・自動検証失敗"})]
    zone = ZoneInfo(timezone)
    sections = [f"実験状況 {datetime.now(zone):%Y-%m-%d %H:%M %Z}",
                f"実行中: {len(active) + len(starting)}件・未完了／要確認: {len(attention)}件"]
    if not active and not starting:
        sections.append("現在、実行中の実験はありません（実行状態の記録に基づく）。")
    sections.extend(message(p, timezone) for p in active)
    sections.extend(starting)
    sections.extend(message(p, timezone) for p in attention)
    completed = [p for p in progresses if p not in active and p not in attention]
    if completed:
        latest = max(completed, key=lambda p: p["last_update"].timestamp() if p["last_update"] else 0)
        sections.append("直近の完了結果\n" + message(latest, timezone))
    if not progresses and not starting:
        sections.append("保存済みの実験はありません。")
    return "\n\n".join(sections)


def send(webhook: str, text: str):
    url = urllib.parse.urlsplit(webhook)
    if (url.scheme != "https" or url.netloc not in {"hooks.slack.com", "hooks.slack-gov.com"}
            or not url.path.startswith("/services/") or url.query or url.fragment):
        raise ValueError("SLACK_WEBHOOK_URL must be a Slack Incoming Webhook URL.")
    request = urllib.request.Request(
        webhook, data=json.dumps({"text": text}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200 or response.read().strip() != b"ok":
                raise RuntimeError("Slack did not acknowledge the notification.")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Slack notification failed (HTTP {exc.code}).") from None
    except (OSError, urllib.error.URLError):
        # Never expose the secret webhook URL through an exception message.
        raise RuntimeError("Slack notification failed (connection/timeout).") from None


def send_to_channel(token: str, channel: str, text: str):
    if not channel or channel[0] not in "CDG" or not channel.isalnum():
        raise ValueError("Use a Slack conversation ID for --channel.")
    request = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps({"channel": channel, "text": text, "unfurl_links": False,
                         "unfurl_media": False}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": "Bearer " + token}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.load(response)
            if response.status != 200 or result.get("ok") is not True:
                # Only known codes are printed; never print arbitrary API data.
                code = result.get("error")
                safe_codes = {"invalid_auth", "not_authed", "token_revoked", "missing_scope",
                              "channel_not_found", "not_in_channel", "rate_limited",
                              "is_archived", "account_inactive", "restricted_action"}
                detail = code if code in safe_codes else "unacknowledged"
                raise RuntimeError(f"Slack notification failed ({detail}).")
            if result.get("channel") != channel:
                raise RuntimeError("Slack response contained an unexpected destination.")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Slack notification failed (HTTP {exc.code}).") from None
    except (OSError, urllib.error.URLError):
        raise RuntimeError("Slack notification failed (connection/timeout).") from None


def send_email(text: str, experiment_id: str):
    required = ("SLACK_EMAIL_TO", "SMTP_HOST", "EMAIL_FROM")
    if any(not os.environ.get(key) for key in required):
        raise RuntimeError("Set SLACK_EMAIL_TO, SMTP_HOST and EMAIL_FROM in .env.")
    recipient = os.environ["SLACK_EMAIL_TO"].strip()
    sender = os.environ["EMAIL_FROM"].strip()
    for address in (recipient, sender):
        if any(char in address for char in "\r\n,;") or Address(addr_spec=address).addr_spec != address:
            raise ValueError("Use a single email address without a display name.")
        if not Address(addr_spec=address).domain:
            raise ValueError("Email addresses must include a domain.")
    security = os.environ.get("SMTP_SECURITY", "starttls").lower()
    if security not in {"starttls", "ssl"}:
        raise RuntimeError("SMTP_SECURITY must be starttls or ssl.")
    port = int(os.environ.get("SMTP_PORT") or ("465" if security == "ssl" else "587"))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid SMTP_PORT.")
    username = os.environ.get("SMTP_USERNAME", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    if bool(username) != bool(password):
        raise RuntimeError("Set both SMTP_USERNAME and SMTP_PASSWORD, or neither for an authorized relay.")
    mail = EmailMessage()
    mail["From"] = sender
    mail["To"] = recipient
    mail["Subject"] = f"実験進捗: {experiment_id}"
    mail["Date"] = formatdate(localtime=True)
    mail["Message-ID"] = make_msgid()
    mail.set_content(text)
    context = ssl.create_default_context()
    try:
        if security == "ssl":
            connection = smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, timeout=30, context=context)
        else:
            connection = smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=30)
        with connection as smtp:
            if security == "starttls":
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
            if username:
                smtp.login(username, password)
            rejected = smtp.send_message(mail, from_addr=sender, to_addrs=[recipient])
            if rejected:
                raise RuntimeError("Progress email rejected by SMTP server.")
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("SMTP authentication failed; check SMTP_USERNAME and SMTP_PASSWORD.") from None
    except (smtplib.SMTPException, OSError):
        # SMTP responses can contain addresses and credentials; never log them.
        raise RuntimeError("Progress email failed (SMTP/TLS/connection); check mail settings.") from None


def deliver(text: str, experiment_id: str, transport: str, channel=None):
    if transport == "email":
        send_email(text, experiment_id)
    elif transport == "slack":
        channel = channel or os.environ.get("SLACK_CHANNEL_ID")
        if channel:
            token = os.environ.get("SLACK_BOT_TOKEN")
            if not token:
                raise RuntimeError("Set SLACK_BOT_TOKEN in the environment or .env.")
            send_to_channel(token, channel, text)
        else:
            webhook = os.environ.get("SLACK_WEBHOOK_URL")
            if not webhook:
                raise RuntimeError("Set SLACK_WEBHOOK_URL in the environment or .env.")
            send(webhook, text)
    else:
        raise ValueError("Unknown delivery transport")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--config")
    source.add_argument("--overview", action="store_true", help="Report running and unresolved experiments across all saved runs")
    parser.add_argument("--latest", action="store_true", help="Follow latest saved run of this experiment, including --new-run")
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument("--channel", help="Slack conversation ID; requires SLACK_BOT_TOKEN instead of webhook")
    parser.add_argument("--transport", choices=("slack", "email"), default="slack")
    parser.add_argument("--dry-run", action="store_true", help="Print notification without sending")
    args = parser.parse_args(argv)
    if args.overview and args.latest:
        parser.error("--latest requires --config")
    if args.transport == "email" and args.channel:
        parser.error("--channel is not used with --transport email; set SLACK_EMAIL_TO in .env.")
    try:
        load_dotenv(ROOT / ".env")
        if args.overview:
            text = overview(args.timezone)
            experiment_id = "全実験の状況"
        else:
            progress = snapshot(resolve_config(ROOT / args.config, args.latest))
            text = message(progress, args.timezone)
            experiment_id = progress["experiment_id"]
        if args.dry_run:
            print(text)
        elif args.transport == "email":
            deliver(text, experiment_id, args.transport)
            print("Progress email accepted by SMTP server; Slack delivery is not yet confirmed.")
        else:
            deliver(text, experiment_id, args.transport, args.channel)
            print("Slack progress notification sent.")
        return 0
    except RuntimeError as exc:
        # RuntimeErrors here are sanitized by the delivery functions above.
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError):
        # Configs and record contents may contain secrets: do not print them.
        print("Progress notification failed; check config, records, timezone and delivery settings.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
