# 贡献指南

1. 使用 Python 3.10+，不需要付费 API、Docker 或真实账户。
2. 提交新服务时同时提交独立买家验收器、坏样本和失败成本测试。
3. 运行 `python -m unittest discover -s tests -v` 和 `python -O -m unittest discover -s tests -q`。
4. 如改变示例行为，运行 `python -m virtual_trade_lab --json > docs/demo-evidence.json` 并解释变化。
5. 不得把模拟成交或积分称为真实营收；不要提交凭据、个人数据或真实客户数据。

当前命令处理器不是安全边界。生产级持久化、并发、鉴权或支付接入需另行设计、威胁建模和审计，不应只替换一个网络接口就宣称可商用。
