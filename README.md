# Virtual Trade Lab · 虚拟交易实验室

**用可复现的虚拟买家、卖家和交易流程，检验“服务交付—独立验收—结算/退款”是否正确，而不是制造虚假收入。**

这是一个零付费 API、Python 标准库即可运行的开源 MVP。核心交易引擎参与者是**确定性规则程序 / mock 角色**；另附已保存的模型角色购物实验与只读退款回放，不能混称自主交易系统。没有真实付款，没有真实客户，没有真实社交账号，也没有自动宣传功能。

## 退货要有收件证据

[一页中文概览](examples/return-custody-model-study/overview.html)：3份实际模型回应分别申请、审核、选择交回。批准后仍托管，匹配的模拟收件证据到达才退32；卖家承担总费用8。购买初态与物流是明确标注的脚本条件，不冒充新模型决策或真实寄件。

## 交互式模型购物与退款回放

运行 `python -m virtual_trade_lab.server`，打开终端显示的 `/replay` 地址。页面用6步展示商品、模型决定、托管、交付、预设错装和实际模型拒收退款；可播放、跳转、展开原文与积分转移，只读、不再次执行交易。

数据来自已封存的缺陷退款实验，不是新编对话。HTTP、数据与DOM替身交互测试已通过；当前环境阻止Chromium启动，**尚未完成浏览器视觉验收**，没有对手机布局或截图作已验证承诺。详见[回放运行与验证说明](docs/REPLAY_UI.md)。


## 三轴校准准备（仅设计）

[同真实产品校准虚拟用户、真实/虚拟孪生校准产品、逐产品校准价格](docs/CALIBRATION_PROTOCOL.md)：元数据协议和防误报检查已实现；参与者数据未导入、模型未运行、9项证据门槛均未满足。`python -m virtual_trade_lab.calibration_protocol` 只检查设计，不能判定已校准。

## 外部基线复现

已实际运行[BazaarBench官方离线20角色×50tick测试](examples/bazaar-reproduction/README.md)，两次通过、0LLM调用；**两次都无完成交易，且同seed轨迹不一致**，保留限制和失败证据。这是上游scripted基础设施复现，不是论文LLM结果或最强模型复现。

## 项目进度

进度面板源数据 [progress/status.json](progress/status.json) 是人工更新的真实工程进度快照，不是自动经营监控。面板每30秒读取最新快照并显示更新时间，不伪造实时收入或完成百分比。

## v0.4：三个产品方向，仍未通过真实业务验收

1. **宣传 PPT**：生成真实可编辑五页原创模板实例；视频渲染尚未实现。
2. **直播**：生成离线彩排脚本、时间表、模拟中断恢复；没有开播或真实观众。
3. **买卖货/渠道体验**：虚构角色的预算、交付、独立验收/返工/拒收/退款；没有真实货款、投放或库存。

```sh
python -m virtual_trade_lab.products --output /tmp/product-bundle
```

打开生成的 `promo.pptx` 和 `livestream-script.md`；`manifest.json` 区分真实文件、mock验收和未验证市场。示例[直接下载PPT](examples/product-run/promo.pptx)，[完整运行报告与交付](docs/PRODUCT_RUN.md)，[紧凑项目总纲](PROJECT_PLAYBOOK.md)，[真实业务验收协议](docs/BUSINESS_VALIDATION.md)。这里是本地 CLI 交付；下方 Web UI 仍是交易基础设施演示，尚未集成三方向编辑器。

**当前先追求诚实的逼真模拟**：异质偏好/预算、外部选择、不购买、观看疲劳、退款/复购、全成本和共同条件下的基线对比；`python -m virtual_trade_lab.realism --output /tmp/realism.json` 跑固定敏感性格子。90个交易规则案例不等于行为真实性。现实付费/观看/优势/持续性/合法资格仍未评估。 不用虚拟转化率或伪造收入作弊。样例含明确「虚构示例」；[来源与许可边界](docs/PROVENANCE.md)。

## 思路与目的

先把交易中容易被“成功演示”掩盖的问题暴露出来：

- 买家有自己的预算、验收条件和返工上限，不能由卖家宣布自己合格。
- 卖家先报价，再交付；不合格会返工或拒收，程序崩溃也有模拟成本。
- 只有验收通过，托管式模拟账户才向卖家释放积分；拒收/取消退回本金。
- 所有积分转移有流水，余额非负且总量守恒；重复请求不能重复付款。

