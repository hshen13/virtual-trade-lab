# v0.3 增量验证 · 2026-11-01

- 主套件 **87/87 通过**（原 61 项 + 实验证据登记 26 项），普通及 `python -O` 均通过。
- 独立退款回归样例 **15/15 通过**；独立执行 demo 与 `SHA256SUMS` 检查通过。这不是外部支付系统测试。
- 实际 CLI 完成 campaign → 合成 import → 相同 import 重放 → simulation_calibration prediction → freeze → report；真实观察为空，最终 **not_evaluated / not_completed**。可运行 `python examples/synthetic_experiment.py` 重现。
- 实验指南中的临时库无数据命令示例也已运行，仍为 not_evaluated。
- 强制 source/evidence identity、固定主体分组、冻结前瞻队列/观察窗、未结束随访、零分母、退款关联、全局重复付款/成本记录、输入格式及数据库事件摘要错误均有测试。
- 持出解析测试使用**生成的合成夹具和测试时钟**，从未收集或声称持有真实买家/付款样本。
- 独立方法审查修复了晚到退款人数计数、带时区金额截止比较、无容差仍可输出描述性误差三处报告边界问题。仍不验证因果性、真实来源、对象独立性或成本完备性。
- 当前增量仅 CLI/文档/测试，无 Web 行为更改。本轮未重新做人工浏览器全流程；下方 v0.2 浏览器记录为历史验证，不冒充本轮新测。
- 未调用真实支付、模型、获客、注册或发帖接口；未做收入或合法性认证；没有真实客户验收、独立收款证据或预算承诺。

以下为保留的 v0.1/v0.2 验证记录，测试数量以本页上方最新增量为准。

# 验证记录

## 执行范围

2026-10-31，在助手的云端工作区执行；未使用用户电脑、Docker、付费 API、真实支付服务或社交账号。测试运行版本见 `test-output.txt`。以下属于本地验证，不代表远端 CI 或真实业务验证。

```sh
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -q
python -m compileall -q virtual_trade_lab tests
python -m virtual_trade_lab --scenario all --json > docs/demo-evidence.json
```

本次实际运行：**Python 3.12.14**。

v0.2 最终版本：**61 个测试全部通过**（原内存交易 26 项 + 持久化 23 项 + HTTP 12 项），普通模式和 `-O` 优化模式均通过。编译检查通过；六场景 CLI 输出是合法 JSON。另已通过 `pip install --no-deps --no-build-isolation --target <临时目录> .` 构建/安装检查，并从仓库外运行安装后的 happy 场景。

标准测试含固定种子下 30 个市场、1,800 条状态转换命令，验证失败原子性和每一步完整性。

独立审查另外运行了 100 个市场、10,000 条随机命令：1,535 次成功、8,465 次原子拒绝；逐步重放账本与所有余额一致。此审查发现并修复三个边界问题，并纳入最终回归测试：

1. action/mode 非字符串导致裸 TypeError → 明确验证并返回 TradeError。
2. 验收器持有的问题列表可能事后被修改 → 存储隔离副本，事件保留历史证据。
3. Python `-O` 会禁用 assert → 改为显式运行时检查，并增加逐笔账本重建校验。

## 失败不是假装成功

| 注入条件 | 预期行为 | 证据 |
|---|---|---|
| 首次交付改动商品价格 | 独立买家要求返工 | `revision` 的 review 事件包含 `product price changed` |
| 连续两次改动价格 | 终态 rejected，买家本金全退 | `reject` 中 buyer=100 / seller=22 / provider=8 |
| 连续两次卖家异常 | 保留两次成本后拒收退款 | `crash` 的 `seller failure: RuntimeError`，成本 8 |
| 报价超过预算 | fund 拒绝，没有转账 | `budget` 流水为空 |
| 卖家成本余额不足 | 交付命令整体不生效 | 自动测试 `test_insufficient_seller_cost_is_atomic` |
| 对 delivered 取消 | 拒绝，必须先验收 | 自动测试 `test_invalid_transitions_are_atomic` |
| 相同幂等键换请求 | 冲突拒绝，无资金或状态变化 | 自动测试 `test_key_conflicts_do_not_mutate` |
| 买家评估器抛异常 | 验收回滚，保持待验收和托管余额 | 自动测试 `test_evaluator_error_rolls_back_review` |
| 不改动商品事实但标题超出买家长度限制 | 正常卖家输出也可被拒收 | 自动测试 `test_buyer_can_fail_normal_seller` |
| 无日志偷偷修改买卖余额、总量仍不变 | 账本重建检查报错 | 自动测试 `test_invariant_detects_conserved_but_unjournaled_mutation` |

JSON 的每条 journal 记录都有 `from`、`to`、`credits`、订单与原因。每次完整性检查从初始余额重新执行全部流水，检查中间无透支，最终等于账面余额。这里只模拟内部可信程序，不意味着真实世界抗篡改或银行级安全。

## 尚未验证 / 不支持

- 未运行远端 GitHub Actions；Python 3.10、3.11、3.13 是否通过需以实际 CI 结果为准。
- 无真实模型调用、客户试用、订单、现金收入或真实算力成本测量。
- 已测试 SQLite 本地保存、重启恢复、事务失败回滚、并发写入冲突和跨重启幂等。未测试断电/硬件故障、跨机器幂等、生产安全或负载性能。
- 无不可信插件隔离；适配器必须无外部副作用。评估器坏掉会使订单停留在待验收状态，当前只能由宿主修复评估器后重试，没有仲裁后台。
- `docs/demo-evidence.json` 是可重放的合成演示输出，不能用作真实成交证明。


## v0.2 本地 Web 与持久化增量

- `tests/test_storage.py`：重启与丢失响应重试不重复扣款；同键冲突；不同 Store 实例竞争；同请求并发；陈旧版本/实验隔离；重置保留旧记录；SQLite 写入中止原子回滚；无效文件、空文件、截断文件、错误摘要、删除命令尾部均拒绝继续。
- `tests/test_server.py`：真实临时 loopback HTTP 测试；主机名、来源和令牌验证；非 ASCII 令牌拒绝；400/409/503；JSON 类型、深层嵌套与大小限制；路径遍历阻止；HTML/JS/CSS 静态资源存在。
- Web 请求限制 64 KiB；每实验最多 1,000 条成功命令。重放每次检查历史，适合小实验而非大量订单。达到上限后可明确创建新实验；旧数据保留，占用磁盘不会自动清理。
- SQLite `BEGIN IMMEDIATE` + `synchronous=FULL` 将命令、序列和末端摘要原子提交。摘要用于发现意外损坏或版本漂移，不是防止有文件写权限的攻击者篡改。
- 第一次创建数据库时若中断留下空文件，会拒绝自动覆盖；保留检查后自行选择新路径。现有不兼容版本同样需要显式迁移。
- 静态文件安装后可用性和仓库外 CLI 检查通过；JS `node --check` 与 Python 编译检查通过。运行 UI 本身不需要 Node。
- 实际浏览器测试见 [UI_QA.md](UI_QA.md)。未部署网站。
