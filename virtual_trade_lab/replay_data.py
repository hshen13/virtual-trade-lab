"""Build a read-only UI projection from sealed model responses and verified ledger.

No database writes and no model calls. UI stages are explanatory, not measured time.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from .precommit_study import load,plan,FixtureSeller,RecordedBuyer
from .core import Market
from .storage import export


def build(root):
    root=Path(root)
    if not (root/'manifest.json').is_file():raise ValueError('sealed evidence manifest required')
    p,records=load(root);report=json.loads((root/'report.json').read_text())
    actual_protocol_hash=hashlib.sha256((root/'protocol.json').read_bytes()).hexdigest()
    if report.get('protocol_sha256')!=actual_protocol_hash:
        raise ValueError('report protocol hash differs from frozen protocol')
    if p['schema']!='defect-refund-model-study/v1' or records['buyer_review']['parsed']['decision']!='refund':
        raise ValueError('this viewer requires the sealed model-refund study, not an arbitrary transaction')
    expected_plan=plan(p,records)
    if report['records']!=records or report['plan']!=expected_plan:
        raise ValueError('report does not match sealed role evidence')
    market=Market(FixtureSeller(p),RecordedBuyer(p,records),buyer_credits=90,seller_credits=40)
    states={'initial':export(market)}
    for action,payload in expected_plan['commands']:
        market.execute(action,'A','A:'+action,**payload);states[action]=export(market)
    if export(market)!=report['state']:
        raise ValueError('saved ledger not reproduced by recorded decisions')
    def stage(key,title,caption,account,roles=(),fixture=None):
        state=states[account]
        b=state['balances']
        return dict(id=key,title=title,caption=caption,
                    balances=dict(buyer=b['buyer'],seller=b['seller'],escrow=b.get('escrow:A',0),cost=b['provider']),
                    total=sum(b.values()),journal=deepcopy(state['journal']),
                    model_outputs=[dict(stage=n,raw=records[n]['raw'],**records[n]['parsed']) for n in roles],
                    inspection=deepcopy(fixture),money_changed=account in ('fund','deliver','review'))
    steps=[
        stage('offer','先看商品与退货规则','32积分，500ml、标称220g。买家有90积分，也可免费使用旧饮料瓶。','initial'),
        stage('inspect','双方选择先验货','这是入库记录，不保证封箱内容。查看记录不等于承诺购买。','initial',('buyer_inspection','seller_inspection'),p['inspection_fixture']),
        stage('fund','各自同意，才进入托管','买卖双方分别接受条件。32积分进入托管，尚未给卖家。','fund',('buyer_commit','seller_commit')),
        stage('deliver','卖方交付，承担4积分费用','卖方诚实说明封箱未复核。交付不代表买方已验收。','deliver',('seller_delivery',)),
        stage('unpack','开箱发现：320g，不是220g','预设模拟错装：unit-B，不是入库的unit-A；超过买方250g上限。此处是环境事实，不是模型猜测。','deliver',(),p['delivery_fixture']),
        stage('refund','买家拒收，32积分原路退回','买家实际选择refund。卖方已在承诺时同意自动全退，不需要伪造第二次批准。','review',('buyer_review',)),
    ]
    steps[4]['money_changed']=False
    return dict(schema='model-refund-replay/v1',disclosure='纯模拟 · 无真实支付',
                title='一次模型驱动的购物与退款',study='defect-refund-model-study',
                summary=dict(actual_model_responses=6,refund_credits=32,delivery_cost=4,real_payments=0),
                product=dict(name='虚构A杯',price=32,capacity_ml=500,listed_weight_g=220,buyer_limit_g=250,alternative='免费旧饮料瓶',picture='原创示意图，不是商品实拍'),
                steps=steps,source=dict(protocol_sha256=actual_protocol_hash,
                    report_sha256=hashlib.sha256((root/'report.json').read_bytes()).hexdigest(),
                    evidence_path='examples/defect-refund-model-study',
                    files=['protocol.json','manifest.json','report.json','responses/*.txt']),
                limits=['模型输出是真实保存的角色回应；商品、检查和错装是预设模拟输入。',
                        '六步按记录组织讲解，不是屏幕录像或测得的实际耗时。',
                        '按钮只切换视图，不重跑模型、不付款、不再次退款。',
                        '本次不是随机对照、真实客户验证或论文复现；不据此推断盈利。'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.write_text(json.dumps(build(a.study),ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
