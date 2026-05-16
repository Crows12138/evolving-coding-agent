`levenshtein.py` 中存在 bug，导致 `test_levenshtein.py` 中的测试失败。

请：
1. 用 Read 工具读 `levenshtein.py`，理解它要实现什么算法
2. 用 Bash 跑 `python -m pytest test_levenshtein.py -x` 看具体哪个测试 fail
3. 定位错误的那一行并用 Edit 修复

注意：bug 是单行级别的小错误（off-by-one、错误运算符、错误初值等），
不需要重写算法，找到错误的那一行改掉即可。不要修改测试文件。
