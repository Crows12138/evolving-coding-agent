# Mini SWE-bench — 本地 Agent 能力评测

轻量版 SWE-bench，专门测试 agent 的问题解决能力。
每个任务 = 一个有 bug 的项目 + 一段 issue 描述 + 测试用例。

用法：
    python eval/run_eval.py

评分标准：agent 能否通过修改代码让测试全部通过。
不需要 Docker，不需要云端 API，全部本地运行。
