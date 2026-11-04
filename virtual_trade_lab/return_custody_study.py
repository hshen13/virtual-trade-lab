"""Recorded model return choices + explicitly scripted carrier evidence and conserved ledger."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from .return_custody import ReturnProtocol
from .core import Market,Quote,TradeError
from .storage import Store,export

PIN='efc7656c21b216deb047de6cf9436572c3eee858a8c78ab0da68d0cd6cdb208c'
CHOICES={'buyer_request':('request_refund','keep','defer'),
         'seller_review':('approve_return','request_evidence','deny','defer'),
         'buyer_shipping':('ship','keep','defer')}


def parse(raw,stage):
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise ValueError('duplicate JSON key')
            d[k]=v
        return d
    x=json.loads(raw,object_pairs_hook=unique)
    if not isinstance(x,dict) or set(x)!={'decision','reason'} or x['decision'] not in CHOICES[stage] or not isinstance(x['reason'],str) or not x['reason'].strip():raise ValueError('invalid role response')
    return x


def load(root):
    root=Path(root);raw=(root/'protocol.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PIN:raise ValueError('frozen protocol changed')
    p=json.loads(raw)
    for name,sha in p['prompt_sha256'].items():
        if hashlib.sha256((root/'prompts'/name).read_bytes()).hexdigest()!=sha:raise ValueError('frozen prompt changed')
    records={}
    for stage in CHOICES:
        path=root/'responses'/f'{stage}.txt'
        if not path.exists():records[stage]={'status':'missing','parsed':None};continue
        row={'raw':path.read_text(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        try:row.update(status='valid',parsed=parse(row['raw'],stage))
        except (ValueError,TypeError):row.update(status='invalid',parsed=None)
        records[stage]=row
    if any(path.stem not in CHOICES for path in (root/'responses').glob('*.txt')):
        raise ValueError('unexpected response file; do not silently exclude evidence')
    for stage in ('seller_review','buyer_shipping'):
        if records[stage]['status']=='missing':continue
        text=(root/'prompts'/f'{stage}_template.txt').read_text().format(
            buyer_request=records['buyer_request'].get('raw',''),
            seller_review=records['seller_review'].get('raw',''),
            evidence=json.dumps(p['evidence'],ensure_ascii=False))
        if (root/'prompts'/f'{stage}_actual.txt').read_text()!=text:raise ValueError('actual prompt derivation mismatch')
    manifest=root/'manifest.json'
    if manifest.exists():
        pins=json.loads(manifest.read_text())['sha256']
        required={'protocol.json','execution.json'}|{f'responses/{k}.txt' for k,v in records.items() if v['status']!='missing'}
        if not required.issubset(pins):raise ValueError('unsealed evidence')
        for name,sha in pins.items():
            if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('unsafe evidence path')
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise ValueError('sealed evidence changed')
    return p,records


def plan(p,records,tick):
    if type(tick) is not int or tick not in range(4):raise ValueError('observation tick must be0..3')
    state=ReturnProtocol();allowed={'buyer_request'}
    def get(s):return records[s]['parsed']
    b=get('buyer_request')
    if b:state.apply('buyer_request','buyer','request',b['decision'])
    if b and b['decision']=='request_refund':
        allowed.add('seller_review');s=get('seller_review')
        if s:state.apply('seller_review','seller','review',s['decision'])
        if s and s['decision']=='approve_return':
            allowed.add('buyer_shipping');ship=get('buyer_shipping')
            if ship:state.apply('buyer_shipping','buyer','shipping',ship['decision'])
    for key,row in records.items():
        if row['status']!='missing' and key not in allowed:raise ValueError('unpermitted later role evidence')
    if state.shipping=='ship' and tick>=p['shipping_tick']:
        state.apply('carrier_handoff','carrier','handoff',dict(order=p['order_id'],label=p['return_label'],unit=p['delivery']['unit_id'],tick=p['shipping_tick']))
    if state.handoff and tick>=p['receipt_tick']:
        state.apply('carrier_receipt','carrier','receipt',dict(order=p['order_id'],label=p['return_label'],unit=p['delivery']['unit_id'],tick=p['receipt_tick']))
    cmds=[['quote',{'source':[{'id':'A'}],'criteria':{'budget':90,'max_revisions':0}}],['fund',{}],['deliver',{}]]
    if state.handoff:cmds.append(['return_postage',{}])
    if state.receipt or state.status()=='buyer_keeps':cmds.append(['review',{}])
    return state,cmds


class Service:
    name='return-custody-fixture/v1'
    def __init__(self,p):self.p=p
    def quote(self,source):
        if source!=[{'id':'A'}]:raise TradeError('unexpected source')
        return Quote(self.p['price'],self.p['delivery_fee'],self.name)
    def fulfill(self,source,attempt,mode):return [deepcopy(self.p['delivery'])]


class Buyer:
    def __init__(self,state):self.state=state
    def assess(self,source,result,criteria):
        if not isinstance(result,list) or len(result)!=1 or result[0].get('unit_id')!=self.state.unit:
            raise TradeError('returned evidence does not match delivered unit')
        if self.state.receipt:return ['recorded refund request and matching returned-item receipt']
        if self.state.status()=='buyer_keeps':return []
        raise TradeError('no authorized settlement')


class ReturnMarket(Market):
    def _dispatch(self,action,order_id,payload):
        if order_id!=self.evaluator.state.order:raise TradeError('custody evidence belongs to another order')
        if action in ('return_postage','review'):
            result=self.order(order_id).result
            if not isinstance(result,list) or len(result)!=1 or result[0].get('unit_id')!=self.evaluator.state.unit:
                raise TradeError('custody evidence does not match delivered unit')
        if action=='return_postage':
            order=self.order(order_id)
            if payload or order.state!='delivered' or not self.evaluator.state.handoff:raise TradeError('return fee requires consented handoff')
            if any(j['order']==order_id and j['reason']=='return_postage' for j in self._journal):raise TradeError('return postage already charged')
            self._transfer('seller','provider',4,order_id,'return_postage')
            return
        if action=='review' and self.evaluator.state.receipt and not any(j['order']==order_id and j['reason']=='return_postage' for j in self._journal):
            raise TradeError('refund requires recorded return postage and receipt')
        return super()._dispatch(action,order_id,payload)


class ReturnStore(Store):
    SCHEMA='return-custody/v1/'+PIN
    def __init__(self,path,p,state):self.p,self.return_state=p,state;super().__init__(path)
    def _new_market(self):return ReturnMarket(Service(self.p),Buyer(self.return_state),buyer_credits=90,seller_credits=40)


def run(root,db,tick=3):
    p,records=load(root);state,commands=plan(p,records,tick)
    store=ReturnStore(db,p,state);stored=store.state();expected=store._new_market()
    if not 0<=stored['revision']<=len(commands):raise ValueError('cannot roll back later stored evidence')
    for a,payload in commands[:stored['revision']]:expected.execute(a,p['order_id'],a,**payload)
    if {k:stored[k] for k in export(expected)}!=export(expected):raise ValueError('noncanonical stored history')
    for a,payload in commands:
        req=dict(epoch=stored['epoch'],expected_revision=stored['revision'],key=a,order_id=p['order_id'],action=a,payload=payload)
        stored=ReturnStore(db,p,state).command(req)
        if ReturnStore(db,p,state).command(req)!=stored:raise RuntimeError('restart replay changed state')
    expected=store._new_market()
    for a,payload in commands:expected.execute(a,p['order_id'],a,**payload)
    if {k:stored[k] for k in export(expected)}!=export(expected):raise RuntimeError('final ledger mismatch')
    replay=ReturnProtocol.replay(state.events,state.configuration())
    for e in state.events:
        if replay.apply(**e):raise RuntimeError('duplicate custody event')
    fees=sum(j['credits'] for j in expected.journal if j['reason'] in ('compute','return_postage'))
    return dict(schema='return-custody-result/v1',protocol_sha256=PIN,observation_tick=tick,
                records=records,return_protocol=state.snapshot(),market=export(expected),command_count=stored['revision'],
                seeded_commands=['quote','fund','deliver'],model_calls_recorded=sum(r['status']!='missing' for r in records.values()),
                carrier_source='scripted matched handoff/receipt fixtures; not model or real shipping',
                total_simulated_fees=fees,conserved_total=sum(expected.balances.values()),
                replay_identical=replay.snapshot()==state.snapshot(),real_payments=0,
                limits='Independent seeded postdelivery case; prior purchase not model-driven in this experiment. Model request/review/shipping separate from scripted carrier evidence. No physical return, real users, profit or empirical timing claim; acquisition cost excluded.')


def main():
    import argparse
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--study',type=Path,required=True);a.add_argument('--db',type=Path,required=True);a.add_argument('--tick',type=int,default=3);a.add_argument('--output',type=Path,required=True)
    x=a.parse_args();x.output.write_text(json.dumps(run(x.study,x.db,x.tick),ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