**能验证：** 受控输入下的流程正确性、失败处理、成本与净变动的计算、可替换服务接口。

**不能验证：** 真实购买意愿、获客成本、服务市场需求、盈利能力、模型智能水平或真实支付安全。“模拟卖家净增 16 积分”不是“赚了 16 元”。

示例选择“商品目录空白清理”，只是因为它容易提供客观验收：保留 SKU、价格、商品描述内容，仅规范空白。**这不是已确认的商业方向，也不是来自真实客户的需求证据。**

## 30 秒运行

需要 Python **3.10+**。在仓库根目录执行；不需要 Docker、token、联网、pip install 或任何 API key。

```sh
python -m virtual_trade_lab
python -m virtual_trade_lab --scenario revision
python -m virtual_trade_lab --scenario all --json
python -m unittest discover -s tests -v
```

`python` 不存在时请替换为 `python3`。可选安装 `python -m pip install .` 后使用 `virtual-trade-lab`；安装构建工具可能联网，但直接运行以上命令不需要。

## v0.3：把模拟与现实证据分开，而不是宣称已对齐

新增独立的本地实验登记 CLI：`python -m virtual_trade_lab.experiments --help`。

- 只接收用户提供的非敏感匿名 JSON/CSV；强制来源引用，区分 `simulated` 与 **用户声明的** `observed`，不把输入标签当作独立验证。
- 预先冻结队列、观察窗、分母、预测版本和有依据的容差；校准与留出不混用，旧事件晚导入不能冒充前瞻观察。
- 没有真实证据时为 **`not_evaluated`**；没有预声明容差时为 `unassessed`。有样本也要披露未结束随访、区间不确定性和来源未核实。
- 分开显示验收、取消、退款和减去已声明成本的净额；不将声明金额叫作已验证收入。
- 真实买家验收、独立真实收款、完整成本、法律资格四个门槛仍未完成。软件不认证合法性，也不能代替真实买家验证。

完整说明、字段和可运行无数据示例：[实验登记指南](docs/EXPERIMENTS.md)。[合成演示报告](docs/experiment-example-report.json)只有两名模拟对象，真实观察数为零，仍为 `not_evaluated`，不能作商业证据。

