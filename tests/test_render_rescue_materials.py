import json
from scripts import render_rescue_materials as render


def test_report_update_preserves_user_text_auto_blocks_and_sources(tmp_path,monkeypatch):
    monkeypatch.setattr(render,'ROOT',tmp_path)
    docs=tmp_path/'docs';docs.mkdir()
    p=docs/'experiment_report_draft.md'
    auto='<!-- auto:status:start -->\n既存の表\n<!-- auto:status:end -->'
    original='# 手書きの目的\n<!-- intervention-rescues:20261015:end -->\n'+auto+'\n既存考察\n'
    p.write_text(original)
    sp=docs/'experiment_report_snapshot.json';sp.write_text(json.dumps({'runs':[{'source':'existing'}],'manual':'維持'}))
    render.refresh_report({'captured_at_utc':'fixed'})
    once=p.read_text()
    render.refresh_report({'captured_at_utc':'fixed'})
    assert p.read_text()==once
    assert auto in once and once.startswith('# 手書きの目的\n') and once.endswith('既存考察\n')
    assert once.count('<!-- reachable-rescues:20261016:start -->')==1
    d=json.loads(sp.read_text())
    assert d['runs']==[{'source':'existing'}] and d['manual']=='維持'
    assert 'primary_reachable_history' in d
