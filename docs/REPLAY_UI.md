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
