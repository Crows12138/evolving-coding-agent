# evolving-coding-agent

一个会**修改自己 prompt 和工具**来解决更多 bug 的 coding agent。

基于一个最小化的 coding agent runtime(fork 自
[nano-claude-code](https://github.com/SafeRL-Lab/nano-claude-code)),在其
上构建了一套 **DGM(Darwin Gödel Machine)自我进化框架**。

[English README](README.md)

```text
gen 1: train 60% (±5) | hold 50% (±15) | LCB 42.5      ← 嘈杂基线
gen 2: train 75% (±5) | hold 65% (±10) | LCB 60.0  ✅  ← 保留
gen 3: train 80% (±5) | hold 55% (±20) | LCB 45.0  ❌  ← 回滚(holdout 跌了)
```

## 做什么

Agent 跑一套 pytest 评测集(51 个有 bug 的 Python 程序)。每次评测后,
一个 **meta-agent** 读取失败详情,修改 worker agent 的 system prompt 和工具
实现。提高 holdout 通过率的改动会被保留,降低的会被回滚。

## 跟别的"agent 自我改进"演示有什么不同

| 维度 | 多数 demo | 本项目 |
|---|---|---|
| 进化范围 | 只改 prompt | **prompt + 工具实现** |
| 决策指标 | 平均通过率 | **LCB**(median − spread/2,惩罚飘忽的 prompt) |
| 防过拟合 | 通常没有 | **Holdout 切分**(16/51)— meta-agent 看不到 holdout 失败 |
| 防 meta 污染 | 常用同一 prompt | **独立稳定的 META_AGENT_SYSTEM** |
| 防作弊 | 信 prompt 约束 | **PROTECTED 文件**(评测脚本/config)被改自动 `git checkout` 还原 |
| 崩溃处理 | 静默漏掉回滚 | **stale-result 检测**(没有新 result 文件 = 判为最差分) |
| 重复性 | 每代一次 | **每代 N=5 次**,作为随机变量样本对待 |

## 快速开始

### 1. 安装

```bash
pip install -r requirements.txt
```

### 2. 准备本地 LLM(默认 Ollama + Qwen3.5)

```bash
# 装 Ollama: https://ollama.com/download
ollama pull qwen3.5:9b

# 创建 16K 上下文版本(本地推荐)
echo 'FROM qwen3.5:9b
PARAMETER num_ctx 16384' > /tmp/Modelfile
ollama create qwen3.5-16k -f /tmp/Modelfile
```

也支持 Claude/GPT/Gemini 等,见 `providers.py`。

### 3. 生成 QuixBugs 任务(38 个额外 bug 修复任务)

```bash
git clone https://github.com/jkoppel/QuixBugs eval/_quixbugs
python eval/build_quixbugs_tasks.py --verify
```

### 4. 烟雾测试(5 分钟,3 个任务)

```bash
python eval/smoke_test.py
```

临时隐藏其他任务,只跑 3 个,跑完无论成功失败都还原。**验证管道完整跑通**。

### 5. 真正跑

```bash
# 默认:3 代,每代 N=5 次评测
python eval/evolve.py --generations 3 --max-rounds 2

# 快但不严谨(N=1)
python eval/evolve.py --generations 3 --quick

# 换模型
python eval/evolve.py --model "claude-sonnet-4-6"
```

本地 9B 模型 + N=5 大概一代 12 小时,**计划隔夜跑**。

## 架构

```
┌──────────────────────────────────────────────────────────┐
│  EVOLVABLE — DGM 能改(带回滚保护)                         │
│    context.py — system prompt                              │
│    tools.py   — 工具实现(Read/Write/Edit/...)            │
├──────────────────────────────────────────────────────────┤
│  PROTECTED — 改了 git checkout 还原                        │
│    eval/evolve.py, eval/run_eval.py — 评测机制本身         │
│    config.py — 运行参数由 model class 自动设              │
├──────────────────────────────────────────────────────────┤
│  Meta 层(DGM 驱动)                                       │
│    META_AGENT_SYSTEM — 编辑者 agent 的稳定 prompt          │
│    HOLDOUT_TASKS — 16 个编辑者永远看不到失败的任务         │
│    LCB 决策 — 基于 holdout LCB 决定 promote / rollback     │
└──────────────────────────────────────────────────────────┘
```

## 关键设计

### 1. 把评测结果当随机变量
每代跑 `N=5` 次,每个 prompt 产生一个分布。比较的是**分布**(median +
spread),不是点估计。LCB(`median - spread/2`)偏好稳定的 prompt,惩罚
飘忽但均值高的。

### 2. Holdout 保持 meta-agent 诚实
Meta-agent 看 35 个 train 任务的失败,但**永远看不到 16 个 holdout 的失败**。
所有 promote/rollback 决策只看 holdout 通过率——这能抓住针对 train 任务过
拟合的 prompt 改动。

### 3. Meta-agent 用独立、不可改的 prompt
Worker 的 prompt 自由进化,meta-agent 的 prompt(`META_AGENT_SYSTEM`)
写死在 `evolve.py` 里,**不在 `EVOLVABLE_FILES`**。Worker prompt 怎么变都
不会污染 meta-agent 的分析能力。

### 4. PROTECTED 文件防 meta-agent 误改
如果 meta-agent 改了 `eval/evolve.py` 或 `config.py`(作弊攻击面),
`_enforce_protected` 跑 `git checkout` 还原。`analyze_and_evolve` 和
`fix_broken_files` 后都会调用,**两层防御**。

### 5. eval 崩了 = 最差分
如果 eval 子进程没写出新 result 文件就崩了(比如 meta-agent 改坏了
`tools.py`),driver 检测"没有比 eval 启动时间更新的 result 文件"
→ 判为全失败 → 触发回滚。没这个检查,evolve 会读到上一代的旧 result,
**静默漏掉回滚**。

## 评测集

总共 51 个 Python bug 修复任务:

- **13 个手写任务**(`task_01..task_13`)— 多样化:购物车、状态机、链表、
  缓存、限流器、解析器、调度器等
- **38 个 QuixBugs 任务**(`qb_*`)— 经典算法单行 bug:排序/图/DP/搜索/
  数学/字符串

每个任务有 `issue.md`(描述)+ 一个或多个 `.py`(含 bug)+ `test_*.py`
(pytest 验证)。Agent 的任务:读 issue,定位 bug,编辑源文件让测试通过。

16 个 holdout 覆盖:手写集里的状态/解析/数值/IO,以及 QuixBugs 里的排序/
图/搜索/DP/数学/字符串。

## 局限

- **本地 9B 模型慢**:每任务 ~84 秒,N=5 × 51 任务 × 3 代 ≈ 36 小时。
  云端模型(Claude/GPT)能快 5-10 倍。
- **没有种群/并行搜索**:这是带回滚的 hill climbing,不是每代多候选的
  进化搜索。
- **评测集偏小**:51 任务能看到 DGM 信号,但仍有残余噪声。
- **没接外部 benchmark**:暂时不接 SWE-bench / HumanEvalFix。计划加入
  mini-SWE-agent 风格的集成。

## 路线图

- [ ] 接入 SWE-bench Verified Mini,产出可对比 leaderboard 的数据
- [ ] 种群式搜索(每代多候选)
- [ ] 跨代记忆(谨慎设计,避免历史污染)
- [ ] 可视化 prompt 跨代演化 diff

## 致谢

- [nano-claude-code](https://github.com/SafeRL-Lab/nano-claude-code) —
  基础 agent runtime(Apache 2.0)
- [QuixBugs](https://github.com/jkoppel/QuixBugs) — 38 个 bug 修复任务
  (MIT)
- [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) — 极简
  agent 设计灵感
- [Darwin Gödel Machine](https://arxiv.org/abs/2504.08066)(Sakana AI)
  — 自我进化 agent 论文

## License

Apache License 2.0,见 `LICENSE` 和 `NOTICE`。
