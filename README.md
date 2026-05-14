# Bridge FEM Agent Workflow

一个基于 Python + Abaqus 的模块化桥梁有限元分析 workflow。第一版面向简单梁桥，生成 B31 beam element 的 Abaqus `.inp`，可调用 Abaqus，也支持 `--dry-run` 在未安装 Abaqus 的机器上验证完整流程。

## 特点

- 从 JSON 读取桥梁任务描述
- 自动生成 `jobname_attempt_0.inp`
- 使用 `subprocess` 封装 Abaqus 调用
- 监控 `.log`、`.msg`、`.dat`、`.sta`、`.odb`
- 解析并分类常见错误
- 基于 deterministic rule-based repair 生成 `jobname_attempt_N.inp`
- 不覆盖原始或历史 `.inp`
- 输出 `report.json` 和 `report.md`
- 不依赖外部 LLM API，代码中保留 TODO 扩展点

## 推荐环境

- Python 3.10+
- Abaqus 可选；没有 Abaqus 时使用 `--dry-run`
- 无第三方 Python 依赖

## 运行

```powershell
python main.py --input bridge_fem_agent\examples\simple_girder_bridge.json --workdir runs\simple_girder_bridge --max-repairs 3 --dry-run
```

真实 Abaqus：

```powershell
python main.py --input bridge_fem_agent\examples\simple_girder_bridge.json --workdir runs\simple_girder_bridge --max-repairs 3
```

如果 Abaqus 命令不是默认 `abaqus`：

```powershell
python main.py --input bridge_fem_agent\examples\simple_girder_bridge.json --workdir runs\simple_girder_bridge --abaqus-command "abaqus" --max-repairs 3
```

## 测试

```powershell
python -m unittest discover bridge_fem_agent\tests
```
