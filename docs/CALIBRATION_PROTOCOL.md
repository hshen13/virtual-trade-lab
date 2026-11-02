# 三轴校准：只交付协议与防误报检查，不是人体实验

**目前：设计准备完成；0次参与者导入、0模型调用、0/9证据门槛满足，`not_evaluated`。** 没有盲测、产品孪生、拟合或人体校准结果。协议JSON里的真实研究数字是设计元数据，不是本项目观察。

## 用户提出的三个问题

|轴|固定条件|未来比较|尚缺|
|---|---|---|---|
|校准虚拟用户|同一真实产品版本、使用经历/信息、报价/赠款、选择集合及不买选项|真实用户与虚拟用户的选择|可比经历、身份来源、模型、盲态分配|
|校准虚拟产品|相同用户群或家庭内配对、价格/赠款、任务|真实产品与版本化虚拟孪生的体验及选择|孪生资产、体验对齐、顺序平衡、盲态标签|
|校准定价|每款产品、经历、用户域及赠款机制|各价格下实际购买与虚拟选择|合理误差容限/样本数、家庭级划分、独立新留出|

“盲测”不能假定参与者无法察觉实物与虚拟界面差异；要明确对谁隐藏何种标签、如何分配/平衡顺序、如何测量泄露。多款产品分别报告，不能一个产品拟合成功便宣布全部对齐。没有经验依据时不填写精确达标阈值；先冻结指标、容差依据、成本/退款观察窗口，再讨论验证。

## 已核对的价格研究锚点（不是本项目的实验）

Davies等的[数据记录](https://datacompass.lshtm.ac.uk/id/eprint/5121/)标注两个open CSV为CC BY4.0；受控补充数据不是同一权限。本轮只阅读元数据、[codebook](https://datacompass.lshtm.ac.uk/id/eprint/5121/4/Phase1-2_data_codebook.html)及[论文](https://journals.plos.org/water/article?id=10.1371/journal.pwat.0000583)，**未下载/导入参与者行**。

Phase1为60户、三款产品（SATO Tap、Kalingalinga bucket、Happy Tap）中每户体验两款，另有300ZMW赠款与不同折扣设计。Phase2为160户、Kalingalinga bucket、两周实物使用、50ZMW现金赠款和20/40/60/80%折扣。Phase2实际四折扣组人数依序40/39/41/40，不假设实际各40户。Phase1产品配对和体验顺序随机、折扣用密封信封；Phase2先交付并使用、后赠款和报价，留5–10分钟做选择。两阶段不能直接合并成同一价格试验。[研究设计来源](https://journals.plos.org/water/article?id=10.1371/journal.pwat.0000583)

Phase2零售标价250ZMW，必须分别保存：

|折扣|标价|交易应付|现金赠款|effective price / 自有资金净贡献|
|---|---:|---:|---:|---:|
|20%|250|200|50|150|
|40%|250|150|50|100|
|60%|250|100|50|50|
|80%|250|50|50|0|

`effective_price = transaction_price - cash_gift`。有效价0不等于无机会成本：不购买者可以保留赠款。不得把有效价当全部成交价，或将未经测试的全零售价购买情况当观察事实。主结局是指定报价下实际购买选择；事后stated_wtp受已发生购买/折扣条件影响，且不买者申报值不能高于交易应付价、买者不能低于交易应付价；单独保留，不冒充独立盲态目标或收款凭证。[定义及结局字段](https://datacompass.lshtm.ac.uk/id/eprint/5121/4/Phase1-2_data_codebook.html)

## 防泄漏与状态

已经看过该研究汇总结果，因此这里只能作calibration/development来源；不能声称全盲留出。未来按家庭分组，同家庭事件不得跨训练/留出；real observed claims与synthetic预测分开，phase也分开。未有新留出、经历重放、UX盲态标签、模型版本/后端、有效容差及独立复核，不能声称calibrated。

```sh
python -m virtual_trade_lab.calibration_protocol
python -m virtual_trade_lab.calibration_protocol --spec metadata.json
python -m unittest tests.test_calibration_protocol -v
```

[机器可读协议](../virtual_trade_lab/calibration_protocol.json)是此固定设计的元数据契约，不是通用参与者数据schema。检查器拒绝新增数据行、混淆价格、合并真实/合成、混用阶段、事件级随机划分及自行填“已校准”。证据位置全部null；null不是0误差或空观察样本。允许将门槛改为planned，但通过格式检查仍为0/9证据完成。修改固定研究设计须新版本和复核；软件不核验许可资格、真实收款或法律合规。
