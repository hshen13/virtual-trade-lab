"""Read-only, verified projection of the preserved return-custody experiment."""
from copy import deepcopy
from html import escape
import json
from pathlib import Path
from .return_custody_study import load, plan, ReturnMarket, Service, Buyer, PIN
from .storage import export


def projection(p, records, tick):
    state, commands = plan(p, records, tick)
    market = ReturnMarket(Service(p), Buyer(state), buyer_credits=90, seller_credits=40)
    for action, payload in commands:
        market.execute(action, p['order_id'], action, **payload)
    return state.snapshot(), export(market)


def build(root):
    root = Path(root)
    if not (root/'manifest.json').is_file():
        raise ValueError('sealed evidence required')
    p, records = load(root)
    stages = []
    definitions = [
        ('approval_not_refund.json', 0, '已批准，仍未退款', '商品仍在买家手里。审核同意不是收件，也不释放托管。', False),
        ('handed_off_not_received.json', 2, '已交回，等待收件', '脚本承运流程记录 tick1 交回。tick2 尚未收件，卖家已承担返程费4，32积分继续托管。', True),
        (None, 3, '匹配收件，退回32积分', '脚本 tick3 收件记录匹配订单、标签与单件，协议才退款。未发生真实物流或支付。', True),
    ]
    for filename, tick, title, description, has_shipping in definitions:
        prefix = deepcopy(records)
        if not has_shipping:
            prefix['buyer_shipping'] = {'status':'missing', 'parsed':None}
        state, market = projection(p, prefix, tick)
        saved = json.loads((root/'snapshots'/filename if filename else root/'report.json').read_text())
        if (saved['protocol_sha256'] != PIN or saved['observation_tick'] != tick or
                saved['records'] != prefix or saved['return_protocol'] != state or saved['market'] != market):
            raise ValueError('snapshot disagrees with sealed role evidence and replay')
        stages.append(dict(title=title, description=description, tick=tick,
                           custody=state['custody'], balances=market['balances'],
                           journal=market['journal'], records=prefix))
    return dict(schema='return-replay/v1', protocol_sha256=PIN, real_payments=0,
                model_calls=3, source='examples/return-custody-model-study', stages=stages)


def render(data):
    nav=''.join(f'<a href="#stage-{i}">{i} · {escape(s["title"])}</a>' for i,s in enumerate(data['stages'],1))
    cards=[]
    labels={'buyer':'买家','seller':'卖家','provider':'费用账户','escrow:return-order':'托管'}
    actors={'buyer_request':'买家申请','seller_review':'卖家审核','buyer_shipping':'买家交回决定'}
    for i,s in enumerate(data['stages'],1):
        balances=''.join(f'<div><span>{labels[k]}</span><b>{v}</b></div>' for k,v in s['balances'].items())
        roles=''.join(f'<details><summary>{actors[k]} · 查看实际模型原文</summary><pre>{escape(v["raw"])}</pre></details>' for k,v in s['records'].items() if v['status']!='missing')
        custody={'buyer':'买家','carrier':'模拟承运方','seller':'卖家'}[s['custody']]
        cards.append(f'<section id="stage-{i}" tabindex="-1"><small>保存的观察点 {i}/3 · tick {s["tick"]}</small><h2>{escape(s["title"])}</h2><p>{escape(s["description"])}</p><p>商品保管方：<strong>{custody}</strong></p><div class="balances">{balances}</div><p class="muted">账户总额 {sum(s["balances"].values())} 积分。费用账户是模拟成本去向，不是商家利润。</p>{roles}<details><summary>查看这个时点的账本</summary><pre>{escape(json.dumps(s["journal"],ensure_ascii=False,indent=2))}</pre></details><a href="#top">返回总览</a></section>')
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>退货追踪 · 只读模型实验</title><link rel="stylesheet" href="/returns.css"></head><body><main id="top"><span class="badge">纯模拟 · 无真实支付或物流</span><h1>退货批准了，钱为什么还没回来？</h1><p class="lead">看三个保存时点：买家是否交回、商品在哪里、32积分何时退回。点击阶段或展开原文，不会执行交易。</p><div class="notice"><strong>独立退货实验，不是旧购买录像的后续。</strong><p>本轮从固定“已交付、未验收”状态开始：虚构水瓶承诺220g，到货记录320g，超过买家250g上限且单件编号不符。前序购买由脚本初始化，3次退货决定来自实际保留的对话模型回应，承运和收件为预设环境事件。</p></div><nav aria-label="退货观察点">'''+nav+'''</nav>'''+''.join(cards)+'''<section><h2>哪些结果没有发生？</h2><p>这次模型选择申请、批准并交回，没有取得新的拒绝案例。拒绝、暂缓、错订单、迟交与重复退款仅由规则测试覆盖，不能算更多顾客结果。</p><p>这是已完成实验的历史回放，不是实时物流。若没有匹配收件，保持等待与托管；本原型尚无丢件、仲裁或自动超时赔付机制，不能承诺现实退款时限。</p><p>模型型号与采样种子未核验；无真人校准或真实销售证明。哈希只检查证据一致性。</p><a href="/returns-data.json" download="return-replay.json">下载此回放证据</a><p><a href="/replay">查看另一独立实验：购买与即时拒收退款</a> · <a href="/">返回实验台</a></p><p class="muted">使用原生链接和折叠详情，可用浏览器返回、刷新保留阶段锚点；页面和下载链接由本地服务提供。未完成浏览器视觉验收。</p></section></main></body></html>'''


def main():
    root=Path(__file__).resolve().parents[1]
    data=build(root/'examples/return-custody-model-study')
    web=root/'virtual_trade_lab/web'
    (web/'returns-data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    (web/'returns.html').write_text(render(data))

if __name__=='__main__':main()
