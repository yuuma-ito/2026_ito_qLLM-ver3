import pytest
from scripts.measurement_ban_report import classify_path
from scripts.run_measurement_ban_job import notify_once


@pytest.mark.parametrize('condition',['execution_feedback','self_debugging','independent_4','self_refine'])
def test_invalid_success_with_budget_requires_a_real_continuation(condition):
    r=classify_path(condition,[(0,False,False,'a'),(1,True,False,'b')])
    assert r['requires_new_generation'] and r['next_generation_round']==2
    assert r['remaining_request_upper_bound']==2 and not r['confirmed_success']
    assert r['diagnostic_changes']==(condition in ['execution_feedback','self_debugging'])


@pytest.mark.parametrize('condition',['baseline','preventive_spec'])
def test_single_generation_budget_is_not_extended(condition):
    r=classify_path(condition,[(0,True,False,'x')])
    assert not r['requires_new_generation'] and not r['confirmed_success']


def test_last_round_failure_does_not_trigger_extra_requests():
    r=classify_path('self_debugging',[(3,True,False,'x')])
    assert not r['requires_new_generation'] and r['status']=='failure_at_budget'
    assert r['diagnostic_changes']


def test_R_can_use_only_verified_existing_suffix():
    r=classify_path('self_refine',[(0,True,False,'x')],[(1,False,False,'y'),(2,True,True,'z')])
    assert r['confirmed_success'] and not r['requires_new_generation']
    assert r['reused_saved_R_rounds']==2
    with pytest.raises(ValueError):classify_path('self_refine',[(0,True,False,'x')],[(2,True,True,'z')])


def test_F_D_suffix_after_changed_feedback_is_not_reused():
    for condition in ['execution_feedback','self_debugging']:
        r=classify_path(condition,[(0,True,False,'x')],[(1,True,True,'y')])
        assert not r['confirmed_success'] and r['requires_new_generation']


def test_notification_is_once_and_ambiguous_delivery_is_not_retried(tmp_path):
    calls=[]
    def sender(text):calls.append(text)
    assert notify_once('ok','safe report',private=tmp_path,sender=sender)=='smtp_accepted'
    assert notify_once('ok','safe report',private=tmp_path,sender=sender)=='smtp_accepted'
    assert len(calls)==1
    def broken(text):calls.append(text);raise RuntimeError('private transport response')
    assert notify_once('fail','safe report',private=tmp_path,sender=broken)=='delivery_unconfirmed'
    assert notify_once('fail','safe report',private=tmp_path,sender=broken)=='delivery_unconfirmed'
    assert len(calls)==2
    assert 'private transport response' not in (tmp_path/'notification_fail.json').read_text()