另加入[丢失响应退款回归样例](examples/refund-regression/README.md)：参考公开报告的问题、独立编写的**纯模拟**正反例，测试持久化操作身份、延迟读取和重启恢复；不是运行 Adyen 当前产品、不是已证明修复、没有付费客户或预算。它与现实观察登记隔离，不自动导入为 observed。

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s examples/refund-regression -v
python examples/refund-regression/demo.py
python examples/synthetic_experiment.py  # 仅合成数据，预期 not_evaluated
```

## 可交互的本地实验台（v0.2）

```sh
python -m virtual_trade_lab.server
# 浏览器打开 http://127.0.0.1:8765
# 可选端口和独立实验文件：
python -m virtual_trade_lab.server --port 8766 --db .virtual-trade-lab/another.sqlite3
```

仅绑定 `127.0.0.1`，不是公网服务器；不需要 Node、Docker、API key。仓库中的 `package.json` 只供云端预览工具调用同一个 Python 命令，不是运行依赖。

1. 设置买家预算、返工次数、标题长度和合成商品 JSON，点击报价。
2. 查看报价，再锁定模拟积分；卖家选择正常、错误价格或崩溃交付。
3. 点击独立买家验收，观察通过/返工/拒收、退款及实际流水。
4. 刷新或关闭服务后使用**同一个数据库路径**重启，可恢复订单和幂等记录，不重复扣款。
5. “新实验”需确认：创建新的独立 130 积分实验，旧实验数据保留在 SQLite 中，不是凭空向原账本加钱。界面只展示当前实验；旧实验目前没有浏览/导出界面。

默认文件为当前目录 `.virtual-trade-lab/state.sqlite3`（已被 Git 忽略）。请只输入非敏感合成数据；数据库是未加密本地文件，没有用户账号隔离。停止服务后备份整个文件；不要在服务运行时复制或编辑数据库。

### 保存、重复点击与多标签页

- 每次成功命令及其状态校验摘要由 SQLite 事务一次提交；请求返回前已提交。
- 恢复时从初始积分重放确定性命令并核对逐步摘要、命令序列和末端 revision，**不是向旧余额再次转账**。修改适配器逻辑或升级数据版本需要显式迁移，不会静默接受不同结果。
- 同一成功请求键跨重启重试不产生第二笔转账。按钮执行时禁用，网络结果不确定时保留原请求以便重试；刷新/浏览器后退不会执行交易。
- 版本号与实验标识校验阻止旧标签页继续操作或将旧请求应用到新实验。多个请求由 SQLite 写事务串行处理；过期请求返回冲突，须刷新后再决定。
- 数据库损坏、缺行或重放不一致会拒绝继续，**不会自动清空或补发积分**。保留文件用于检查；如只需新的实验，显式选另一个 `--db` 路径。
- 重启服务会更换浏览器会话令牌；先刷新状态再用保留的原请求重试。不同浏览器/标签页不能共享尚未提交的界面请求缓存，但已提交请求键保存在数据库。

本地 HTTP 层带 Host、同源和会话令牌检查，但不构成生产认证或安全审计。可信本机程序仍可访问数据。本地持久化只支持自带的 catalog-v1 确定性适配器；内存 `Market` 仍可替换其他服务。

## 看什么结果

每个场景从独立的 100 买家积分 + 30 卖家积分开始；供应方初始 0。

| 场景 | 路径 / 原因 | 总交付成本 | 卖家净变动 |
|---|---|---:|---:|
| happy | 正常交付，验收通过 | 4 | +16 |
| revision | 首次故意改错价格，返工后通过 | 8 | +12 |
| reject | 两次改错价格，拒收退款 | 8 | -8 |
| cancel | 付款后、交付前取消，全退 | 0 | 0 |
| budget | 报价 20 超过预算 5，不付款 | 0 | 0 |
| crash | 两次注入卖家异常，拒收退款 | 8 | -8 |

**全部为模拟积分，不可充值、提现、兑换或转账。** 商品字段 `price_cents` 是待清理的数据，不是本系统真实成交金额。服务报价为 `10 + 5 × 行数`，每次交付成本为 `2 + 行数`；这两个公式是人为设定的实验参数，不是市场定价或真实算力成本。provider 是模拟成本接收方，因此成本不会凭空消失。

示例输出：

```text
[revision] quoted → funded → delivered → revision_requested → delivered → accepted
  报价 20 | 成本 8 | 卖家净变动 +12
  积分守恒 130 = 130
  失败/返工证据: CUP-01: product price changed
```

[完整 JSON 演示证据](docs/demo-evidence.json)包含交付、买家问题、逐步事件和双向积分流水；运行 CLI 可自行再生成。历史失败原因保留在事件里，不会被后一次合格交付覆盖。

## 交易规则

```text
quoted ──fund──> funded ──deliver──> delivered ──review/pass──> accepted
   │               │                  │
   │               │                  └─review/fail─> revision_requested
   │               │                                       │  │
   │               │                         deliver <─────┘  └─cancel──> cancelled
   │               │
   └─cancel────────┴─cancel──> cancelled

delivered ──review/fail（返工次数耗尽）──> rejected
```

- `fund` 检查报价不超过预算且买家余额充足；积分进入该订单独立的 `escrow:<id>`。
- `deliver` 由卖家预付本次成本。余额不足则整条命令不生效，可取消退本金。卖家运行异常则记为失败交付，成本照计，交给买家决定返工或拒收。
- `review` 只有独立买家评估器能决定结果；默认最多返工一次（最多两次交付）。
- `cancel` 仅允许报价中、已付款但尚未交付、等待返工三种状态；已交付必须先验收，已终结不能再操作。
- 拒收和取消只退服务本金，已消耗的卖家计算成本不会退还。
- 每条成功命令使用唯一幂等键。同键同请求重试返回原收据，不重复执行；同键不同请求报错。失败命令不占用键，修改状态后可重试。内存 `Market` 的缓存只在当前进程中有效；Web 的 SQLite 包装层会持久化成功请求。
- 命令异常会回滚交易状态。适配器的已计费运行异常是显式失败交付，不是回滚。买家评估器异常回滚验收，保持资金待处理，不能伪装成验收通过。

## 可替换服务，不把目录清理写死为商业模式

引擎 `Market(service, evaluator)` 接受两个互相独立的接口：

```python
from virtual_trade_lab import CatalogBuyer, CatalogSeller, Market

