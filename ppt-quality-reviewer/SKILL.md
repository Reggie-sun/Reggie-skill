---
name: ppt-quality-reviewer
description: Review and improve slides_outline.json, generated PowerPoint content, or presentation drafts for clarity, executive readability, slide density, logical flow, duplicate titles, long bullets, weak conclusions, and document-to-PPT quality. Use after doc-to-ppt-outline or pptxgenjs-builder when the user asks to review, improve, polish, audit, or quality-check a PPT/deck/slides.
---

# ppt-quality-reviewer

## Overview

使用本 skill 审查 `slides_outline.json`、已生成 PowerPoint 的文本抽取结果、或用户粘贴的逐页内容，重点检查汇报逻辑、页面密度、领导可读性和文档转 PPT 质量。需要直接修复时，额外输出 `revised_slides_outline.json`，并保持与 `pptxgenjs-builder` 兼容。

## Triggers

当用户说以下类似需求时使用本 skill：

- 检查这个 PPT
- 优化这个 PPT 大纲
- 看看这个 `slides_outline.json` 有没有问题
- 领导汇报是否合适
- PPT 内容太密帮我改
- 检查文档转 PPT 效果
- review deck
- polish slides
- quality check presentation

## Inputs

支持审查：

- `slides_outline.json`
- PPT 文本抽取结果
- 用户粘贴的每页内容
- `doc-to-ppt-outline` 的输出
- `pptxgenjs-builder` 生成前的大纲

## Outputs

默认输出：

- `review_report.md`

如果用户要求直接修复，额外输出：

- `revised_slides_outline.json`

## Review Dimensions

必须检查以下维度。

### A. Structure

- 是否有标题页。
- 是否有目录页。
- 是否有总结页。
- 是否逻辑顺序合理。
- 是否从背景、进展、问题、方案、计划推进。
- 是否缺少“下一步”。

### B. Slide Quality

- 每页是否只有一个核心观点。
- 每页 bullet 是否 3-5 条。
- bullet 是否过长。
- 是否像文档搬运。
- 是否出现空页。
- 是否出现重复页。
- 标题是否重复或太虚。

### C. Executive Readability

- 是否减少技术黑话。
- 是否讲清楚业务价值。
- 是否讲清楚风险。
- 是否讲清楚进展。
- 是否讲清楚需要领导决策或支持的点。

### D. Visual Suggestions

- 哪些页适合流程图。
- 哪些页适合表格。
- 哪些页适合指标卡。
- 哪些页适合两栏对比。
- 哪些页不应该放太多文字。

### E. Document-To-PPT Quality

- 是否只是复制原文。
- 是否做了压缩。
- 是否提炼出结论。
- 是否保留关键证据。
- 是否丢失重要限制条件。
- 是否有过度发挥。

完整清单见 `references/ppt_review_checklist.md`。

## Scoring

输出 0-100 分：

- 90-100：可以直接用于正式汇报，只需小修。
- 75-89：结构可用，但需要压缩和润色。
- 60-74：内容基本有用，但不适合直接汇报。
- 0-59：需要重做大纲。

评分维度：

- 结构完整性：20
- 内容压缩质量：20
- 管理层可读性：20
- 页面密度控制：15
- 视觉表达适配：15
- 结论与下一步清晰度：10

## Report Format

`review_report.md` 必须包含：

```markdown
# PPT Quality Review

## Overall Score

分数：xx/100
等级：...

## Executive Summary

用 3-5 条说明最大问题和最大优点。

## Key Issues

按严重程度列出问题：

- Critical
- Major
- Minor

## Slide-by-Slide Review

逐页检查：

- 页码
- 标题
- 问题
- 修改建议

## Recommended Changes

给出可执行修改建议。

## Revised Outline Needed

说明是否建议生成 revised_slides_outline.json。
```

## Direct Fix Mode

如果用户要求直接修复，输出 `revised_slides_outline.json`，并遵守：

- 保留原始核心信息。
- 压缩过长 bullet。
- 合并重复页。
- 补充缺失总结页。
- 让标题更像汇报标题。
- 保持 schema 和 `pptxgenjs-builder` 兼容。
