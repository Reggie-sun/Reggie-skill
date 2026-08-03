---
name: pptxgenjs-builder
description: Generate editable PowerPoint .pptx files from slides_outline.json using PptxGenJS. Use when the user asks to create PPT, generate PPTX, convert documents to slides, build report decks, or export PowerPoint presentations.
---

# pptxgenjs-builder

## Overview

使用本 skill 将结构化的 `slides_outline.json` 转成可编辑的 PowerPoint `.pptx` 文件。PptxGenJS 只作为本 skill 的 npm 依赖使用，不修改第三方仓库源码，不把脚本放进 `node_modules`，也不复制 `gitbrent/PptxGenJS` 仓库。

## When To Use

在用户提出以下需求时使用本 skill：

- 生成 PPT
- 文档转 PPT
- 输出 pptx
- 做汇报 PPT
- 把大纲变成 PowerPoint
- 提到 slides、deck、presentation 或 PowerPoint 导出

## Input

优先使用 `slides_outline.json` 作为输入。推荐 schema 见 `examples/slides_outline.example.json`。

如果用户只提供 `docx`、`pdf`、`md`、`txt` 或长文档，先将原文抽取和重组为 `slides_outline.json`，再调用 `scripts/build-pptx.mjs` 生成 `.pptx`。抽取时不要逐字搬运原文，要压缩为适合汇报的页面结构。

## Output

输出可编辑 `.pptx` 文件，默认使用 16:9 宽屏、企业汇报风格、白底深色文字和少量强调色。中文字体优先使用 `Microsoft YaHei`、`Noto Sans CJK SC`，再回退到 `Arial`。

## Quality Bar

- 每页只表达一个核心观点。
- 每页正文控制在 3-5 个 bullet。
- bullet 不要太长，优先用短句。
- 标题不要重复。
- 不要把长文档逐字搬运进 PPT。
- 面向领导汇报时减少技术黑话，突出结论、进展、风险和下一步。

## Run

在 skill 目录中运行：

```bash
node scripts/build-pptx.mjs examples/slides_outline.example.json output/demo.pptx
```

也可以使用 npm script：

```bash
npm run demo
```

## Post-Generation Checks

生成后必须检查：

- 输出文件是否存在。
- 文件大小是否合理。
- 是否有空页。
- 是否有重复标题。
- 是否有过长 bullet。
- 是否所有 slide 都有 title。

## Document-To-Outline Workflow

当输入是长文档时，先生成 `slides_outline.json`：

1. 提取文档标题、汇报对象、时间、作者和核心结论，写入 `meta`。
2. 将内容拆成 6-12 页左右的汇报结构：封面、目录、背景、进展、问题、方案、计划、总结。
3. 每页只保留一个核心观点，正文压缩为 3-5 条短 bullet。
4. 为图表、流程或对比内容选择合适 layout：`table`、`process`、`two_column`。
5. 生成 `.pptx` 后按 `Post-Generation Checks` 做静态检查。
