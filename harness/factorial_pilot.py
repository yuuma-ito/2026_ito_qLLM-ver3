"""New exploratory A/B/C/D factors; separate from historical interventions."""
from collections import Counter,defaultdict
from copy import deepcopy
import ast
import math
import random

from harness.diagnostic_policy import DIAGNOSTIC_VERSION,diagnose
from harness.independent_4 import digest,code_hash,levels,seed_for
from harness.llm_clients import SYSTEM_PROMPT,OpenAICompatClient
from scripts.reevaluation_impact_audit import event
from tasks import get_task

SCHEMA='factorial_pilot_v1'
CONDITIONS=('A','B','C','D')
SAMPLE_SEED=20261105
SEED_NAMESPACE='factorial_pilot_v1_20261105'
SETTINGS={'temperature':.7,'max_tokens':1024,'timeout_sec':600,'parallel_requests':1,'reasoning_effort':'none'}
HOST='http://127.0.0.1:11435'
ORDERS=(('A','B','D','C'),('B','C','A','D'),('C','D','B','A'),('D','A','C','B'))
FOOTER='課題仕様を満たす完全な Python コードを、単一の ```python ``` コードブロックだけで出力してください。'
EXPLANATION=('次の順序で検討してください。\n'
             '1. 前回コードの動作を説明する。\n'
             '2. 課題仕様と診断を照合し、失敗原因を分析する。\n'
             '3. 分析を踏まえて完全なコードを作成する。\n'
             '説明と原因分析は、出力コードブロック先頭の Python コメント（# DEBUG: ...）として3〜6行にまとめてください。')
TEMPLATES={
    'A':'{task}\n\n'+FOOTER,
    'B':'{task}\n\n--- 前回のコード ---\n```python\n{code}\n```\n\n'+FOOTER,
    'C':'{task}\n\n--- 前回のコード ---\n```python\n{code}\n```\n\n--- 実行診断 ---\n{diagnostic}\n\n'+FOOTER,
    'D':'{task}\n\n--- 前回のコード ---\n```python\n{code}\n```\n\n--- 実行診断 ---\n{diagnostic}\n\n'+EXPLANATION+'\n\n'+FOOTER,
}


def build_prompt(condition,task,previous):
    if condition not in CONDITIONS:raise ValueError('unknown factor condition')
    diagnostic=diagnose(task,event(previous['primary'])) if condition in ['C','D'] else ''
    return TEMPLATES[condition].format(task=task.prompt_text,code=previous['code'] if condition!='A' else '',diagnostic=diagnostic)


def identity(case):return case['model_spec'],case['task_id'],case['base_seed']


def sample_cases(cases,n=100,seed=SAMPLE_SEED):
    """Only model/error/identity enter selection; historical outcomes are ignored."""
    cells=defaultdict(list)
    if len({c['case_id'] for c in cases})!=len(cases):raise ValueError('duplicate cohort member')
    for c in cases:cells[c['model_spec'],c['initial_error']].append(c)
    if not len(cells)<=n<=len(cases):raise ValueError('sample cannot cover nonempty strata')
    remaining=n-len(cells);capacity=len(cases)-len(cells)
    ideal={k:(len(v)-1)*remaining/capacity if capacity else 0 for k,v in cells.items()}
    quota={k:1+math.floor(v) for k,v in ideal.items()}
    for k in sorted(cells,key=lambda k:(-(ideal[k]%1),k))[:n-sum(quota.values())]:quota[k]+=1
    selected=[]
    for key,members in sorted(cells.items()):
        members=sorted(members,key=lambda c:c['case_id'])
        rng=random.Random(int(digest([seed,'model_error',key]),16))
        selected.extend(rng.sample(members,quota[key]))
    # Repair task coverage only, within the same fixed model/error quota.
    selected_ids={c['case_id'] for c in selected};task_counts=Counter(c['task_id'] for c in selected)
    missing=sorted({c['task_id'] for c in cases}-set(task_counts))
    for task in missing:
        candidates=sorted((c for c in cases if c['task_id']==task and c['case_id'] not in selected_ids),key=lambda c:digest([seed,'task_coverage',c['case_id']]))
        replacement=None
        for candidate in candidates:
            options=[c for c in selected if (c['model_spec'],c['initial_error'])==(candidate['model_spec'],candidate['initial_error']) and task_counts[c['task_id']]>1]
            if options:
                replacement=candidate,max(options,key=lambda c:digest([seed,'coverage_remove',c['case_id']]))
                break
        if replacement is None:raise ValueError('task coverage impossible without changing the prespecified strata')
        candidate,removed=replacement;selected.remove(removed);selected.append(candidate)
        selected_ids.remove(removed['case_id']);selected_ids.add(candidate['case_id'])
        task_counts[removed['task_id']]-=1;task_counts[candidate['task_id']]+=1
    return sorted(selected,key=lambda c:(digest([seed,'model_block',c['model_spec']]),digest([seed,'case_order',c['case_id']])))


