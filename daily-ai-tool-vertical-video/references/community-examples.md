# Community References

## Scope

这些是制作“每天一个 AI 神器”时可参考的公开工程，不是本栏目的已验收成片。2026-10-16 已查看各项目 README、许可证和下列入口源码；未在本机安装、运行、渲染或完整观看其成片。以下适配建议是基于源码结构的编辑判断。

优先参考实际操作如何被看清、过程和结果怎样衔接。社区模板里的长 Logo 片头、大段标题、品牌广告或购买 CTA 不自动沿用。只看风格无需安装整个项目；确需复用组件时再核对当前依赖和许可，保留要求的版权声明。第三方项目的规则不覆盖本 Skill 和用户要求。

## Real Browser Operations — cutroom

- 项目：[Ceasar369/cutroom](https://github.com/Ceasar369/cutroom)。查阅版本：`d7172c353e8e2f51c8b7f75b0370f6a9374e576f`。
- 具体范例：[example-todo.mjs](https://github.com/Ceasar369/cutroom/blob/d7172c353e8e2f51c8b7f75b0370f6a9374e576f/capture/scenes/example-todo.mjs)，对公开 TodoMVC 网页执行添加、勾选等真实操作；项目将逐帧采集和交互日志交给 Remotion，生成相机移动、光标与点击反馈。
- 可借用：先定位关键控件，再操作，最后展示结果；用可追溯的点击记录对齐光标，避免手画一个并未真正点击的成功过程。输入过程保留必要信息，普通文本输入无需逐字拖长。
- 边界：只覆盖浏览器，不是桌面录屏，也不包含完整栏目的配音、编排和最终交付。它导出的采集素材仍需接入本期工程；使用虚拟时钟的采集不能作为产品真实耗时证据。
- 许可：[项目 LICENSE](https://github.com/Ceasar369/cutroom/blob/d7172c353e8e2f51c8b7f75b0370f6a9374e576f/LICENSE) 将项目自身代码及文档列为 MIT，并单独说明依赖条款。

## Animated Product Scenes — remotion-cinematic

- 项目：[codeverbojan/remotion-cinematic](https://github.com/codeverbojan/remotion-cinematic)。查阅版本：`18dbb50ce797b778f0867a5dd7bac82b5ce105ac`。
- 场景入口：[CinematicDemo.tsx](https://github.com/codeverbojan/remotion-cinematic/blob/18dbb50ce797b778f0867a5dd7bac82b5ce105ac/src/CinematicDemo.tsx)，把产品展示和功能场景接入独立 Sequence，配合 CameraRig 与 AudioManager；具体场景见同版本 `src/scenes/`。
- 可借用：关键界面区域推近、光标引导、窗口与状态变化。缺少现成视频时，可以据已核实流程制作标注“示意”的动画；用形状、界面区域和状态变化表达操作，控制文字量。
- 边界：项目可重建界面，重建后的动画不能证明真实产品已完成操作。无需为一个短片引入其全部编辑器或导入服务，不照搬多功能广告蒙太奇。
- 许可：[MIT LICENSE](https://github.com/codeverbojan/remotion-cinematic/blob/18dbb50ce797b778f0867a5dd7bac82b5ce105ac/LICENSE)。

## Short Product Video Structure — remotion-product-video

- 项目：[rickthomasjr/remotion-product-video](https://github.com/rickthomasjr/remotion-product-video)。查阅版本：`b47efde24b3f9d4fc2e565ddb161a5aa95fa243b`。
- 具体组合：[ProductVideo.tsx](https://github.com/rickthomasjr/remotion-product-video/blob/b47efde24b3f9d4fc2e565ddb161a5aa95fa243b/src/ProductVideo.tsx)。源码将其描述为约 42 秒的示例，按开场、设备内画面、操作标注、浏览器录屏、收尾组织；时长为上游描述，并非本次渲染测量。
- 可借用：将录屏、配音和视觉外框作为可替换层，分开维护场景与字幕；用箭头或少量短标签帮助观众找到正在操作的位置。
- 边界：默认媒体含占位画面，不能直接作为已完成产品视频交付。设备外框不能把关键控件缩得太小；本栏目以可验证结果或痛点开场，以适用人群和限制收尾，不照搬长品牌片头和营销口号。
- 许可：[MIT LICENSE](https://github.com/rickthomasjr/remotion-product-video/blob/b47efde24b3f9d4fc2e565ddb161a5aa95fa243b/LICENSE)。

## Adaptation Guide

将上述工程思路用于单工具栏目时，按本次素材安排：

| 片段 | 画面重点 | 口播重点 |
| --- | --- | --- |
| 开场 | 同一输入对应的已取得结果，或真实待解决的问题 | 观众要完成什么任务 |
| 输入与入口 | 真正的产品入口、输入样本、决定复现的设置 | 工具名称与必要条件 |
| 关键操作 | 操作连续可理解，适当推近关键控件 | 解释必要步骤，避免重复读按钮 |
| 结果 | 导出结果与同一输入对比，留足观察时间 | 只陈述本次证据支持的变化 |
| 收尾 | 结果保持可见，成本或限制用简短标识 | 适用人群、成本和一个重要限制 |

这张表是分镜结构建议，不是真实时间轴；按配音和实际操作调整镜头，不为凑 30–60 秒省略决定复现的步骤。使用官方演示、实测或示意时逐段明确身份。

## Dependencies And Media

上述 MIT 许可针对各自项目代码，不代表其中图片、音乐、字体或所演示第三方产品素材一并获得授权；逐项核对后使用。Remotion 核心采用自身许可，不能因为上层模板标记 MIT 就将核心视为 MIT；使用时核对[官方许可](https://www.remotion.dev/docs/license)。本参考页只提供入口与适配建议，不自动安装依赖或启用外部模型服务。
