"""Original static reading page from preserved evidence; no JS/network/model calls."""
from html import escape
import json
from pathlib import Path
from virtual_trade_lab.return_custody_study import load,plan,ReturnMarket,Service,Buyer
from virtual_trade_lab.storage import export


def build(root):
    root=Path(root)
    if not (root/'manifest.json').is_file():raise ValueError('sealed evidence required')
    p,records=load(root);state,commands=plan(p,records,3)
    m=ReturnMarket(Service(p),Buyer(state),buyer_credits=90,seller_credits=40)
    for a,payload in commands:m.execute(a,p['order_id'],a,**payload)
    report=json.loads((root/'report.json').read_text())
    if report['market']!=export(m) or report['records']!=records or report['return_protocol']!=state.snapshot():raise ValueError('report disagrees with sealed evidence')
    earlier=[json.loads((root/'snapshots'/f).read_text()) for f in ('approval_not_refund.json','handed_off_not_received.json')]
    cards=''
    for stage,label in [('buyer_request','买家 · 申请退货'),('seller_review','卖家 · 同意收回'),('buyer_shipping','买家 · 决定交回')]:
        x=records[stage];cards+=f'<article><small>实际模型回应</small><h2>{label}</h2><p>{escape(x["parsed"]["reason"])}</p><details><summary>查看原文</summary><pre>{escape(x["raw"])}</pre></details></article>'
    rows=''
    for label,r in [('已批准，未交回',earlier[0]),('已交回，未收件',earlier[1]),('匹配收件，完成退款',report)]:
        b=r['market']['balances'];rows+=f'<tr><th>{label}</th><td>{b["buyer"]}</td><td>{b["escrow:return-order"]}</td><td>{b["seller"]}</td><td>{b["provider"]}</td></tr>'
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>退货闭环 · 先收回，再退款</title><style>
body{font-family:system-ui,"Noto Sans CJK SC",sans-serif;background:#f3f6f4;color:#203934;margin:0;line-height:1.7}main{max-width:980px;margin:auto;padding:38px 22px}.tag{font-size:12px;background:#fff0cd;color:#78591c;padding:7px 12px;border-radius:5px}h1{font-size:38px;line-height:1.3;letter-spacing:-.03em;margin-bottom:12px}.lead{color:#54796f;max-width:730px}.result{background:#175b4f;color:white;border-radius:13px;padding:24px;margin:27px 0}.result b{font-size:32px}.result p{margin:7px 0}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}article,section.panel{background:white;border:1px solid #dbe6df;border-radius:12px;padding:21px}small{color:#678b7f}h2{font-size:19px}p{font-size:14px}section.panel{margin-top:20px}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:12px 7px;border-bottom:1px solid #e4ece6;text-align:left}td{font-variant-numeric:tabular-nums}thead{color:#648174}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;background:#f4f7f5;padding:9px}summary{cursor:pointer;color:#417b68;font-size:12px;padding:6px 0}.note{font-size:12px;color:#6d8079}a{color:#186d58}code{overflow-wrap:anywhere;font-size:11px}@media(max-width:700px){.cards{grid-template-columns:1fr}h1{font-size:29px}main{padding:28px 15px}table{font-size:11px}td,th{padding:9px 4px}}
</style></head><body><main><span class="tag">纯模拟 · 无真实寄件或支付</span><h1>同意退货，不等于已经退款。</h1><p class="lead">这次补上了上一轮没有处理的环节：商品是否真的交回？谁承担返程费用？只有订单、标签和单件编号匹配的模拟收件证据到达，32积分才退回。</p><div class="result"><b>32积分已退回</b><p>卖家承担交付费4 + 返程费4。最终买家90、卖家32、费用账户8、托管0，总额130守恒。</p><small style="color:#b9d7cb">独立新情境：之前购买与交付是固定初态，不算本轮模型决定。</small></div><div class="cards">'''+cards+'''</div><section class="panel"><h2>积分没有提前退，也没有重复退</h2><table><thead><tr><th>阶段</th><th>买家</th><th>托管</th><th>卖家</th><th>费用</th></tr></thead><tbody>'''+rows+'''</tbody></table><p class="note">收件是预设的承运流程：tick1交回、tick2尚未收到、tick3匹配收件；不是额外模型、真实物流或实际耗时。</p></section><section class="panel"><h2>哪些是真实取得的决定？</h2><p>3份对话模型回应：申请、审核、交回。没有重试筛结果。运输与匹配收件是明确标注的脚本环境输入。规则测试还覆盖拒绝、暂缓、错订单、错单件、迟交、提前退款及重复收费，不能把这些测试当额外模型结果。</p><p>修复了收件证据可能用于别的订单的边界问题：现在必须同时绑定本订单与交付单件。</p><details><summary>来源与限制</summary><p><a href="README.md">完整说明</a> · <a href="report.json">完整报告</a> · <a href="manifest.json">证据清单</a></p><p>退货费4、交回需10分钟、物流耗时均为假设；不模拟真实认证、物品损坏、争议升级或完整库存成本。不是真人校准、收入或论文复现。型号/采样种子未核验，哈希不独立证明模型来源。</p><code>'''+escape(report['protocol_sha256'])+'''</code></details></section><p class="note">本地静态阅读页，无外部资源、交易按钮或网络请求。未进行浏览器视觉验收。</p></main></body></html>'''


if __name__=='__main__':
    root=Path(__file__).resolve().parent
    (root/'overview.html').write_text(build(root))
