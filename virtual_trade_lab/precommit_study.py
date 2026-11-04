"""Recorded-role precommit inspection plus the existing conserved SQLite Market.

No model calls during replay. A model refusal is never replaced with a rule choice.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from .precommit_inspection import Precommit
from .handoff_protocol import Handoff
from .core import Market, Quote, TradeError
from .storage import Store, export

PIN='a3c439bc5d59f98bf121dacd6fc1fba57132bae81aa6867c205ee67c705db2b6'
DEFECT_PIN='d4dda59ed286c8cb3f2d3f6cc2cdf3e7f15b9993689fc9b881e86384b40eea23'
SUPPORTED_PINS={PIN,DEFECT_PIN}
STAGES={'buyer_inspection':('inspect','skip','exit','defer'),
        'seller_inspection':('inspect','skip','exit','defer'),
        'buyer_commit':('accept','decline','defer'),'seller_commit':('accept','decline','defer'),
        'seller_delivery':('deliver','cancel','defer'),'buyer_review':('accept','refund','defer')}


def parse(raw,stage):
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise ValueError('duplicate JSON key')
            d[k]=v
        return d
    x=json.loads(raw,object_pairs_hook=unique)
    if not isinstance(x,dict) or set(x)!={'decision','reason'} or x['decision'] not in STAGES[stage]:
        raise ValueError('invalid response schema')
    if not isinstance(x['reason'],str) or not x['reason'].strip():raise ValueError('reason required')
    return x


def load(root):
    root=Path(root);raw=(root/'protocol.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() not in SUPPORTED_PINS:raise ValueError('frozen protocol changed')
    p=json.loads(raw)
    for name,expected in p['prompt_sha256'].items():
        if hashlib.sha256((root/'prompts'/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('frozen prompt changed')
    records={}
    for name in STAGES:
        path=root/'responses'/f'{name}.txt'
        if not path.exists():
            records[name]=dict(status='missing',parsed=None)
            continue
        text=path.read_text()
        row=dict(raw=text,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        try:row.update(status='valid',parsed=parse(text,name))
        except (ValueError,TypeError):row.update(status='invalid',parsed=None)
        records[name]=row
    if any(path.stem not in STAGES for path in (root/'responses').glob('*.txt')):
        raise ValueError('unknown response file')
    # Verify the delivered prompt text was rendered from frozen templates and prior role evidence.
    choices={actor:records[actor+'_inspection']['parsed']['decision'] for actor in ('buyer','seller')
             if records[actor+'_inspection']['parsed']}
    visible=p['inspection_fixture'] if choices=={'buyer':'inspect','seller':'inspect'} else None
    for stage in ('buyer_commit','seller_commit','seller_delivery','buyer_review'):
        if records[stage]['status']=='missing':continue
        actor=stage.split('_')[0]
        params=dict(own_response=records[actor+'_inspection'].get('raw',''),
                    choices=json.dumps(choices,ensure_ascii=False),
                    visible_report=json.dumps(visible,ensure_ascii=False),
                    delivery_report=json.dumps(p['delivery_fixture'],ensure_ascii=False),
                    seller_dispatch_information=json.dumps(p.get('seller_dispatch_information'),ensure_ascii=False))
        expected=(root/'prompts'/f'{stage}_template.txt').read_text().format(**params)
        actual=root/'prompts'/f'{stage}_actual.txt'
        if not actual.is_file() or actual.read_text()!=expected:
            raise ValueError('actual continuation prompt differs from frozen derivation: '+stage)
    manifest=root/'manifest.json'
    if manifest.exists():
        pins=json.loads(manifest.read_text())['sha256']
        for name,expected in pins.items():
            path=root/name
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError('unsafe manifest path')
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('sealed evidence changed: '+name)
        required={'protocol.json','execution.json'}|{f'responses/{name}.txt' for name,row in records.items() if row['status']!='missing'}
        if not required.issubset(pins):raise ValueError('unsealed response or metadata')
    return p,records


def spec_issues(p):
    d=p['delivery_fixture'];issues=[]
    if p.get('inspection_fixture',{}).get('unit_id') is not None and d.get('unit_id')!=p['inspection_fixture']['unit_id']:
        issues.append('unit_identifier_mismatch')
    if d.get('capacity_ml')!=500:issues.append('capacity_mismatch')
    if d.get('weight_g')!=220:issues.append('listing_weight_mismatch')
    if d.get('leaks') is not False:issues.append('leakproof_failed')
    return issues


def plan(p,records):
    pre=Precommit(p['stock_available'],p['inspection_fixture']); handoff=Handoff()
    commands=[];applied=[];permitted={'buyer_inspection','seller_inspection'}
    def reply(name):return records[name]['parsed']
    for actor in ('buyer','seller'):
        x=reply(actor+'_inspection')
        if x:pre.apply(actor+'_inspection',actor,'inspection_choice',x['decision'])
    if pre.status() in ('ready_inspected','ready_uninspected'):
        permitted.update(('buyer_commit','seller_commit'))
        for actor in ('buyer','seller'):
            x=reply(actor+'_commit')
            if not x:continue
            if pre.status() not in ('ready_inspected','ready_uninspected','awaiting_other_commit'):
                applied.append(dict(stage=actor+'_commit',applied=False,reason='other_actor_closed_or_deferred',intent=x['decision']))
            else:
                pre.apply(actor+'_commit',actor,'commit',x['decision'])
                applied.append(dict(stage=actor+'_commit',applied=True,decision=x['decision']))
    next_step=pre.status()
    if pre.status()=='committed':
        handoff.apply('quote','buyer','accept_quote')
        for actor in ('buyer','seller'):handoff.apply(actor+'_slot',actor,'availability',['today_18'])
        commands=[('quote',dict(source=[dict(id='A',capacity_ml=500,weight_g=220,leaks=False)],
                                criteria=dict(budget=p['initial_balances']['buyer'],max_revisions=0))),('fund',{})]
        permitted.add('seller_delivery'); next_step='awaiting_seller_delivery'
        d=reply('seller_delivery')
        if d and d['decision']=='cancel':
            commands.append(('cancel',{}));handoff.apply('cancel','seller','decline',d['reason']);next_step='seller_cancelled'
        elif d and d['decision']=='deliver':
            commands.append(('deliver',{}));handoff.apply('seller_confirm','seller','confirm',True)
            handoff.apply('inspect','buyer','inspect',0 if spec_issues(p) else 100)
            permitted.add('buyer_review');next_step='awaiting_buyer_review'
            b=reply('buyer_review')
            if b and b['decision']=='refund':
                handoff.apply('buyer_refund','buyer','decline',b['reason']);commands.append(('review',{}));next_step='buyer_refunded'
            elif b and b['decision']=='accept':
                if spec_issues(p) and not p.get('allow_buyer_disclosed_mismatch_acceptance',False):next_step='model_acceptance_conflicts_with_specs_pending'
                else:
                    handoff.apply('buyer_accept','buyer','confirm',True);commands.append(('review',{}));next_step='accepted'
            elif b:next_step='buyer_review_deferred'
        elif d:next_step='seller_delivery_deferred'
    for name,record in records.items():
        if record['status']!='missing' and name not in permitted:
            raise ValueError('unpermitted continuation evidence: '+name)
    return dict(precommit=pre.snapshot(),handoff=handoff.snapshot(),commands=[list(c) for c in commands],
                next_step=next_step,application_log=applied)


class FixtureSeller:
    name='precommit-recorded-fixture-v1'
    def __init__(self,p):self.p=deepcopy(p)
    def quote(self,source):
        if source!=[dict(id='A',capacity_ml=500,weight_g=220,leaks=False)]:
            raise TradeError('unexpected product source')
        return Quote(self.p['price'],self.p['delivery_cost'],self.name)
    def fulfill(self,source,attempt,mode):return [deepcopy(self.p['delivery_fixture'])]


class RecordedBuyer:
    def __init__(self,p,records):self.p,self.records=p,records
    def assess(self,source,result,criteria):
        if result!=[self.p['delivery_fixture']]:raise TradeError('delivery differs from frozen fixture')
        x=self.records['buyer_review']['parsed']
        if not x or x['decision']=='defer':raise TradeError('no recorded buyer review authorization')
        if x['decision']=='refund':return ['recorded buyer requested preacceptance refund']
        if spec_issues(self.p) and not self.p.get('allow_buyer_disclosed_mismatch_acceptance',False):
            raise TradeError('model acceptance conflicts with independent specification check')
        return []


class StudyStore(Store):
    SCHEMA='precommit-model-fixture/v1/'+PIN
    def __init__(self,path,p,records):
        self.p,self.records=p,records
        self.SCHEMA='precommit-model-fixture/v2/'+hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()
        # Preserve the already-tested original study schema; new study gets a distinct binding.
        if p.get('schema')=='precommit-model-study/v1':self.SCHEMA=type(self).SCHEMA
        super().__init__(path)
    def _new_market(self):
        return Market(FixtureSeller(self.p),RecordedBuyer(self.p,self.records),
                      buyer_credits=self.p['initial_balances']['buyer'],seller_credits=self.p['initial_balances']['seller'])


def run(root,db):
    p,records=load(root);expected_plan=plan(p,records);commands=expected_plan['commands']
    store=StudyStore(db,p,records);state=store.state();expected=store._new_market()
    if not 0<=state['revision']<=len(commands):raise ValueError('unexpected stored command count')
    for action,payload in commands[:state['revision']]:expected.execute(action,'A','A:'+action,**payload)
    if {k:state[k] for k in export(expected)}!=export(expected):raise ValueError('stored history not canonical evidence prefix')
    for action,payload in commands:
        request=dict(epoch=state['epoch'],expected_revision=state['revision'],key='A:'+action,
                     order_id='A',action=action,payload=payload)
        state=StudyStore(db,p,records).command(request)
        if StudyStore(db,p,records).command(request)!=state:raise RuntimeError('restart retry changed state')
        if sum(state['balances'].values())!=130:raise RuntimeError('conservation failure')
    expected=store._new_market()
    for action,payload in commands:expected.execute(action,'A','A:'+action,**payload)
    if {k:state[k] for k in export(expected)}!=export(expected) or state['revision']!=len(commands):
        raise RuntimeError('final state not canonical')
    result=dict(schema='precommit-model-result/v1',protocol_sha256=hashlib.sha256((Path(root)/'protocol.json').read_bytes()).hexdigest(),source=('recorded conversation-model intent; original deterministic execution' if (Path(root)/'manifest.json').exists() else 'unsealed recorded inputs; original deterministic execution'),
                records=records,plan=expected_plan,state=export(expected),command_count=state['revision'],
                recorded_response_count=sum(x['status']!='missing' for x in records.values()),
                replay_identical=True,real_payments=0,real_revenue=0,
                limits='One synthetic dyad, not humans or causal comparison. Fixture checks are assumptions, not real inspection. No new model calls during replay. Unit acquisition cost omitted from transfer boundary; do not infer profit.')

    if p.get('schema')=='defect-refund-model-study/v1':
        buyer=records['buyer_review']['parsed']
        result['defect_assessment']=dict(specification_issues=spec_issues(p),
            fixture_conforms=not bool(spec_issues(p)),
            buyer_review=buyer,
            mismatch_waived_by_buyer=bool(buyer and buyer['decision']=='accept' and spec_issues(p)),
            refund_authority='seller preauthorized full preacceptance refund at commitment; no later seller approval invented')
    return result


def main():
    import argparse
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--study',type=Path,required=True)
    a.add_argument('--db',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    args=a.parse_args();args.output.write_text(json.dumps(run(args.study,args.db),ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
