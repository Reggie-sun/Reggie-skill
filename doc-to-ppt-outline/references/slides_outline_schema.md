# slides_outline.json Schema

## Purpose

`slides_outline.json` 是 `doc-to-ppt-outline` 和 `pptxgenjs-builder` 之间的结构化交接格式。前者负责从材料中提炼每页内容，后者负责将该 JSON 渲染成可编辑 `.pptx`。

## Top-Level Structure

```json
{
  "meta": {
    "title": "",
    "subtitle": "",
    "author": "",
    "date": "",
    "audience": "",
    "purpose": "",
    "style": "enterprise"
  },
  "slides": []
}
```

## meta Fields

- `title`：整套汇报标题，优先使用面向受众的汇报标题。
- `subtitle`：补充说明，如“阶段进展、问题复盘与后续计划”。
- `author`：作者或团队名称，可以为空。
- `date`：汇报日期，可以是 `YYYY-MM` 或 `YYYY-MM-DD`。
- `audience`：受众，如“公司领导 / 部门负责人”。
- `purpose`：汇报目的，如“阶段汇报”“立项评审”“复盘汇报”。
- `style`：默认 `enterprise`。

## Supported Layouts

### title

用于封面。

```json
{
  "layout": "title",
  "title": "企业级项目阶段汇报",
  "subtitle": "阶段进展、问题复盘与后续计划",
  "speaker_notes": "开场说明本次汇报目标。"
}
```

### agenda

用于目录页。`bullets` 应为数组，通常 4-6 条。

```json
{
  "layout": "agenda",
  "title": "汇报议程",
  "bullets": ["背景与目标", "当前进展", "问题复盘", "后续计划"],
  "speaker_notes": "说明本次汇报结构。"
}
```

### section

用于章节分隔页，适合 10 页以上的正式 deck。

```json
{
  "layout": "section",
  "title": "二、当前进展",
  "subtitle": "从交付结果、验证结果和风险状态展开",
  "speaker_notes": "切换到进展部分。"
}
```

### content

用于普通内容页。每页一个核心观点，`bullets` 控制在 3-5 条。

```json
{
  "layout": "content",
  "title": "当前阶段已形成基础交付闭环",
  "bullets": ["核心流程已完成端到端验证", "关键角色协作边界已明确", "基础验收标准覆盖主要场景"],
  "visual_suggestion": "可用状态卡展示已完成、进行中和待补齐事项。",
  "speaker_notes": "强调结论，不展开过多细节。"
}
```

### two_column

用于对比页，如价值与风险、现状与下一步、方案 A 与方案 B。

```json
{
  "layout": "two_column",
  "title": "阶段价值与当前风险并存",
  "left_title": "已体现价值",
  "left_bullets": ["统一流程降低沟通成本", "关键指标让状态更透明"],
  "right_title": "仍需关注",
  "right_bullets": ["复杂场景稳定性仍需观察", "边界流程需要继续固化"],
  "speaker_notes": "左侧讲价值，右侧讲风险。"
}
```

### table

用于状态、指标、计划或问题清单。`headers` 和每行列数应尽量一致。

```json
{
  "layout": "table",
  "title": "重点事项状态",
  "table": {
    "headers": ["事项", "当前状态", "下一步"],
    "rows": [
      ["核心流程", "已完成基础闭环", "扩展覆盖场景"],
      ["反馈机制", "已打通入口", "完善分级处理"]
    ]
  },
  "speaker_notes": "表格用于快速对齐状态。"
}
```

### process

用于流程页。`steps` 控制在 4-6 步。

```json
{
  "layout": "process",
  "title": "核心链路覆盖需求到交付",
  "steps": ["需求确认", "方案设计", "开发联调", "验收发布", "运营复盘"],
  "speaker_notes": "说明主要工作链路。"
}
```

### summary

用于结论页。`bullets` 应聚焦结论、下一步和需要支持的点。

```json
{
  "layout": "summary",
  "title": "阶段结论与请求支持",
  "bullets": ["项目已具备阶段验收基础", "下一阶段重点提升稳定性", "建议确认资源和发布时间窗口"],
  "speaker_notes": "收束到需要决策的事项。"
}
```

## Common Mistakes

- 把原文段落整段塞进 `bullets`。
- 使用文档章节名作为标题，如“3.2.1 系统模块说明”。
- 同一页同时讲背景、问题、方案和计划。
- 连续多页标题重复，如多页都叫“当前进展”。
- `bullets` 写成字符串，而不是数组。
- `table.rows` 不是二维数组。
- `process.steps` 超过 6 步，导致页面拥挤。
- 缺少 `speaker_notes`，后续讲稿无法承接。

## Handoff To pptxgenjs-builder

生成 `slides_outline.json` 后，将文件交给 `pptxgenjs-builder`：

```bash
cd /home/reggie/.codex/skills/pptxgenjs-builder
node scripts/build-pptx.mjs /path/to/slides_outline.json /path/to/output.pptx
```

`pptxgenjs-builder` 依赖 layout 和字段名渲染页面，因此不要随意新增 layout 名称。未知 layout 可能会回退为普通内容页，但推荐只使用本 schema 中列出的 layout。
