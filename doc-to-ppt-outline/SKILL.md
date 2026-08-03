---
name: doc-to-ppt-outline
description: Convert documents, long text, PDFs, Word docs, Markdown, meeting notes, reports, or pasted materials into a structured slides_outline.json for PowerPoint generation. Use before pptxgenjs-builder when the user asks for document-to-PPT, report deck, leadership presentation, slide outline, PPT structure, or PowerPoint content planning.
---

# doc-to-ppt-outline

## Overview

使用本 skill 将长文档、会议纪要、方案、报告或用户粘贴材料压缩、重组、结构化为 `slides_outline.json`。本 skill 不负责生成 `.pptx`；真正的 PowerPoint 文件生成交给 `pptxgenjs-builder`。

## Triggers

当用户说以下类似需求时使用本 skill：

- 文档转 PPT
- 帮我做 PPT 大纲
- 把报告变成汇报 PPT
- 根据这份材料生成 `slides_outline.json`
- 生成给领导看的汇报 PPT
- 先整理每页内容
- convert document to slides
- create deck outline
- build presentation structure

## Responsibility

只输出可供后续生成 PPT 的结构化大纲：

- 默认输出文件名：`slides_outline.json`
- 在项目目录中操作时，优先放到 `input/slides_outline.json`
- 只在临时示例或无项目上下文时，放到 `/tmp/slides_outline.json`

不要调用 PptxGenJS，不要生成 `.pptx`。用户需要 PowerPoint 文件时，下一步使用 `pptxgenjs-builder`。

## Input Sources

支持从以下材料整理大纲：

- 用户粘贴的长文档
- `.docx` 内容
- `.pdf` 提取文本
- Markdown
- `txt`
- 会议纪要
- 技术方案
- 项目总结
- 评测报告
- 日志总结

## Required Schema

输出必须是合法 JSON，基础结构如下：

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
  "slides": [
    {
      "layout": "title",
      "title": "",
      "subtitle": "",
      "speaker_notes": ""
    }
  ]
}
```

详细字段说明见 `references/slides_outline_schema.md`。

## Supported Layouts

每页必须使用以下 layout 之一：

- `title`
- `agenda`
- `section`
- `content`
- `two_column`
- `table`
- `process`
- `summary`

## Fields By Layout

- `title`：`layout`、`title`、`subtitle`、`speaker_notes`
- `agenda`：`layout`、`title`、`bullets`、`speaker_notes`
- `content`：`layout`、`title`、`bullets`、`visual_suggestion`、`speaker_notes`
- `two_column`：`layout`、`title`、`left_title`、`left_bullets`、`right_title`、`right_bullets`、`speaker_notes`
- `table`：`layout`、`title`、`table.headers`、`table.rows`、`speaker_notes`
- `process`：`layout`、`title`、`steps`、`speaker_notes`
- `summary`：`layout`、`title`、`bullets`、`speaker_notes`

## Compression Rules

- 不要把原文逐字搬进 PPT。
- 每页只表达一个核心观点。
- 每页 3-5 个 bullet。
- 每个 bullet 控制在 18-32 个中文字左右。
- 标题要像汇报标题，不要像文档章节名。
- 先讲结论，再讲证据。
- 面向领导时减少技术黑话。
- 技术细节只保留管理层需要知道的影响、风险、成本、进度、下一步。
- 如果材料过长，优先保留结论、现状、问题、风险、计划、指标。

## Default Enterprise Structure

如果用户没有指定页数，默认生成 8-12 页，推荐 10 页：

- 标题页
- 汇报目录
- 背景与目标
- 当前进展
- 核心能力 / 方案架构
- 关键数据 / 验证结果
- 主要问题
- 优化方案
- 后续计划
- 总结与请求支持

## Planning Defaults

生成前先判断：

- 受众是谁
- 汇报目的是什么
- 是否是管理层汇报
- 是否需要技术细节
- 是否需要正式风格
- 是否需要页数限制

如果用户没有说清楚，默认：

- `audience`: 公司领导 / 部门负责人
- `purpose`: 阶段汇报
- `style`: enterprise
- `page count`: 10

## Self-Check

输出 `slides_outline.json` 前必须检查：

- JSON 合法。
- `slides` 是数组。
- 每页有 `title`。
- 每页 `layout` 合法。
- `content`、`agenda`、`summary` 的 `bullets` 是数组。
- `table` 有 `headers` 和 `rows`。
- `process` 有 `steps`。
- 不存在连续重复标题。
- 没有明显超长 bullet。
- 不存在空页。

## Next Step

当 `slides_outline.json` 通过自检后，用 `pptxgenjs-builder` 生成可编辑 PowerPoint：

```bash
node scripts/build-pptx.mjs input/slides_outline.json output/deck.pptx
```