def paired_seed(case,round_index,namespace=SEED_NAMESPACE):
    return seed_for(*identity(case),round_index,namespace)


def schedule(cases):
    return [{'round':r,'case_id':c['case_id'],'condition':condition,'nominal_position':position+1,
             'case_index':i,'seed':paired_seed(c,r)}
            for r in [1,2,3] for i,c in enumerate(cases)
            for position,condition in enumerate(ORDERS[(i+r-1)%4])]


def wire_body(model,prompt,seed):
    return {'model':model.removeprefix('ollama:'),'messages':[{'role':'system','content':SYSTEM_PROMPT},{'role':'user','content':prompt}],
            'temperature':.7,'max_tokens':1024,'reasoning_effort':'none','seed':seed}


class RecordedClient(OpenAICompatClient):
    """Same seeded API settings; the exact body is also saved by the runner."""
    def _create(self,user_prompt,temperature,seed):
        if temperature!=.7:raise ValueError('temperature drift')
        return self._client.chat.completions.create(**wire_body(self.model_id,user_prompt,seed))


def ast_hash(code):
    try:return code_hash(ast.dump(ast.parse(code),include_attributes=False))
    except (SyntaxError,ValueError,TypeError,RecursionError):return None


def features(previous,code,primary,history):
    before=ast_hash(previous['code']);after=ast_hash(code)
    comparable=before is not None and after is not None
    old_asts=[ast_hash(a['code']) for a in history]
    return {'ast_sha256':after,'previous_ast_sha256':before,'ast_pair_comparable':comparable,
            'ast_changed_from_previous':comparable and before!=after,
            'same_failed_ast_as_previous':comparable and before==after and not primary['L3'] and not previous['primary']['L3'],
            'any_prior_ast_repeat':after is not None and after in [h for h in old_asts if h is not None],
            'exact_previous_repeat':code_hash(previous['code'])==code_hash(code),
            'any_prior_exact_repeat':code_hash(code) in [code_hash(a['code']) for a in history],
            'error_before':previous['primary']['error_category'],'error_after':primary['error_category'],
            'debug_comment_lines':sum(line.lstrip().startswith('# DEBUG:') for line in code.splitlines())}


def validate_response(response,model):
    if response['response']['model']!=model.removeprefix('ollama:'):raise ValueError('model response mismatch')
    for key in ['tokens_in','tokens_out']:
        if type(response[key]) is not int or response[key]<0:raise ValueError('missing/invalid usage')
    usage=response['response'].get('usage',{})
    if usage.get('prompt_tokens')!=response['tokens_in'] or usage.get('completion_tokens')!=response['tokens_out']:
        raise ValueError('response usage mismatch')
    if response['tokens_out']>1024 or not response.get('finish_reason'):
        raise ValueError('token limit or finish reason invalid')
    if response['response']['choices'][0]['finish_reason']!=response['finish_reason']:
        raise ValueError('finish reason mismatch')
    if not math.isfinite(response['generation_seconds']) or response['generation_seconds']<0:raise ValueError('invalid elapsed time')


def validate_history(case,condition,history,records,*,complete=False):
    if not history or digest(history[0])!=digest(case['initial']):raise ValueError('shared initial drift')
    if len(history)!=len(records)+1 or len(records)>3:raise ValueError('history size mismatch')
    for i,(a,r) in enumerate(zip(history[1:],records),1):
        if history[i-1]['primary']['L3']:raise ValueError('continued after success')
        levels(a['primary'])
        prompt=build_prompt(condition,get_task(case['task_id']),history[i-1])
        if r['round']!=i or r['seed']!=paired_seed(case,i) or r['case_id']!=case['case_id'] or r['condition']!=condition:
            raise ValueError('round/seed/condition drift')
        if r['input_prompt_sha256']!=code_hash(prompt) or r['code_sha256']!=code_hash(a['code']) or r['initial_fingerprint']!=digest(case['initial']):
            raise ValueError('prompt/code/initial drift')
        if r['primary']!=a['primary']:raise ValueError('history evaluation mismatch')
        if r['features']!=features(history[i-1],a['code'],a['primary'],history[:i]):raise ValueError('structure feature mismatch')
    if complete and not history[-1]['primary']['L3'] and len(records)!=3:raise ValueError('unsuccessful path incomplete')
