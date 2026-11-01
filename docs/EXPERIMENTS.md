# 实验与证据登记：sim → real → sim

这个 CLI 将**模拟、用户声明的观察、独立外部验证**分开记录，避免把模拟成交当成真实需求或收入。它是本地实验登记器，不是市场数据采集器、支付验证服务、法律认证或训练好的预测模型。

**当前仓库没有真实客户数据、真实付费成交或已验证收入。** 本文的默认演示不导入任何事件；预测只是人为设置的玩具基线，报告应保持 `not_evaluated`、总体目标 `not_completed`。

## 三种证据不能混称

| 层级 | 在本工具里的含义 | 不能据此声称 |
|---|---|---|
| `simulated` | 合成或规则模拟生成的事件 | 真人购买、真实现金收入、商业需求已验证 |
| `observed` | 用户自行导入、声明为观察到的事件 | 工具独立核实了来源、买家身份或付款真实性 |
| 独立外部验证 | 当前尚未提供；需另行取得与核对可授权使用的证据 | 改一个 domain 字段或填写 evidence_ref 就完成验证 |

`observed` 是**声明标签**，不是认证。工具不会访问 `evidence_ref`、核对银行收据、联系买家或核查合法经营资格。自动测试中即使走到 `observed` 解析分支，所用记录也是测试生成的合成夹具，不是真实观察证据。

## 闭环的顺序与边界

1. **sim：提出假设。** 从规则模拟或明确标注的人工假设开始，定义需要预测的目标。本版固定目标是“观察截止前验收通过的被曝光对象 / 全部被曝光对象”。
2. **预先登记。** 建立 campaign，声明货币、校准截止、留出队列曝光截止、观察截止、队列对象 ID、最小样本量；如要作阈值判断，必须同时给出容差与理由。
3. **校准并冻结。** 生成一个有版本号的预测，冻结一个主版本。冻结必须发生在校准截止之后、曝光截止之前。此后不能继续修改该 campaign 的校准数据或主预测。
4. **real：接收后续观察声明。** 留出对象必须预先列入队列，实际事件时间必须在冻结之后；不能把冻结前发生的事件晚一点导入就称为前瞻验证。曝光事件不能晚于预登记曝光截止。
5. **等待完整随访并比较。** 观察窗口结束、队列完整、随访关闭、漏斗质量检查通过后，才具备比较条件。真实来源与外部有效性仍未被认证。
6. **回到 sim：提出下一轮假设。** 查看误差、拒收、退款和成本，建立下一轮 campaign。需要**新的真实队列**评估新的假设。给旧样本换 ID，或者复制到新 campaign，不会让它成为独立留出集。

这套流程支持有纪律的证据接收，不会自行发现客户、自动成交或证明盈利。

## 默认无数据演示：可以直接运行

从仓库根目录执行以下 Bash 命令。只需要 Python 标准库，不需要 token、联网、Docker 或付费 API。用临时目录避免覆盖已有登记库；每次运行都会建立一个独立演示目录。

```bash
DEMO_DIR="$(mktemp -d)"
DB="$DEMO_DIR/experiments.sqlite3"

# UTC：校准昨日结束，曝光窗口再开放 14 天，观察窗口再开放 30 天。
read -r CALIBRATION_END EXPOSURE_END OBSERVATION_END < <(
  python - <<'PY'
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
print(*( (now + timedelta(days=d)).isoformat() for d in (-1, 14, 30) ))
PY
)

python -m virtual_trade_lab.experiments --db "$DB" campaign toy-no-data \
  --currency USD \
  --calibration-end "$CALIBRATION_END" \
  --exposure-end "$EXPOSURE_END" \
  --observation-end "$OBSERVATION_END"

python -m virtual_trade_lab.experiments --db "$DB" predict toy-no-data \
  --method manual --probability 0.20 \
  --rationale '玩具人工假设；没有学习、没有真实数据、没有市场依据'

python -m virtual_trade_lab.experiments --db "$DB" freeze toy-no-data --version 1
python -m virtual_trade_lab.experiments --db "$DB" report toy-no-data
printf '演示数据库保留在：%s\n' "$DB"
```

这个例子**不导入事件，也不声明真实留出对象**，不设置 tolerance。人工的 `0.20` 不是学习结果、行业平均值或有证据支持的概率。默认 `min_holdout=30` 是程序参数，不是经功效分析证明充分的样本量。

预期报告：

- `evaluation.status` 为 `not_evaluated`；没有真实留出观察声明可评估。
- `groups.observed` 与 `groups.simulated` 的事件/曝光相关计数均为空数据状态；无分母时比率为 `null`，不是“0% 市场转化率”。
- `overall_goal` 为 `not_completed`；验收、独立收款验证、完整成本、法律资格四个完成条件仍未解决。

未指定 `--db` 时，默认保存至 `.virtual-trade-lab/experiments.sqlite3`。它独立于互动交易演示的模拟积分账本；导入货币记录不会给模拟买家或卖家充值。

