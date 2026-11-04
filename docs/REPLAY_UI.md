# 模型购物与退款回放（本地只读）

## 运行

在仓库根目录：

```
python -m virtual_trade_lab.server --port 8765 --db .virtual-trade-lab/ui.sqlite3
```

打开终端打印的 `http://127.0.0.1:8765/replay`。仅绑定loopback，不是公开部署，也不是能从另一台电脑直接打开的公网链接。原规则实验台在 `/`，新增回放入口不改变旧交易操作。

页面提供步骤选择、播放/暂停、前后跳转、范围滑条、当前积分、模型原文和账本明细。URL里的 `#step=N` 保留步骤，刷新/浏览器前后导航可以返回；切出页面会暂停播放。失败时显示读取错误，不操作账本。

## 事实来源与区分

`virtual_trade_lab/web/replay-data.json` 是封存 `examples/defect-refund-model-study/` 的只读投影。构建器核对全部模型回应、冻结提示、保存的计划，并用原Market在内存重放所有命令，要求得到相同账本。它拒绝把旧的成功接受实验渲染成退款。

- 商品、入库检查与错装是预设模拟数据。
- inspect、commit、deliver、refund来自6份实际保存的模型回应，逐字展示。
- 积分显示取自相应命令后的真实模拟状态：初始90/40/0/0，托管58/40/32/0，交付58/36/32/4，退款90/36/0/4。
- 开箱步骤只是对同一交付状态的讲解，不新增转移。六步没有虚构时间戳或实际持续时间。
- 顶部明确是“本次最终结果”；主体积分是所选步骤的状态。商品图由原创CSS绘制，标为示意、非实拍。

回放只GET静态JSON，不访问命令/重置API，也不调用模型。来回播放、重复点退款步骤、刷新不会再次退款。

## 重建与验证

```
python -m virtual_trade_lab.replay_data --study examples/defect-refund-model-study --output /tmp/replay-data.json
cmp /tmp/replay-data.json virtual_trade_lab/web/replay-data.json
python -m unittest discover -s tests -p test_replay.py -v
node tests/replay_interaction_test.js
node --check virtual_trade_lab/web/replay.js
```

8项Python回归覆盖逐字来源、账本守恒、无提前退款、数据篡改、真实loopback HTTP路由及无写入。Node脚本是原创DOM替身，不依赖新npm库，覆盖步骤/跳转/重复点击/前后导航/刷新/播放暂停/隐藏页面/终点/读取失败/坏数据防护。**DOM替身通过不等于浏览器渲染通过。**

## 当前视觉验收限制

已安装Chromium在助手云环境启动时失败：`process_singleton_posix.cc: socket() failed: Operation not permitted`。获准提升执行后仍相同，未继续换路径规避。没有实际页面截图，桌面/手机的像素布局、字体、浏览器原生焦点与辅助技术行为尚待正式浏览器环境验收。

CSS包含桌面与窄屏布局，但不能将其写成“已验证响应式”。当前交付是可运行本地页面和通过的数据/HTTP/交互逻辑测试，未部署网站。以后正式预览应检查390px/1440px布局、溢出、播放中手动跳转、重复点击、前后导航、刷新和数据读取失败。

## 收件后退款：独立的退货追踪页

运行同一个本地服务 `python -m virtual_trade_lab.server`，打开
`http://127.0.0.1:8765/returns`。实验台及旧回放均有入口。

这是 `examples/return-custody-model-study` 的三个已保存观察点，不是旧购买实验的连续后续，也不是实时物流。前序购买固定初始化；三个实际保留的对话模型决定分别为申请、批准、交回。承运交回及收件为明确标注的预设环境事件。本轮没有再调用模型。

- 批准时：买家58、卖家36、费用4、托管32，商品仍在买家。
- 交回后未收件：买家58、卖家32、费用8、托管32，商品在模拟承运方。
- 匹配收件：买家90、卖家32、费用8、托管0，商品返回卖家。

三个阶段均总额130积分。页面用原生锚点链接及折叠详情展示角色原文、物品保管方、账本和边界，没有交易按钮或 JavaScript。点击、返回、刷新和重复访问不会发送交易命令。没有匹配收件时仍等待；当前模型没有丢件、仲裁或超时赔付机制，不能据此保证现实退款时限。

生成命令：`python -m virtual_trade_lab.return_replay`。生成器校验冻结协议及角色清单，逐一重新构建两个中间快照和最终账本；任一观察时点的原文、协议、tick、保管状态或账本不一致即拒绝生成。`/returns-data.json` 可下载同一只读投影，不含会话能力或用户数据。

验证：`python -B -m unittest discover -s tests -p test_return_replay.py -v`。
新增测试覆盖精确再生成、三份原文、阶段守恒、篡改中间/终态、缺失封存、文本转义、HTTP重复访问/拒绝写入/Host限制。浏览器渲染仍未验收：现有环境 Chromium 的 socket 权限拒绝未解除，没有尝试绕过。原生交互与布局需后续在正式允许的预览环境视觉验证。