market = Market(CatalogSeller(), CatalogBuyer())
market.execute("quote", "order-1", "request-1", source=[
    {"sku": "A", "title": "  Canvas   bag ", "price_cents": 1999}
], criteria={"budget": 40, "max_revisions": 1, "max_title_length": 80})
market.execute("fund", "order-1", "request-2")
market.execute("deliver", "order-1", "request-3")
receipt = market.execute("review", "order-1", "request-4")
print(receipt["state"], market.balances)
```

- `ServiceAdapter.quote(source) -> Quote`：固定服务积分价格和每次交付成本。
- `ServiceAdapter.fulfill(source, attempt, mode) -> list[dict]`：返回 JSON 交付。`mode` 是当前演示的正常/缺陷/崩溃注入方式，不是生产故障处理 API。
- `BuyerEvaluator.assess(source, result, criteria) -> list[str]`：返回客观问题；空列表才合格。
- 增加服务时同时提供独立验收器和坏样本。不要复用卖家的“我成功了”字段当作验收证据。
- 适配器和评估器必须是可信、确定性、无外部副作用的程序。事务回滚只覆盖引擎内部状态，无法撤销真实 API 调用。本版本并未提供不可信插件沙箱。

测试包含一个 Echo 服务替换示例。未来如加入 LLM，应明确标注模型/版本、实际调用成本、隐私边界和失败样本，不能把规则模拟冒充模型实验。

## 文件与验证

```text
virtual_trade_lab/core.py      状态机、幂等、模拟账本、接口
virtual_trade_lab/catalog.py   示例卖家和独立买家验收器
virtual_trade_lab/__main__.py  六个可读/JSON 演示
virtual_trade_lab/storage.py   SQLite 原子保存、重放校验与版本冲突
virtual_trade_lab/server.py    仅回环地址的本地 HTTP 服务
virtual_trade_lab/web/         无依赖交互实验台
tests/test_market.py          自动化测试
docs/VALIDATION.md            验证范围、失败证据与限制
```

检查余额守恒、非负、逐笔账本重建、订单托管余额、成本和返工次数的完整性检查在 `python -O` 下仍生效。GitHub Actions 配置了 Python 3.10–3.13；本地通过不代表远端 CI 已运行。

## 已知限制与下一步边界

- 单买卖双方；CLI 的 `Market` 是内存模拟，本地 Web 包装层另有 SQLite 保存/恢复和串行写入。没有生产级多用户认证、签名、加密隐私保护或真实支付。
- 无履约超时、仲裁、恶意买家/卖家博弈、物流、税务或跨币种模型；停留在 funded/delivered 的订单不会自动超时。
- 验收标准有限且预设；规则验收器不是对真实质量的通用判断。
- 模拟参与者不是独立真人或生产级代理。无自动注册账号、刷量、刷评价或虚构成交记录。
- 下一阶段应先由真实潜在用户确认一个具体问题并自愿提供非敏感样本，再做有明确指标的小范围试验；没有该证据前，不声称找到了赚钱方向。

贡献欢迎：新服务 + 独立验收器、失败样本、账本/幂等边界测试。请不要提交 token、个人数据或真实客户资料。许可证：[MIT](LICENSE)。

### 退货的钱为什么还没到账？

本地实验台新增 `/returns`，用三个已保存时点展示“批准退货 → 已交回待收件 → 匹配收件后退款”。可点击阶段、展开实际模型原文和账本，查看商品在谁手里，以及返程费用何时扣除。与旧 `/replay` 是独立实验，购买初态和承运事件为脚本，只有三次退货决定来自保留的模型输出。没有新顾客、真实支付或实时物流；未收件、丢件争议仍可能停留在托管。说明见 [回放使用与验证](docs/REPLAY_UI.md)。

### 从宣传入口到真实保留的模型选择

新增本地 `/journey`：[原创文字短剧→商品页→顾客暂缓](examples/channel-customer-journey/README.md)。同一角色两次实际回应均保留，本轮没有进入交易，账本零操作。文字分镜不冒称视频观看，不补造卖家、成交或售后。

### 商品信息补齐对照

本地 `/information` 展示[新一轮双顺序商品信息对照](examples/product-information-contrast/README.md)：尺寸、清洗、错装售后均明示为虚构设计。两个独立模型上下文对原版/补充版的四个决定全为不买；全部原文保留，没有触发卖家或账本。此为开发性小样本，不是真人或因果转化验证。