## 事件输入：严格相同的 JSON / CSV 字段

`import` 接受 `.json` 或 `.csv`，UTF-8（允许 BOM），文件不超过 5 MiB，一次 1–10,000 条事件。JSON 顶层必须是数组。CSV 第一行必须是完整且不重复的字段名；字段顺序可不同。**不能缺字段或增加额外字段。**

| 字段 | 约束 / 用途 |
|---|---|
| `event_id` | 唯一不透明事件 ID；完全相同的重复导入被忽略，内容不同则整批拒绝 |
| `campaign_id` | 已存在的 campaign ID |
| `subject_id` | 稳定的不透明客户/相关事件组 ID；相关客户事件不能另起 ID 拆入不同分组；本版每组每 campaign 仅建模一次机会 |
| `domain` | 严格为 `observed` 或 `simulated` |
| `partition` | 严格为 `calibration` 或 `holdout` |
| `event_type` | 见下方事件类型；一个对象最多一个终局决定 |
| `occurred_at` | 带时区的 ISO 时间戳，如 `2026-01-01T12:00:00+00:00`；observed 不能是未来时间 |
| `amount_minor` | 最小货币单位整数，范围 0–10¹²；paid/refunded/cost 必须大于 0，其余必须为 0 |
| `currency` | 与 campaign 一致的三位大写声明代码，如 USD；没有汇率转换 |
| `source_id` | 不透明来源 ID；只是来源标记，不是认证 |
| `evidence_ref` | 非空的逐条证据引用，长度 1–512，首尾不能有空白；同一 source_id + evidence_ref 不可用另一个 event_id 重复导入 |
| `transaction_id` | paid/refunded/cost 必填不透明交易引用；非金额事件必须为 `""` |

本版无法从匿名 ID 识别隐藏的同一客户。提交者必须将同一客户及相关事件保持同一稳定分组；不能为了避开终局限制而换 ID。多订单复购、家庭/组织关联及群组相关性需要另行预声明的结果模型，本版不宣称支持。

ID 格式：首字符是 ASCII 字母或数字，其余可用 ASCII 字母、数字、`_ . : -`，总长 1–128。**使用随机或内部不透明 ID，不要填写姓名、邮箱、电话，也不要用这些个人信息的哈希冒充匿名化。** 原始证据应留在有适当权限的来源中；不要在引用里嵌入凭据、个人资料或未经授权的客户数据。格式检查并不保证隐私合规。

### JSON 结构样例：仅合成记录

以下只是展示格式，明确 `simulated`，不是观察数据或成交证据；campaign 必须先存在。

```json
[
  {
    "event_id": "synthetic-event-001",
    "campaign_id": "synthetic-schema-demo",
    "subject_id": "synthetic-subject-001",
    "domain": "simulated",
    "partition": "calibration",
    "event_type": "exposure",
    "occurred_at": "2026-01-01T12:00:00+00:00",
    "amount_minor": 0,
    "currency": "USD",
    "source_id": "synthetic-fixture",
    "evidence_ref": "synthetic-record-001",
    "transaction_id": ""
  }
]
```

对应 CSV：

```csv
event_id,campaign_id,subject_id,domain,partition,event_type,occurred_at,amount_minor,currency,source_id,evidence_ref,transaction_id
synthetic-event-001,synthetic-schema-demo,synthetic-subject-001,simulated,calibration,exposure,2026-01-01T12:00:00+00:00,0,USD,synthetic-fixture,synthetic-record-001,
```

CSV 金额必须是十进制整数文本：`0` 或不带前导零的正整数；不接受 `1.5`、`1e3`、`+1` 或空值。JSON 金额必须是真正的整数，不能用字符串、浮点数或布尔值代替。

导入已准备且有权使用的文件：

```bash
python -m virtual_trade_lab.experiments --db /path/to/registry.sqlite3 import /path/to/events.json
# CSV 使用同一个 import 命令。
```

每批导入是原子的：任一冲突或非法记录使整批回滚。完全相同事件可安全重试；不同 ID 不代表可以重复使用同一条证据。

## 漏斗、终局和随访关闭不是一回事

漏斗阶段依次为：

```text
exposure → interest → quote → order → paid → fulfilled → accepted
```

此外支持 `rejected`、`cancelled`、`refunded`、`cost`、`followup_closed`。

