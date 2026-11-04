# 先收回，再退款：模型决定与模拟物流分开

先看 [一页中文概览](overview.html)。本轮修正的缺口是：此前退款没有处理商品退回、等待收件和返程费用。

这是独立新订单，**从已交付、尚未验收的固定初态开始**。购买与首次交付由场景设定，不算本轮模型决定；没有改写旧的即时退款实验。

## 实际发生了什么

预冻结协议SHA256：`efc7656c21b216deb047de6cf9436572c3eee858a8c78ab0da68d0cd6cdb208c`。

实际取得3份模型回应，原文全部保留，无重试或替换：

1. 买家申请退货：320g超过250g上限，且unit-B不符约定unit-A，愿提交合成记录。
2. 独立卖家批准收回，明确“目前未收件，款项继续托管”。批准没有触发退款。
3. 同一买家再次自主选择ship，愿花约10分钟交回，并明确等待匹配收件证据，不视为已退款。

随后只按预声明的**脚本物流输入**执行：tick1交到模拟承运方、tick2尚未收件、tick3收到订单/标签/单件匹配的证据。这不是额外模型决定、真实寄件或现实时间。

## 积分与商品状态

- 审核批准、商品仍在买家：买家58，卖家36，费用4，托管32。
- 交回承运方、尚未收件：买家58，卖家32，费用8，托管32。
- 匹配收件后退款：买家90，卖家32，费用8，托管0。

总额始终130。4积分首次履约费已经发生，返程费4仅在实际模拟交回时扣，费用都由卖方承担。缺失收件不是失败，也不会自动退款或给卖家放款。

`return_protocol` 的 received_refund_ready 表示收件证据门槛满足；是否已经退款另看 `market.orders[0].state=rejected` 和 `reject_refund` 账本记录。批准、收件、结算是不同状态。

货品采购成本、实物损坏与库存价值回收未入账，不能把余额变化当完整损益，更不是真实收入。10分钟与返程费4也是假设。

## 自主纠正和验证

审查发现初版低层账本可能用同一收件证据处理别的订单，已修复为同时绑定**本订单和实际交付单件**。跳过返程费直接退款、错标签/单件/订单、提前收件、超期交回、重复收费/收件/退款均受回归保护。

买家keep/defer、卖家deny/request_evidence/defer保留为合法未决分支，不替角色答应。本轮实际模型选择的是退货，其他分支只有规则测试，不能计为额外模型样本。

保留的一次测试失败是“对已退款数据库尝试倒退到tick2”的异常类型预期不符：存储层在重放时安全拒绝，并未撤销退款。已调整测试明确检查拒绝后tick3仍能完整重放。不要用旧tick改写后来的历史；查看旧阶段用保存快照或新的独立数据库。

## 重放

```
python -m virtual_trade_lab.return_custody_study --study examples/return-custody-model-study --db /tmp/return-study.sqlite3 --tick 2 --output /tmp/return-pending.json
python -m virtual_trade_lab.return_custody_study --study examples/return-custody-model-study --db /tmp/return-study.sqlite3 --tick 3 --output /tmp/return-final.json
cmp /tmp/return-final.json examples/return-custody-model-study/report.json
python -m unittest discover -s tests -p 'test_return_custody*.py' -v
PYTHONPATH=. python examples/return-custody-model-study/render_overview.py
```

模型原文在 `responses/`，冻结提示与实际续问在 `prompts/`。`approval_not_refund.json` 是只有2份回应时保存的真实实验快照，未提前补入买家寄回选择。`handed_off_not_received.json` 保留物流等待阶段，最终 `report.json` 保留收件及退款。

SQLite保存市场命令；角色与承运事件保存在封存文件并确定性重放。事件中的buyer/seller/carrier是模拟标签，不提供真实身份认证。可重复执行不会重复转移费用或退款；文件哈希仅验证完整性，不独立证明模型来源。

没有额外付费API、真实客户、公开评价、推广或论文复现。模型SKU/采样种子未核验。静态概览只检查生成内容与转义，未绕过此前浏览器环境限制，未宣称视觉QA通过。
