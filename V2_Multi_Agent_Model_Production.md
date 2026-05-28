# V2 Multi-Agent Abaqus Model Production

本版本在 V1 的 Abaqus 求解、诊断、修复链路之外，新增“多 Agent 协作生成可审查 Abaqus 模型”的工作流。

## 核心思路

V2 不让图纸或文本直接生成 Abaqus 文件，而是经过一个可审计的中间层：

```text
图纸/文本/结构化 JSON
  -> Bridge Semantic Model
  -> 多 Agent 模型计划
  -> Abaqus/CAE Python build script
  -> .cae / .inp
  -> 可选 Abaqus/Standard 验证
```

当前版本先支持结构化 JSON 输入，并读取本地 `samples/**/*.jnl` 参考模型，提取建模风格统计。V2 已支持 `beam` 与 `solid` 两条生成路径；后续可以把 PDF/CAD/OCR 解析接到同一个 semantic model。

## Agent 分工

- `DocumentAgent`: 读取 JSON，生成桥梁语义模型。
- `ReferenceAgent`: 扫描 `samples` 中的 Abaqus journal，识别 wire beam、solid extrude、connector、mesh、load 等参考模式。
- `GeometryAgent`: 生成桥梁纵向坐标、跨径站点、支座断点和主梁 wire 轴线。
- `IdealizationAgent`: 选择有限元理想化方式。当前默认生成 B31 beam 全桥模型。
- `MaterialAgent`: 准备材料和截面定义。
- `MeshAgent`: 计算目标网格尺寸，保留支座与跨径断点。
- `BoundaryAgent`: 将 pinned、roller、fixed 等工程支座语义转换为 Abaqus DOF 约束。
- `LoadAgent`: 将自重、桥面均布面荷载转换为 Abaqus gravity 和 beam line load。
- `QaAgent`: 在生成 Abaqus 模型前检查支座、材料、荷载、网格等关键项。
- `AbaqusCaeScriptBuilder`: 输出可审查的 Abaqus/CAE Python 脚本，并可调用 Abaqus 生成 `.cae/.inp`。

## 示例命令

只生成可审查模型资产，不调用 Abaqus/CAE：

```powershell
python main.py --workflow model-production --input bridge_fem_agent\examples\three_span_agent_bridge.json --workdir runs\three_span_agent_bridge_v2 --samples-dir samples
```

生成资产并调用 Abaqus/CAE noGUI 生成 `.cae/.inp`：

```powershell
python main.py --workflow model-production --input bridge_fem_agent\examples\three_span_agent_bridge.json --workdir runs\three_span_agent_bridge_v2_cae --samples-dir samples --build-cae
```

## 主要输出

```text
runs/three_span_agent_bridge_v2_cae/
  model_plan.json
  qa_report.json
  qa_report.md
  model_production_report.json
  three_span_agent_bridge_build_model.py
  three_span_agent_bridge.cae
  three_span_agent_bridge.inp
```

其中：

- `model_plan.json`: 多 Agent 协作后的完整建模计划。
- `qa_report.md`: 生成前 QA/QC 审查报告。
- `three_span_agent_bridge_build_model.py`: 可人工审查的 Abaqus/CAE Python 脚本。
- `three_span_agent_bridge.cae`: Abaqus/CAE 模型数据库。
- `three_span_agent_bridge.inp`: Abaqus 输入文件。

## 本机验证记录

已用本地 `samples` 目录作为参考，生成三跨连续梁示例：

```text
E:\Desktop\Text to bridge\runs\three_span_agent_bridge_v2_cae_retry2
```

Abaqus/CAE noGUI 成功生成：

```text
three_span_agent_bridge.cae
three_span_agent_bridge.inp
```

随后直接提交生成的 `.inp` 给 Abaqus/Standard：

```powershell
abaqus job=three_span_agent_bridge_check input=three_span_agent_bridge.inp interactive
```

状态文件显示：

```text
THE ANALYSIS HAS COMPLETED SUCCESSFULLY
```

## 实体分析路径

当输入 JSON 设置：

```json
{
  "model_level": "solid",
  "mesh": {
    "element_type": "C3D8R"
  }
}
```

系统会参考 `samples` 中的实体建模模式，生成：

- `BaseSolidExtrude` 矩形实体主梁
- `HomogeneousSolidSection` 实体截面
- `C3D8R` 为主的实体单元
- `seedPart + generateMesh` 网格流程
- 支座断面分割
- 底面支座节点集
- 顶面 `Pressure`
- 自重 `Gravity`
- Abaqus/Standard 静力分析 step

实体示例：

```powershell
python main.py --workflow model-production --input bridge_fem_agent\examples\three_span_solid_bridge.json --workdir runs\three_span_solid_bridge_v2_cae --samples-dir samples --build-cae
```

本机实体模型验证目录：

```text
E:\Desktop\Text to bridge\runs\three_span_solid_bridge_v2_cae_retry2
```

已生成：

```text
three_span_solid_bridge.cae
three_span_solid_bridge.inp
three_span_solid_bridge_check.odb
three_span_solid_bridge_check_odb_results.json
```

实体模型的 Abaqus/Standard 状态：

```text
THE ANALYSIS HAS COMPLETED SUCCESSFULLY
```

当前实体分析结果提取：

```text
max_displacement = 1.3075553125059352
max_stress = 1051906.5
```

说明：实体路径中顶面 `Pressure` 会优先尝试创建 Abaqus surface；若 Abaqus/CAE 对分割实体的 surface side 创建失败，脚本会自动回退为顶面节点集等效竖向集中力，保证模型可生成和可求解。

## 当前边界

- 当前 V2 可生成全桥 B31 beam 模型，也可生成简化矩形实体 C3D8R 模型。
- samples 中的 `.cae` 二进制文件不直接解析，当前读取 `.jnl` 作为参考模式来源。
- PDF/CAD 图纸理解还未接入，后续应作为 `DrawingAgent` 或 `DocumentAgent` 的前置能力。
- 壳单元、实体单元、局部精细模型、连接器支座、规范荷载组合将在后续版本扩展。
