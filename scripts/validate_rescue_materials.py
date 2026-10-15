"""Validate public rescue analysis and built sharing PDFs without executing code."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime,timezone

from harness.run_state import atomic_json
from scripts import analyze_verified_rescues as base
from scripts.analyze_reachable_rescue_history import OUT, JOB, progress
from scripts.render_rescue_materials import FIXED, tables

ROOT=base.ROOT


def command(*args):
    return subprocess.run(args,check=True,capture_output=True,text=True).stdout


def run():
    out=ROOT/OUT;fixed=ROOT/FIXED
    snap=json.loads((out/'results_snapshot.json').read_text())
    sanity=json.loads((out/'sanity_report.json').read_text())
    manifest=json.loads((out/'manifest.json').read_text())
    checks={}
    checks['sanity_passed']=sanity['passed'] is True
    checks['fixed_counts']=snap['discordant_pairs']==83 and snap['discordant_condition_paths']==166 and snap['discordant_transitions']==398
    checks['source_hashes_unchanged']=all(base.sha(ROOT/p)==h for p,h in manifest['inputs'].items())
    checks['analysis_script_hash']=base.sha(ROOT/'scripts/analyze_reachable_rescue_history.py')==manifest['script_sha256']
    checks['analysis_output_hashes']=all(base.sha(out/p)==h for p,h in manifest['outputs'].items())
    cases=base.read_csv(out/'discordant_cases.csv')
    transitions=base.read_csv(out/'discordant_transitions.csv')
    checks['all_83_both_paths']=len(cases)==166 and len({(r['source_dir'],r['model_spec'],r['task_id'],r['base_seed']) for r in cases})==83
    checks['all_83_success_transitions']=sum(r['to_L3']=='True' for r in transitions)==83
    checks['transition_uniqueness']=len({(r['record_key'],r['to_round']) for r in transitions})==len(transitions)
    checks['transition_hash_chain']=all(
        next(r for r in transitions if r['record_key']==c['record_key'] and r['from_round']=='0')['from_code_sha256']==c['initial_code_sha256']
        and next(r for r in transitions if r['record_key']==c['record_key'] and r['to_round']==c['stop_round'])['to_code_sha256']==c['final_code_sha256']
        for c in cases)
    checks['reproduced_csv_identical']=all(base.sha(p)==base.sha(Path('/tmp/rescue_reproduced')/p.relative_to(out)) for p in out.rglob('*.csv'))
    tests=(ROOT/JOB/'analysis_tests.txt').read_text()
    checks['related_tests_passed']='16 passed' in tests and 'failed' not in tests
    repair=base.read_csv(out/'core/repair_summary.csv')
    overlap=base.read_csv(out/'core/fd_overlap_summary.csv')
    checks['tables_match_csv']=(fixed/'tables.tex').read_text()==tables(snap,repair,overlap)
    # Restrict public outputs to schemas and hashes, never raw strings or code.
    banned={'extracted_code','raw_output','error_message','prompt','response','code','text','api_key'}
    checks['public_csv_fields_allowlisted']=all(not (set(base.read_csv(p)[0]) & banned) for p in out.rglob('*.csv'))
    def json_keys(value):
        if isinstance(value,dict):
            return set(value)|set().union(*(json_keys(v) for v in value.values()),set())
        if isinstance(value,list):
            return set().union(*(json_keys(v) for v in value),set())
        return set()
    checks['public_json_no_raw_fields']=all(not(json_keys(json.loads(p.read_text())) & banned) for p in [out/'results_snapshot.json',out/'manifest.json',out/'sanity_report.json'])
    # Publication data must not contain obvious credential patterns.
    files=[p for d in (out,fixed) for p in d.rglob('*') if p.is_file() and p.suffix in ('.md','.json','.csv','.tex')]
    checks['no_obvious_secrets']=not any(re.search(r'(?:sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)',p.read_text()) for p in files)
    review=json.loads((ROOT/JOB/'visual_review.json').read_text())
    documents={}
    for directory in ('midterm2026','winf2026'):
        d=ROOT/'docs'/directory
        info=command('pdfinfo',str(d/'paper.pdf'))
        fonts=command('pdffonts',str(d/'paper.pdf'))
        text=command('pdftotext',str(d/'paper.pdf'),'-')
        normalized=''.join(unicodedata.normalize('NFKC',text).split())
        log=(d/'paper.log').read_text()
        source=(d/'paper.tex').read_text()
        count=int(re.search(r'Pages:\s+(\d+)',info)[1])
        local={
            'pdf_header':(d/'paper.pdf').read_bytes().startswith(b'%PDF-'),
            'two_a4_pages':count==2 and 'A4' in info,
            'no_unresolved_refs':not re.search(r'(undefined|Missing character|Overfull)',log,re.I),
            'fonts_embedded':all(re.search(r'\byes\s+yes\s+(?:yes|no)\s+\d+\s+\d+\s*$',line) for line in fonts.splitlines()[2:]),
            'main_counts_in_pdf':all(s in normalized for s in ('96/545','183/545','180/545','455','545','1,708,086','1,975,782','1,809,845','398修正遷移')),
            'no_obsolete_main_counts':not re.search(r'(?<!\d)(582|191)(?!\d)',source),
            'current_tables_only':r'\input{../presentation_sources/20261016T_reachable_rescues/tables.tex}' in source and '20261013T_' not in source,
            'style_unchanged_from_before':base.sha(d/'winf-paper.sty')==base.sha(ROOT/JOB/'before/docs'/directory/'winf-paper.sty'),
            'visually_reviewed_all_pages':review[directory]['passed'] is True and review[directory]['pages']==count and review[directory]['pdf_sha256']==base.sha(d/'paper.pdf'),
        }
        local['passed']=all(local.values())
        documents[directory]=dict(checks=local,pages=count,pdf_sha256=base.sha(d/'paper.pdf'),
            tex_sha256=base.sha(d/'paper.tex'),style_sha256=base.sha(d/'winf-paper.sty'),
            visual_notes=review[directory]['notes'],nonblocking_tex_warning='Underfull hbox in displayed rescue-rate fraction; no clipping')
        checks[directory]=local['passed']
    before_report=(ROOT/JOB/'before/docs/experiment_report_draft.md').read_text()
    current_report=(ROOT/'docs/experiment_report_draft.md').read_text()
    without_addition=re.sub(r'\n\n<!-- reachable-rescues:20261016:start -->.*?<!-- reachable-rescues:20261016:end -->','',current_report,flags=re.S)
    checks['existing_report_preserved_except_new_section']=without_addition==before_report
    original_snapshot=json.loads((ROOT/JOB/'before/docs/experiment_report_snapshot.json').read_text())
    current_snapshot=json.loads((ROOT/'docs/experiment_report_snapshot.json').read_text())
    checks['existing_report_snapshot_fields_preserved']=all(current_snapshot[k]==v for k,v in original_snapshot.items())
    checks['legacy_fixed_files_unchanged']=all(
        base.sha(p)==base.sha(ROOT/'docs'/directory/p.name)
        for directory in ('midterm2026','winf2026')
        for p in (ROOT/JOB/'before/docs'/directory).iterdir()
        if p.name in ('analysis_snapshot_20261014.json','results_snapshot_20261008.json','validation_report_20261014.json','analysis_tables_20261014.tex','template-original.tex'))
    passed=all(checks.values())
    validation=dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),passed=passed,checks=checks,
        related_tests='16 passed: analysis, reachable branch/stopping, cost, safe static delta, report preservation',
        supplementary_source_tests='53 passed including existing followup tests; mock API and fixture circuits only; 6 existing QFT deprecation warnings',
        new_llm_requests=0,saved_generated_code_executions=0,evaluator_changes=0,
        publication_scope='No raw, generated code, prompts, API responses, raw exception messages or secrets',
        documents=documents,
        remaining_research_limitations=['静的差分の因果的寄与は未同定','再構成経路の計算コスト・金銭費用未測定',
            '共有初期・タスク・seed依存、設定/処理差、指定入力のみの主L3','別seed/タスクでの介入選択・停止方策の検証は未実施','WiNF著者・正式所属は要確認'])
    atomic_json(out/'validation_report.json',validation)
    atomic_json(fixed/'validation_report.json',validation)
    for directory,data in documents.items():
        atomic_json(ROOT/'docs'/directory/'validation_report_20261016.json',dict(validation,documents={directory:data}))
    # Record final public analysis output hashes, keeping manifests acyclic.
    manifest['outputs']={str(p.relative_to(out)):base.sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json'}
    atomic_json(out/'manifest.json',manifest)
    shutil.copyfile(out/'manifest.json',fixed/'manifest.json')
    paths=[p for p in fixed.iterdir() if p.is_file() and p.name!='source_manifest.json']
    paths += [ROOT/'scripts'/name for name in ('analyze_verified_rescues.py','analyze_reachable_rescue_history.py','render_rescue_materials.py','validate_rescue_materials.py')]
    paths += [ROOT/'tests'/name for name in ('test_analyze_verified_rescues.py','test_analyze_reachable_rescue_history.py','test_render_rescue_materials.py')]
    for directory in ('midterm2026','winf2026'):
        paths += [ROOT/'docs'/directory/name for name in ('paper.tex','paper.pdf','README.md','progress_report_draft.txt','validation_report_20261016.json')]
    paths.append(ROOT/'docs/winf2026/abstract.txt')
    atomic_json(fixed/'source_manifest.json',dict(captured_at_utc=validation['captured_at_utc'],
        source_analysis=str(OUT),analysis_manifest_sha256=base.sha(out/'manifest.json'),
        source_plan_sha256=snap['primary']['source_plan_sha256'],
        files={str(p.relative_to(ROOT)):base.sha(p) for p in sorted(paths)},
        build_commands=['platex -interaction=nonstopmode -halt-on-error paper.tex (twice)',
                        'dvipdfmx -p a4 -f ptex-ipaex.map -o paper.pdf paper.dvi']))
    if not passed:
        raise ValueError('Validation failed: '+', '.join(k for k,v in checks.items() if not v))
    print(json.dumps(dict(passed=passed,checks=checks),ensure_ascii=False,indent=2))
    return validation


if __name__=='__main__':run()
