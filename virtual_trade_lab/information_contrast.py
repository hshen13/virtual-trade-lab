"""Read-only replay of a small, balanced-order fictional information comparison."""
import hashlib
from html import escape
import json
from pathlib import Path
from .channel_journey import parse
from .core import Market,Quote,TradeError
from .storage import export
PIN='1ba410ebe210d0059525fe0bc4d297f67341a16780b1253b42a43f36ab673d3d'

def unique(pairs):
    d={}
    for k,v in pairs:
        if k in d:raise ValueError('duplicate key')
        d[k]=v
    return d

def buyer(raw):
    data=json.loads(raw,object_pairs_hook=unique)
    if not isinstance(data,dict) or set(data)!={'X17','Y62'}:raise ValueError('both variants required')
    return {k:parse(json.dumps(v,ensure_ascii=False),'buyer_product') for k,v in data.items()}

def row(path,kind):
    if not path.exists():return {'status':'missing','parsed':None}
    raw=path.read_text();r={'raw':raw,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    try:r.update(status='valid',parsed=buyer(raw) if kind=='buyer' else parse(raw,kind))
    except (ValueError,TypeError):r.update(status='invalid',parsed=None)
    return r

def load(root):
    root=Path(root)
    if hashlib.sha256((root/'protocol.json').read_bytes()).hexdigest()!=PIN:raise ValueError('frozen protocol changed')
    p=json.loads((root/'protocol.json').read_text())
    for name,sha in p['sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise ValueError('frozen input changed')
    records={};expected=set()
    for role in p['roles']:
        key=role;expected.add(key);records[key]=row(root/'responses'/f'{key}.txt','buyer')
        for variant in ('X17','Y62'):
            for suffix,kind in [('seller','seller_offer'),('review','buyer_review')]:
                key=f'{role}-{variant}-{suffix}';expected.add(key);records[key]=row(root/'responses'/f'{key}.txt',kind)
    if any(x.stem not in expected for x in (root/'responses').glob('*.txt')):raise ValueError('unknown output')
    if not (root/'manifest.json').is_file():raise ValueError('sealed manifest required')
    pins=json.loads((root/'manifest.json').read_text())['sha256']
    required={'protocol.json','execution.json'}|{f'responses/{k}.txt' for k,v in records.items() if v['status']!='missing'}
    if not required.issubset(pins):raise ValueError('unsealed evidence')
    for name,sha in pins.items():
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('unsafe path')
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise ValueError('sealed evidence changed')
    # Conditional prompts must be exact frozen-template substitutions.
    for role in p['roles']:
        for variant in ('X17','Y62'):
            br=(records[role]['parsed'] or {}).get(variant)
            for suffix in ('seller','review'):
                key=f'{role}-{variant}-{suffix}'
                if records[key]['status']=='missing':continue
                text=(root/'prompts'/f'{suffix}_template.txt').read_text()
                values={'buyer':json.dumps(br,ensure_ascii=False),'card':(root/f'card-{variant}.txt').read_text(),'variant':variant,'seller':records[f'{role}-{variant}-seller'].get('raw','')}
                for slot,value in values.items():text=text.replace('{'+slot+'}',value)
                if (root/'prompts'/f'{key}-actual.txt').read_text()!=text:raise ValueError('conditional prompt mismatch')
    return p,records

def branch(p,b,s,r):
    buy=b and b['decision']=='buy';consent=s and s['decision']=='accept_dispatch'
    if s is not None and not buy:raise ValueError('seller called without buyer consent')
    if r is not None and not (buy and consent):raise ValueError('review before mutual consent')
    class Service:
        name='information-contrast-bottle/v1'
        def quote(self,source):return Quote(p['price'],p['delivery_cost'],self.name)
        def fulfill(self,*args):return [p['delivery'].copy()]
    class Buyer:
        def assess(self,*args):
            if r and r['decision']=='accept':return []
            if r and r['decision']=='refund':return ['actual model refund decision']
            raise TradeError('no settlement consent')
    m=Market(Service(),Buyer(),buyer_credits=90,seller_credits=40);commands=[]
    if buy and consent:
        commands=[('quote',{'source':[{'id':'A'}],'criteria':{'budget':90,'max_revisions':0}}),('fund',{}),('deliver',{})]
        if r and r['decision'] in ('accept','refund'):commands.append(('review',{}))
    for action,payload in commands:
        m.execute(action,'comparison-order',action,**payload);before=export(m)
        m.execute(action,'comparison-order',action,**payload)
        if export(m)!=before:raise RuntimeError('duplicate changes state')
    return export(m)

def build(root):
    p,rows=load(root);branches=[]
    for role,order in p['roles'].items():
        for variant in order:
            b=(rows[role]['parsed'] or {}).get(variant);s=rows[f'{role}-{variant}-seller'];r=rows[f'{role}-{variant}-review']
            if s['status']!='missing' and (not b or b['decision']!='buy'):raise ValueError('unexpected seller evidence')
            if r['status']!='missing' and (not s['parsed'] or s['parsed']['decision']!='accept_dispatch'):raise ValueError('unexpected review evidence')
            branches.append({'role':role,'variant':variant,'position':order.index(variant)+1,'buyer':b,'seller':s['parsed'],'review':r['parsed'],'market':branch(p,b,s['parsed'],r['parsed'])})
    return {'schema':'information-contrast-result/v1','protocol_sha256':PIN,'records':rows,'branches':branches,'actual_calls':sum(x['status']!='missing' for x in rows.values()),'independent_buyer_contexts':2,'real_customers':0,'real_payments':0,'empirical_conversion_rate':None,'limits':p['limits']}

def render(root,r):
    root=Path(root)
    body='<h1>补齐商品信息，顾客就会买吗？</h1><p>新一轮虚构商品信息对照，两个独立模型上下文，各自看两个版本，展示顺序相反。不是盲测或真实转化实验。</p>'
    for variant in ('X17','Y62'):body+='<details><summary>展开版本 '+variant+'</summary><pre>'+escape((root/f'card-{variant}.txt').read_text())+'</pre></details>'
    for b in r['branches']:
        body+='<section><h2>'+b['role']+' · '+b['variant']+' · 顺序'+str(b['position'])+'</h2><p>'+escape(json.dumps(b['buyer'],ensure_ascii=False))+'</p><p>积分转账 '+str(len(b['market']['journal']))+' 笔</p><details><summary>卖家、验收与完整账本</summary><pre>'+escape(json.dumps(b,ensure_ascii=False,indent=2))+'</pre></details></section>'
    body+='<details><summary>全部原始模型回答，含未进入阶段</summary><pre>'+escape(json.dumps(r['records'],ensure_ascii=False,indent=2))+'</pre></details><p>所有尺寸、清洗方案和检查记录均为假设，不是实物性能。两个上下文不是四个独立顾客；不能把差异当作已证明的信息或顺序效应。</p>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>虚构商品信息对照</title><link rel="stylesheet" href="/journey.css"><small>纯模拟 · 无真实支付</small>'+body+'</html>'

def main():
    root=Path(__file__).resolve().parents[1]/'examples/product-information-contrast'
    r=build(root);(root/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    html=render(root,r);(Path(__file__).parent/'web/information.html').write_text(html)
    css=(Path(__file__).parent/'web/journey.css').read_text()
    (root/'overview.html').write_text(html.replace('<link rel="stylesheet" href="/journey.css">','<style>'+css+'</style>'))
if __name__=='__main__':main()
