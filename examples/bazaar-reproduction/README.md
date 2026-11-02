# BazaarBench 官方离线测试复现（不是论文 LLM 成绩复现）

2026-11-02，固定上游 [ziyan-wang98/BazaarBench](https://github.com/ziyan-wang98/BazaarBench/tree/f87e01e22ae664dd06925c06b358d7ebcafb95b5)，commit `f87e01e22ae664dd06925c06b358d7ebcafb95b5`。下载源码全部271个tracked blob与GitHub树SHA一致；未修改上游。上游Apache-2.0，LICENSE声明继承CAMEL-AI/OASIS Apache-2.0；使用时保留上游LICENSE。这里不重新分发上游源码、数据库或许可证未明确的HF分析数据，只提供原创运行包装器、环境版本和结果摘要。

## 实测结果

执行的是上游 `tests/integration/test_smoke.py::test_smoke_20x50`：20个RandomBenignPolicy角色，50tick（0–49），persona/policy seed参数500–519，5个phantom初始listing。这个上游测试明确注入HashEncoder，不使用MiniLM语义模型。两次各1项测试通过（各0.66秒，不含安装），Python3.12.14。

|指标|第一次|第二次|
|---|---:|---:|
|events|1486|1480|
|listings|32|32|
|threads|15|13|
|offers|16|15|
|accepted offers|3|4|
|blocked events|0|1|
|handler errors|0|0|
|completed=true事件|0|0|
|sold listings|0|0|
|LLM调用记录|0|0|
|审计钩子观察的网络连接尝试|0|0|

**没有完成交易，不能把接受报价当成交。** 第一次有一次complete_transaction动作，但返回completed=false，买家确认、卖家未确认。上游通过标准是无handler错误、events>50、listings>=5、threads>=1及HTML渲染返回预期标题，不要求最终成交；所以通过测试不意味着已复现完整成功交易。

**同seed并非相同轨迹。** 去除wall_time后事件哈希仍不同；上游RandomBenignPolicy多处使用SQLite `ORDER BY RANDOM()`，不受Python种子控制。我们保留两次结果，不修改上游或挑选成交的seed。这里只重现测试不变量，不宣称精确轨迹复现。[全部计数、哈希和范围](summary.json)。

## 复现命令

以下需要下载已审查的第三方源码及PyPI依赖。不要在包含秘密或重要数据的目录运行；本次使用隔离云工作目录，未使用Docker/个人电脑。先检查源码及许可，按你的权限流程批准。

```sh
git clone https://github.com/ziyan-wang98/BazaarBench.git
cd BazaarBench
git checkout --detach f87e01e22ae664dd06925c06b358d7ebcafb95b5
python3.12 -m venv .venv
# 将本目录 dependencies.lock 和 offline_test_runner.py 复制到自己的实验目录
.venv/bin/python -m pip install --only-binary=:all: --index-url https://pypi.org/simple -r /path/to/dependencies.lock
PYTHONPATH="$PWD" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
 .venv/bin/python /path/to/offline_test_runner.py \
 tests/integration/test_smoke.py::test_smoke_20x50 -v \
 --basetemp=/tmp/bazaar-reproduction-run1
```

本次还用`env -i`清空环境（仅传PATH/HOME/PYTHONPATH及offline开关），未配置API凭据。包装器拒绝Python socket连接/DNS审计事件并报告尝试次数；这是辅助检测，不是恶意本地代码的完备安全沙箱。依赖只安装基础包和测试包，没有LLM/memory extras。上游example脚本未注入HashEncoder，可能触发MiniLM下载，因此不能将它冒称为本次运行命令。

## 没有复现什么

没有调用LLM、重新进行语义裁判、复现论文模型排名/风险率、验证真实客户行为或复现持续收益。HashEncoder上游自己标明不适合正式语义研究。论文实验需另行配置兼容模型后端、模型版本、预算及对应完整实验协议；当前没有获批付费API或可用本地推理后端。不能把这次scripted smoke称作“最强虚拟客户模型复现完成”。

本次仅审查并运行这一项官方测试两次，未运行上游完整测试集。当前项目自身107项主测试和17项退款测试是另一套检查，不能混淆。
