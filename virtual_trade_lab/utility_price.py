"""Replay a frozen 2-persona x 3-price development study, not human demand."""
import hashlib
from html import escape
import json
from pathlib import Path
from .information_contrast import branch,unique
from .channel_journey import parse
PIN='92ed982380ffc4d071102dab923947da69be8f939f09dba84acedaa5ccf15405'

def choice(raw):
    d=json.loads(raw,object_pairs_hook=unique)
    if not isinstance(d,dict) or set(d)!={'choice','reason'} or d['choice'] not in ('old','original','v2','defer') or not isinstance(d['reason'],str) or not d['reason'].strip():raise ValueError('invalid buyer choice')
    return d

def read(path,kind):
    if not path.exists():return {'status':'missing','parsed':None}
    raw=path.read_text();r={'raw':raw,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    try:r.update(status='valid',parsed=choice(raw) if kind=='buyer' else parse(raw,kind))
    except (ValueError,TypeError):r.update(status='invalid',parsed=None)
    return r

def load(root,sealed=True):
    root=Path(root)
    if hashlib.sha256((root/'protocol.json').read_bytes()).hexdigest()!=PIN:raise ValueError('frozen protocol changed')
    p=json.loads((root/'protocol.json').read_text())
    for name,sha in p['sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise ValueError('frozen input changed')
    rows={};expected=set()
    for case in p['cases']:
        for suffix,kind in [('', 'buyer'),('-seller','seller_offer'),('-review','buyer_review')]:
            key=case+suffix;expected.add(key);rows[key]=read(root/'responses'/f'{key}.txt',kind)
    if any(x.stem not in expected for x in (root/'responses').glob('*.txt')):raise ValueError('unexpected output')
    if sealed:
        pins=json.loads((root/'manifest.json').read_text())['sha256']
        required={'protocol.json','execution.json','failures.json'}|{f'responses/{k}.txt' for k,v in rows.items() if v['status']!='missing'}
        if not required.issubset(pins):raise ValueError('unsealed evidence')
        for name,sha in pins.items():
            if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('unsafe path')
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise ValueError('sealed evidence changed')
    for case,c in p['cases'].items():
        b=rows[case]['parsed']
        for suffix in ('seller','review'):
            key=case+'-'+suffix
            if rows[key]['status']=='missing':continue
            if not b or b['choice'] not in ('original','v2'):raise ValueError('later call without purchase choice')
            text=(root/'prompts'/f'{suffix}_template.txt').read_text()
            vals={'buyer':rows[case]['raw'],'seller':rows[case+'-seller'].get('raw',''),'option':json.dumps(c['options'][b['choice']],ensure_ascii=False)}
            for k,v in vals.items():text=text.replace('{'+k+'}',v)
            if (root/'prompts'/f'{key}-actual.txt').read_text()!=text:raise ValueError('prompt derivation mismatch')
    return p,rows

def result(root,sealed=True):
    root=Path(root);p,rows=load(root,sealed);failures=json.loads((root/'failures.json').read_text());cases=[]
    for key,c in p['cases'].items():
        b=rows[key]['parsed'];s=rows[key+'-seller'];r=rows[key+'-review'];buy=b and b['choice'] in ('original','v2')
        if s['status']!='missing' and not buy:raise ValueError('seller without purchase consent')
        if r['status']!='missing' and (not s['parsed'] or s['parsed']['decision']!='accept_dispatch'):raise ValueError('review before seller consent')
        if key in failures and rows[key]['status']!='missing':raise ValueError('failure and answer conflict')
        option=c['options'][b['choice']] if buy else c['options']['v2']
        ledger=branch({'price':option['price'],'delivery_cost':p['delivery_fee'],'delivery':option}, {'decision':'buy' if buy else 'leave','reason':'adapter projection; not additional model output'},s['parsed'],r['parsed'])
        cases.append({'case':key,'profile':c['profile'],'v2_price':c['v2_price'],'presentation_order':c['order'],'buyer':b,'seller':s['parsed'],'review':r['parsed'],'failure':failures.get(key),'market':ledger})
    return {'schema':'utility-price-results/v1','protocol_sha256':PIN,'cases':cases,'records':rows,'infrastructure_failures':failures,'actual_responses':sum(x['status']!='missing' for x in rows.values()),'real_customers':0,'real_payments':0,'price_elasticity':None,'empirical_conversion':None,'cost_or_profit_validated':False,'limits':p['limits']}

def render(root,r):
    root=Path(root);p=json.loads((root/'protocol.json').read_text())
    out='<h1>换功能，而不只是换文案</h1><p>2种虚拟处境 × V2三档价格。旧瓶0、原杯32；V2容量和性能假设固定，价格16/24/32。每格一个独立顾客上下文，完整保留选择和模型容量错误。</p><p>所有保冷、防漏、清洗和出库表现都是假设或合成记录，不是现实测试。不是价格弹性、真人转化或利润证据。</p>'
    for c in r['cases']:
        out+='<section><h2>'+escape(c['case'])+'</h2><p>'+escape(json.dumps(c['buyer'] if c['buyer'] else c['failure'],ensure_ascii=False))+'</p><p>余额 '+escape(json.dumps(c['market']['balances'],ensure_ascii=False))+'</p><details><summary>本格看到的原始提示</summary><pre>'+escape((root/'prompts'/f'{c["case"]}.txt').read_text())+'</pre></details><details><summary>完整模型原文与账本</summary><pre>'+escape(json.dumps({'case':c,'records':{k:v for k,v in r['records'].items() if k==c['case'] or k.startswith(c['case']+'-')}},ensure_ascii=False,indent=2))+'</pre></details></section>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V2虚构功能与价格实验</title><link rel="stylesheet" href="/journey.css"><small>纯模拟 · 无真实支付</small>'+out+'<p>顺序按固定种子平衡，但每格仅一次且有缺失，不能分离顺序效应或估计真实转化。采购成本未知，账本只是积分守恒。没有实体寄回。</p></html>'

def main():
    root=Path(__file__).resolve().parents[1]/'examples/product-utility-price-v2';r=result(root)
    (root/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    html=render(root,r);web=Path(__file__).parent/'web';(web/'utility.html').write_text(html)
    (root/'overview.html').write_text(html.replace('<link rel="stylesheet" href="/journey.css">','<style>'+(web/'journey.css').read_text()+'</style>'))
if __name__=='__main__':main()
