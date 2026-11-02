# 三方向原型试跑（不是业务验收）

## 实际可交付

- [可编辑五页宣传 PPT](../examples/product-run/promo.pptx)：虚构「纸舟计划卡」，原创文案/版式/原生表格。模板已逐页视觉检查；后续 CLI 仅替换 1–12 字产品名，不是通用 PPT 设计引擎。**视频渲染未实现**。
- [直播彩排脚本](../examples/product-run/livestream-script.md)、[时间表](../examples/product-run/run-sheet.csv)、[事件记录](../examples/product-run/livestream-events.json)：180 秒离线彩排，包括提问、库存未知、中断恢复、停止。没有开播、观众或真实观看时长。
- [虚拟买卖/渠道体验](../examples/product-run/channel-experience.json)：明确标记的虚构买家、卖家、渠道；不是实际投放或真实订单。
- [交付清单/哈希](../examples/product-run/manifest.json)、[完整模拟流水](../examples/product-run/campaign.json)。三种状态分别记录：确实生成文件、规则买家验收、真实市场验证。前两者不能替代第三者。

## 复现

```sh
python -m virtual_trade_lab.products --output /tmp/product-run
python -m virtual_trade_lab.products --output /tmp/product-run-again
diff -qr /tmp/product-run /tmp/product-run-again
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -q
python -m unittest discover -s examples/refund-regression -v
python examples/refund-regression/demo.py
```

Windows 请使用自己的临时目录及文件比较工具。CLI 不联网；初始 PPT 作者服务不是开源运行时组件，交付模板后实例化只用 Python 标准库。不同字体/编辑器及更长替换名称仍须人工检查排版。

## 固定设计与结果

预先固定三方向 × 六种情况 × seeds 0–4 = 90 案例。seed **只改变预算余量**，不是独立市场样本，更不是学习的用户模型。全部 seed 保留，无择优。六种情况：正常接受、先缺陷后修复、重复缺陷拒收、预算不足取消、付款后取消、重复崩溃退款。每种情况每方向 5 次。

本次 90/90 达到设计期望：30 接受（含15次返工成功），30 拒收（含15次崩溃退款），30 取消（含15次预算不足）。每条命令使用相同幂等键重放并比较回执；每例最终模拟积分总量130，交付成本扣除后归入成本账户，不消失、不等于真实支出。拒收是预期拦截，不是为了展示高转化而删除的失败。

买家读取真实文件与 SHA256，检查声明、PPT结构、彩排阶段/时序、虚构标识及禁止的营销断言；不采信卖家自报成功。局限：检查器不是完整自然语言真实性审查或通用恶意 Office 文档检测器；结构检查不代替视觉检查。测试只针对受控原创模板和有限故障。

退款回归另跑17项：丢响应、重复请求、重启、延迟权威读取、乱序/重复事件、永久缺失终态 webhook 后恢复读取。固定演示中不安全基线退款两次4000单位；持久化操作身份路径一次2000单位。这是原创有限提供商模拟，不是对任何支付平台执行测试或证明生产修复。

## 没有通过的业务门槛

真实付费需求、真实自愿观看、相对明确替代品的优势、长期净经济性/复用、合法经营资格：**全部未评估**。本轮没有真实客户、真实观看、真实收入或成本调查；不能称作 sim2real 对齐、优于现有产品或可持续业务。下一实验应测试替换合理行为模型是否翻转结论，而非增加模拟轮数；真实验证须另行授权。见[业务验证协议](BUSINESS_VALIDATION.md)。

## 行为模拟（与90个机械案例分开）

```sh
python -m virtual_trade_lab.realism --output /tmp/realism.json
```

结果保留在 [realism.json](../examples/product-run/realism.json)，设计、假设、结构控制与局限见[模拟验收协议](BUSINESS_VALIDATION.md)。它允许产品输给外部选择、无人观看、退款、负净额，不把预定状态测试冒充逼真的商业表现。

本轮行为模型输出（重复使用相同cohort的seed×条件配对，并非独立样本）：开发集24个seed×条件对比中候选净额胜6/负17/平1，范围−41至+53模拟积分；原预留集（已消耗）36个对比胜2/负34，范围−61至+48。不能据此宣称候选优于现有产品；结论只说明在这些假设下增加清晰度/质量并提高价格/制作成本并不稳健获利。不是市场效应估计。

v2是在检查v1结果及独立模型复核后修订的探索性重跑，修复复购仍相信旧质量承诺的问题。不能将原holdout继续称作新版本独立验证。完整模型源码哈希与控制参数已纳入输出config_sha256。

## 最终本地检查

107项主测试（含12项产品交付和8项行为模型测试）在正常与`-O`模式均通过；17项退款回归通过，旧演示/退款哈希及JS语法检查通过。第二目录重新生成的所有产品/模型文件逐字节一致。独立模型复核另跑8项行为测试，并重算全部输出与保留JSON完全一致；不把该窄复核宣称为独立跑过全部测试。远端CI以对应发布提交的运行结果为准。
