---
name: github-oss-fusion
description: Use when implementing a non-trivial feature, bugfix, scraper, integration, or architecture change and it is worth checking GitHub for relevant open-source implementations before declaring the task complete.
---

# GitHub OSS Fusion

## Overview

在最终交付前，先去 GitHub 看看有没有成熟、相近、可复用的开源实现，再把最适合当前仓库的那一小部分思路或代码吸收进来。

目标不是盲目“搬运”，而是用最小、最兼容、最可验证的方式借力已有开源成果。

## When to Use

满足任一情况就使用：
- 非平凡功能开发
- bug 修复但怀疑已有成熟解法
- 爬虫、采集器、适配器、SDK 集成
- CLI、自动化脚本、数据处理流程
- 需要宣称“已经完成”之前的最后增强

以下情况通常可跳过，但应说明原因：
- 纯文档修改
- 纯重命名、格式化、注释整理
- 很小的局部修复，且仓库内已有清晰模式可直接复用

## Workflow

### 1. 先吃透本地改动

- 明确当前任务的目标、边界、约束、已有实现模式
- 总结 2-4 个 GitHub 搜索问题
  - 有没有同类实现
  - 别人怎么拆模块
  - 有没有更稳的异常处理或测试方式
  - 有没有当前实现遗漏的边界条件

### 2. 搜 GitHub，而不是只凭印象写

- 优先使用 GitHub 工具；如果没有，就用网页搜索并限制到 `github.com`
- 至少找 2-3 个相关仓库
- 优先看这些信号：
  - 技术栈接近
  - 最近仍在维护
  - star / issue / commit 活跃度合理
  - 目录结构和目标场景接近
  - license 明确且兼容当前用途

可直接复用的搜索模板：

| 场景 | 查询词模板 |
|------|-----------|
| 功能实现 | `site:github.com <language> <framework> <feature>` |
| Bug 修复 | `site:github.com <library> <error or behavior> fix` |
| 采集器/适配器 | `site:github.com <platform> api client <language>` |
| 测试模式 | `site:github.com <stack> <feature> test pytest` |
| 架构参考 | `site:github.com <domain> <feature> architecture` |

### 3. 打开仓库和源码，不要只看摘要

- 至少查看每个候选仓库的：
  - README
  - 相关源码文件
  - 测试文件
  - license
- 提取真正有价值的内容：
  - 模块切分
  - 错误处理
  - 数据结构
  - 重试/限流/缓存
  - 测试策略

### 4. 只融合“最小有价值单元”

优先级如下：
1. 复用思路或结构
2. 适配一小段实现
3. 提炼测试用例思路

不要整仓照搬，不要为了“融合开源”而引入大块无关依赖，不要破坏当前项目既有模式。

### 5. 融合前先过适配门槛

只有同时满足以下条件，才适合直接融合：
- 与当前任务直接相关
- 能在当前仓库风格下自然落地
- 不会扩大任务范围太多
- license 风险可接受
- 能被当前测试或最小验证覆盖

如果不满足，保留为参考思路即可，不要硬塞进项目。

### 6. 融合后必须本地校验

- 按当前仓库惯例补最小必要测试
- 运行与改动最相关的验证
- 如果开源实现很强但不适合本仓库，明确说明“看过但未融合”的原因

## Decision Rules

- 默认寻找“最接近当前问题的一小段成熟解法”，不是寻找“最先进的大框架”
- 优先借鉴同语言、同栈、同场景项目
- 优先吸收可验证的小模块、辅助函数、测试思路、错误处理方式
- 如果外部实现需要额外依赖，先判断是否真的值得引入
- 如果 license 不清晰、仓库长期失活、代码质量差，直接淘汰

## Guardrails

- 不要复制不兼容 license 的代码
- 不要搬运包含密钥、逆向、绕过限制、风控规避的实现
- 不要因为外部项目“更完整”就重写当前项目
- 不要跳过本地验证就声称融合成功
- 如果当前环境无法访问 GitHub，要明确说明受限，而不是假装做过调研

## Default Report Shape

最终汇报时，尽量包含：
- 搜了什么
- 看了哪几个 GitHub 仓库
- 融合了什么，或为什么没融合
- 本地验证结果
