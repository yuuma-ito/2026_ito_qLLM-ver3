import pytest
from scripts.summarize_generation_limits import summarize


def test_conditions_and_denominators_remain_separate():
    rows=[dict(record_key='f',round=1,condition_id='F',api_finish_reason='length'),
          dict(record_key='f',round=2,condition_id='F',api_finish_reason='stop'),
          dict(record_key='d',round=1,condition_id='D',api_finish_reason='stop')]
    result=summarize(rows)
    assert result['total_generations']==3
    by={r['condition_id']:r for r in result['conditions']}
    assert by['F']['length_rate']==.5 and by['D']['length_rate']==0
    assert not result['causal_effect_identified']


def test_duplicate_and_missing_reason_are_not_silently_dropped():
    r=dict(record_key='f',round=1,condition_id='F',api_finish_reason='stop')
    with pytest.raises(ValueError,match='duplicate'):summarize([r,r])
    with pytest.raises(ValueError,match='missing'):summarize([{**r,'api_finish_reason':''}])
