from datetime import datetime, timezone
import json

import pytest

from scripts.notify_reevaluation import notify_once, terminal_message
from scripts.pilot_reevaluation import sha


def terminal_run(tmp_path, *, status="completed", attention=0):
    output=tmp_path/"docs/analysis/reevaluation_full_fixture"
    output.mkdir(parents=True)
    cp=tmp_path/".cache/reevaluation/fixture"; cp.mkdir(parents=True)
    (cp/"driver.lock").touch()
    state={"status":status,"checkpoint_dir":str(cp),"plan_sha256":"identity","planned_rounds":2,
           "completed_rounds":2 if status=="completed" else 1,"updated_at_utc":datetime.now(timezone.utc).isoformat()}
    (output/"run_status.json").write_text(json.dumps(state))
    (output/"manifest.json").write_text(json.dumps({"plan_sha256":"identity"}))
    final=output/"final"; final.mkdir()
    summary={"plan_sha256":"identity","planned_records":2,"complete_records":2,"planned_rounds":2,"scored_rounds":2,
             "missing_rounds":0,"runtime_failures":0,"unclassified_primary_rounds":attention,"shared_initial_judgment_mismatches":0,
             "old_final_successes_complete_subset":1,"new_final_successes":2,"new_success_old_failure":1,"new_failure_old_success":0}
    sanity={"manifest_sha256":"identity","integrity":"ok","duplicate_keys":0}
    (final/"summary.json").write_text(json.dumps(summary)); (final/"sanity_report.json").write_text(json.dumps(sanity))
    (final/"artifact_manifest.json").write_text(json.dumps({"files":{name:{"sha256":sha(final/name)} for name in ("summary.json","sanity_report.json")}}))
    return output


def test_completion_notifies_user_once_and_flags_unconfirmed_slack_delivery(tmp_path):
    output=terminal_run(tmp_path); sent=[]
    sender=lambda text,identity:sent.append((text,identity))
    assert notify_once(output,root=tmp_path,sender=sender)=="smtp_accepted"
    assert notify_once(output,root=tmp_path,sender=sender)=="smtp_accepted"
    assert len(sent)==1 and "全件再評価完了" in sent[0][0]
    ledger=next((tmp_path/".cache/reevaluation_notifications").glob("*.json"))
    assert json.loads(ledger.read_text())["slack_delivery_confirmed"] is False


def test_unknown_classification_is_attention_not_unqualified_success(tmp_path):
    output=terminal_run(tmp_path,attention=1)
    event,text=terminal_message(output,root=tmp_path)
    assert event=="completed" and "分析要確認" in text


def test_runtime_stop_notification_does_not_claim_completion(tmp_path):
    output=terminal_run(tmp_path,status="blocked_runtime_failure")
    sent=[]
    assert notify_once(output,root=tmp_path,sender=lambda text,_:sent.append(text))=="smtp_accepted"
    assert "完了ではありません" in sent[0]


def test_smtp_ambiguity_is_not_automatically_retried(tmp_path):
    output=terminal_run(tmp_path);calls=[]
    def fail(*args):calls.append(1);raise RuntimeError("private SMTP details")
    assert notify_once(output,root=tmp_path,sender=fail)=="delivery_unconfirmed"
    assert notify_once(output,root=tmp_path,sender=fail)=="delivery_unconfirmed"
    assert len(calls)==1
    ledger=next((tmp_path/".cache/reevaluation_notifications").glob("*.json"))
    assert "private SMTP details" not in ledger.read_text()


def test_corrupt_artifacts_cannot_trigger_completion_notification(tmp_path):
    output=terminal_run(tmp_path)
    (output/"final/summary.json").write_text('{}')
    with pytest.raises(ValueError,match="artifact mismatch"):
        terminal_message(output,root=tmp_path)
