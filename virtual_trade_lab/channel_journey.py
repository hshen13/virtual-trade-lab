"""Frozen original text-ad journey, driven only by preserved model decisions."""
import hashlib
from html import escape
import json
from pathlib import Path
from .core import Market,Quote,TradeError
from .storage import export

PIN='6498838ddce766839dfaaa2c6c3646af926674a100d8617da17114a3a5652157'
CHOICES={'buyer_entry':{'open_product','leave','defer'},'buyer_product':{'buy','leave','defer'},'seller_offer':{'accept_dispatch','decline','defer'},'buyer_review':{'accept','refund','defer'}}

def parse(raw,stage):
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise ValueError('duplicate key')
            d[k]=v
        return d
    d=json.loads(raw,object_pairs_hook=unique)
    if not isinstance(d,dict) or set(d)!={'decision','reason'} or d['decision'] not in CHOICES[stage] or not isinstance(d['reason'],str) or not d['reason'].strip():raise ValueError('invalid role response')
    return d


def load(root):
    root=Path(root)
    if hashlib.sha256((root/'protocol.json').read_bytes()).hexdigest()!=PIN:raise ValueError('frozen protocol changed')
    p=json.loads((root/'protocol.json').read_text())
    for name,sha in p['sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise ValueError('frozen visible input changed')
    rows={}
    for key in CHOICES:
        path=root/'responses'/f'{key}.txt'
        if not path.exists():rows[key]={'status':'missing','parsed':None};continue
        raw=path.read_text();row={'raw':raw,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        try:row.update(status='valid',parsed=parse(raw,key))
        except (ValueError,TypeError):row.update(status='invalid',parsed=None)
        rows[key]=row
    if any(x.stem not in CHOICES for x in (root/'responses').glob('*.txt')):raise ValueError('unknown output')
    for key,slot,source in [('buyer_product','entry','buyer_entry'),('seller_offer','buyer','buyer_product'),('buyer_review','seller','seller_offer')]:
        if rows[key]['status']=='missing':continue
        expected=(root/'prompts'/f'{key}_template.txt').read_text().replace('{'+slot+'}',rows[source].get('raw',''))
        if (root/'prompts'/f'{key}_actual.txt').read_text()!=expected:raise ValueError('actual prompt mismatch')
    manifest=root/'manifest.json'
    if not manifest.is_file():raise ValueError('sealed evidence manifest required')
    if manifest.exists():
        pins=json.loads(manifest.read_text())['sha256']
        required={'protocol.json','execution.json'}|{f'responses/{k}.txt' for k,v in rows.items() if v['status']!='missing'}
        if not required.issubset(pins):raise ValueError('unsealed evidence')
        for name,sha in pins.items():
            if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('unsafe manifest path')
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise ValueError('sealed evidence changed')
    return p,rows


def execute(p,rows):
    def choice(key):return (rows[key]['parsed'] or {}).get('decision')
    allowed=['buyer_entry']
    if choice('buyer_entry')=='open_product':
        allowed.append('buyer_product')
        if choice('buyer_product')=='buy':
            allowed.append('seller_offer')
            if choice('seller_offer')=='accept_dispatch':allowed.append('buyer_review')
    for k,v in rows.items():
        if v['status']!='missing' and k not in allowed:raise ValueError('later decision without prior consent')
    class Service:
        name='fictional-channel-bottle/v1'
        def quote(self,source):return Quote(p['price'],p['delivery_cost'],'fictional-channel-bottle/v1')
        def fulfill(self,*args):return [p['delivery'].copy()]
    class Buyer:
        def assess(self,*args):
            if choice('buyer_review')=='accept':return []
            if choice('buyer_review')=='refund':return ['actual model requested refund after disclosed mismatch']
            raise TradeError('no actual review decision')
    market=Market(Service(),Buyer(),buyer_credits=p['buyer_credits'],seller_credits=p['seller_credits'])
    commands=[]
    if 'buyer_review' in allowed:
        commands=[('quote',{'source':[{'id':'A'}],'criteria':{'budget':90,'max_revisions':0}}),('fund',{}),('deliver',{})]
        if choice('buyer_review') in ('accept','refund'):commands.append(('review',{}))
    checkpoints=[]
    for action,payload in commands:
        market.execute(action,'journey-order',action,**payload)
        before=export(market)
        market.execute(action,'journey-order',action,**payload)
        if export(market)!=before:raise RuntimeError('repeated command changed ledger')
        checkpoints.append({'action':action,'market':before})
    final=export(market)
    return {'schema':'channel-journey-result/v1','protocol_sha256':PIN,'records':rows,'reached_stages':allowed,
            'model_calls_recorded':sum(v['status']!='missing' for v in rows.values()),'market':final,'checkpoints':checkpoints,
            'real_customers':0,'real_payments':0,'video_views_measured':None,'stopped_at':allowed[-1],
            'limits':'One conversation-model role journey; textual storyboard not video viewing. No conversion estimate, human calibration, ad attribution or superiority claim. Ledger and delivery are deterministic; physical return custody not simulated.'}


def page(root,report):
    root=Path(root);parts=[]
    if 'buyer_product' in report['reached_stages']:
        parts.append('<section><h2>顾客点开后实际收到的商品页</h2><pre>'+escape((root/'product-page.txt').read_text())+'</pre></section>')
    labels={'buyer_entry':'看到文字广告后','buyer_product':'了解商品后','seller_offer':'卖家确认','buyer_review':'到货评价 / 售后'}
    for key,row in report['records'].items():
        parts.append('<section><h2>'+labels[key]+'</h2><p>'+('未进入或未取得回答，不能算同意' if row['status']=='missing' else escape((row['parsed'] or {}).get('reason','无效回复，未作为同意')) )+'</p><details><summary>完整原文与状态</summary><pre>'+escape(json.dumps(row,ensure_ascii=False,indent=2))+'</pre></details></section>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>从广告入口到顾客决定</title><style>body{font:16px/1.8 system-ui;background:#f0f5f2;color:#193e36;max-width:850px;margin:auto;padding:25px}section{background:white;padding:22px;margin:18px 0;border-radius:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}summary{cursor:pointer}small{color:#68531d}</style><small>纯模拟 · 原创文字广告 · 无真实观看或支付</small><h1>一个顾客，会走到哪一步？</h1><p>只有保存的独立模型选择才能推进下一阶段。拒绝与离开原样保留，不为演示补造成交。</p><section><h2>顾客实际收到的入口</h2><pre>'+escape((root/'advertisement.txt').read_text())+'</pre></section><section><h2>本轮实得结果</h2><p>保存模型回应 '+str(report['model_calls_recorded'])+' 份；账本转账 '+str(len(report['market']['journal']))+' 笔。未进入的后续阶段保持空白，不算默许或购买。</p></section>'+''.join(parts)+'<section><h2>最终积分与边界</h2><pre>'+escape(json.dumps(report['market'],ensure_ascii=False,indent=2))+'</pre><p>商品页、卖家、交付和售后只有前一步实际同意才进入。未进入的阶段不算失败购买，也不补造新的模型回应。当前缺少真实视频播放、可点击渠道接入及产品体验测量。</p><p>一名模型角色不是实际顾客；不能据此计算转化率或证明宣传有效。</p></section></html>'


def main():
    root=Path(__file__).resolve().parents[1]/'examples/channel-customer-journey'
    p,rows=load(root);r=execute(p,rows)
    (root/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    html=page(root,r)
    (root/'overview.html').write_text(html)
    css=html.split('<style>',1)[1].split('</style>',1)[0]
    web=Path(__file__).parent/'web'
    (web/'journey.html').write_text(html.replace('<style>'+css+'</style>','<link rel="stylesheet" href="/journey.css">'))
    (web/'journey.css').write_text(css)


if __name__=='__main__':main()