- 以**唯一对象数**而不是事件行数计数。每一阶段同时显示原始人数、完成此前所有阶段的合格人数和明确分母；缺前序阶段或阶段时间乱序会产生质量问题，不会悄悄填补漏斗。
- `accepted`、`rejected`、`cancelled` 是终局决定。每个对象最多一条；不应为了关闭随访，把“到观察截止仍未转化”伪造为“买家取消”。
- `followup_closed` 表示已完成该截止窗口的随访，**不是成交，也不是取消**。关闭时间必须在对应统计截止时间或之后，才会计入该窗口的关闭标记。零转化对象也要保留曝光并关闭随访，不能从分母中移除。
- 即使已有 accepted/rejected/cancelled，仍需要合格的 `followup_closed` 才不属于待随访对象；否则晚到的结果或费用可能被误当作不存在。
- 校准窗口使用 `calibration_end`；留出窗口使用 `observation_end`。漏斗和主验收率仅使用截止时间内的事件。截止之后的 accepted 单列 `late_acceptance_subjects`，不倒填主要验收率。
- 金额汇总使用**所有已导入的金额事件**，不因观察截止而丢掉晚到的退款与成本。`money_as_of` 标出已导入事件的报告时间信息；它不是银行结算时间或凭据核验时间。晚到退款不把既有 accepted 事件改成 rejected，但会减少声明净额。

## 交易引用与金额：声明值，不是已验证收入

- `paid` 的 `transaction_id` 在整个登记库中不可重复，包含跨对象和跨 campaign；请使用带来源命名空间的 ID。
- `refunded` 必须引用该对象此前已记录的 paid 交易，时间不能早于付款；同一付款的累计退款不能超过付款金额。
- `cost` 使用自己的不透明成本记录 ID，同样在登记库中全局去重；退款可以多次引用同一付款以支持部分退款。格式与去重不能阻止恶意重命名或伪造来源。
- 报告分别显示声明收款、退款、成本、退款后净收款，以及减去已声明成本后的净值。
- **没有 cost 事件不等于真实成本为零。** 税费、人工、获客、平台费等可能未知或未覆盖；`cost_coverage` 因此明确保持 unknown。
- 声明货币数额不等于核实营收。真实买家验收、独立收款证明、完整成本账和法律资格仍分别是 `unverified` / `unresolved`，没有自动完成按钮。

## 预测快照与“是否接近”的判断

`predict` 每次创建递增版本并保存理由、校准事件 ID、校准内容 SHA-256 摘要和样本信息。这里摘要用于记录**事件集合版本**，不是用于对个人信息做哈希匿名化。

| method | 行为 |
|---|---|
| `manual` | 必须明确提供 0–1 的 `--probability` 与理由；只是声明基线 |
| `simulation_calibration` | 从 simulated/calibration 的完整队列计算验收比例 |
| `observed_calibration` | 从 observed/calibration 的完整队列计算验收比例；数据仍是用户声明 |

经验方法不接受额外的人工 probability；要求非空曝光队列、随访完整、漏斗无质量问题。得到的是**经验队列比例快照，不是训练好的通用模型**。冻结前如校准事件变化，必须重新生成预测版本；不能冻结旧数据快照。冻结之后不能再选另一主版本。

报告的 `observation_snapshot` 含事件集合 SHA-256 版本、数量和事件 ID；相同导入重试不改变版本，新增观察会产生新内容版本。它是可追踪的当前快照，不是已提供历史报告浏览/纠错系统。

真实留出队列通过 `campaign --holdout-subjects <JSON文件>` 预先登记，文件内容为不透明 ID 数组。观察事件的 holdout 对象必须在该列表内；不能同时进入校准。任何 holdout 事件导入之前都必须先冻结预测。模拟与观察不合并，校准与留出不互换。

报告状态的含义：

- `not_evaluated`：没有冻结预测或没有观察留出证据。
- `insufficient_data`：最小样本、完整预登记曝光队列、全部随访关闭、有效漏斗或完整观察期限等条件未满足。
- `unassessed`：数据条件达到，但没有预先给出有理由的 tolerance；仅报告描述性估计。
- `within_declared_tolerance` / `outside_declared_tolerance` / `inconclusive`：比较观察比例的 Wilson 95% 区间与“预测 ± 预声明容差”；区间完全位于容差带内、完全不相交或其余情况。

只有在创建 campaign 时显式设置 `--tolerance` 并提供 `--plan-rationale` 才启用容差判断；没有默认的任意“已对齐”判定。理由是提交者自述，软件并未独立审查其科学充分性。最小样本量、容差和队列设计应有事先说明的依据；区间假设对象相互独立，不保证因果关系、外推有效性或数据真实性。报告中的绝对误差和 Brier score 也不能替代这些验证。

## 保存、冲突与纠错限制

登记库使用本地 SQLite 事务。没有自动删除、reset 或清洗历史操作；数据库无效时停止并提示保留文件，不自动用空库替换。导入本身不是不可篡改审计系统，拥有本地文件权限的人仍可破坏数据库。

当前 campaign 定义不可改写，已有 event_id 的冲突修正会被拒绝。**尚无撤销/更正记录协议。** 发现错误时应保留原始库及原始来源，停止依赖受影响报告，记录问题，并通过未来有审计记录的人工纠错流程处理；不要删库重来、偷偷改 SQL 或换 ID 重复导入来制造“干净证据”。

新 campaign 可用于新的假设与新的真实队列，但不能清除已发生的信息泄漏或把反复使用的留出集变成独立验证。软件的形式检查不能阻止所有人为重标记；这种边界必须在报告中如实披露。
