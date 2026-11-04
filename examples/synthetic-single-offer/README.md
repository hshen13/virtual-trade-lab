# 原币种单次报价接口：先修正尺度，不做现实校准

## 已核实的结构性不兼容

`virtual_trade_lab/realism.py` 的 `people()` 默认预算为8–22或18–45个未标币种的模拟单位，`simulate()` 要求 `person.budget >= offer.price`，`utility()` 还用任意 `price / 40` 系数，且每人有三期选择。

已保存的校准设计 `calibration_protocol.json` 则记录现实研究使用ZMW原币、单次分配报价最低50、报价前50赠款，不买保留赠款。**如果把50及以上报价直接送入旧默认预算，零购买是机械门槛，不是拟合出的顾客行为。** 这不意味着所有自定义Person预算都≤45，也不代表已执行过这种错误现实校准；未发现已有自动接入。原研究与codebook来源见已有校准协议，不在本样例复制任何家庭记录或购买结果。

旧 `realism.py` 保持不变，旧输出可继续复算。此新模块完全独立，不缩放价格，不变更默认预算或效用系数，也不根据已见购买比例调参。

## 新接口保留什么

`virtual_trade_lab.single_offer` 目前只接受**显式合成情境**，使用ZMW major原币单位及十进制字符串；不接收真实参与者行，不做换汇或积分映射。

- 分开保存标价、完整交易价、报价前无条件现金赠款、自有可支配资金。
- 自有资金字段明确不含赠款；可用总额为自有资金+赠款。
- 自有预算未知则保留null，不从人口、观测购买或旧模型推断。若赠款本身足够支付，仍可确认最低限度的可负担性；总现金余额依然未知。
- `transaction_price - cash_gift` 仅作说明，不替代付款额。净差0也不是免费选择：购买放弃了保留赠款现金的机会。
- 选择为buy/decline/defer，不先运行宣传注意率、三期复购或任意效用评分。
- 声明buy但预算未知，记录pending_budget_evidence；已知资金不足则记录infeasible_declared_buy。两者都保留原buy，不偷偷改成拒绝或算作实际购买。
- `recorded_simulated_payment` 只是合成案例记账，不是真实付款、收款凭据或完成了双方同意的市场交易。该窄接口不承担商家、托管、物流与售后。
- 重新读取保存记录只能重放相同报价和决定；不同价格/选择或损坏记录报冲突，不能冒充重试。没有数据库或跨进程并发锁。

模型可见上下文只允许定义字段，不带观测结果、转化率、标签或校准结论。现有已看过的研究只能作为开发参考，不能冒称新盲测；本轮没有模型角色调用，没有向模型提交真实结果。默认calibration_status一直not_evaluated。

## 完全合成示例

`offer.json` 并非研究报价或参与者：虚构对象标价120、报价75、赠款20、自有可用60 ZMW。

- 声明购买：可用80，完整模拟付款75，剩5；不是只付净差55。
- 拒绝：不付任何款，保留80，其中20为可保留赠款。
- 尚无使用体验：status=not_available、days=null，不假装已使用过实物。

```sh
python -m virtual_trade_lab.single_offer --spec examples/synthetic-single-offer/offer.json
python -m virtual_trade_lab.single_offer --spec examples/synthetic-single-offer/offer.json --choice buy
python -m virtual_trade_lab.single_offer --spec examples/synthetic-single-offer/offer.json --choice decline
python -m virtual_trade_lab.single_offer --spec examples/synthetic-single-offer/offer.json --choice buy --previous examples/synthetic-single-offer/buy.json
python -B -m unittest discover -s tests -p test_single_offer.py -v
```

这些buy/decline是人工指定的规则样例，**不是实际顾客或模型选择**。接口只防止单位、赠款和预算语义错误，不能判断产品价值、提供合法性认证或使虚拟人自动与现实对齐。
