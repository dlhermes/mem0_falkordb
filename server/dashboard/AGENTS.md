# mem0 dashboard 项目规则

## UI 设计规范（强制）

本项目 UI 工作必须遵循根目录 `DESIGN.md`（**Sentry 风格**：深紫午夜画布 + 电光青柠主 CTA + 紫/粉辅助 accent，数据密集仪表盘）。

关键要点：
1. **画布**：night `#150f23`（最底）→ canvas-dark `#1f1633`（面板）→ surface-1/2/3 递进。
2. **主 CTA**：青柠 `#c2ef4e` 底 + 深色文字 `#1a2405`；仅用于主操作/高亮/正值，不铺背景。
3. **辅助 accent**：紫 `#6a5fc1`（focus 光环/数据点）、粉 `#fa7faa`（装饰/对话徽章）。
4. **边框**：hairline `#362d59`，强调 `#4a3f6e`；不用纯黑。
5. **字体**：Rubik/Inter（sans），Monaco（mono）；数字 tabular-nums；表头/分组标签 11px 大写。
6. **布局**：侧边栏 232px（active 青柠左边条）+ 顶栏 52px（组织选择器）；数据密集。
7. **徽章**：圆点前缀 + 彩色（lime/pink/violet/success）。
8. 语义状态色仅限：success `#27a644` / warning `#f5a623` / danger `#e5484d`。
9. 中文界面文案保持不变（技术术语可保留英文）。

## 整体重构范围（发哥定义）

重构 = **布局、组件、样式全面重做**，保留：现有功能、路由、业务逻辑、中文文案。
不允许只换主题色就交差——每个页面的布局结构和组件视觉都要重新设计。

## 技术栈约束

- Next.js 15 + React 19 + Tailwind CSS 3 + shadcn/ui（Radix + cva）。
- 颜色通过 globals.css 的 CSS 变量接入（:root 与 .dark 统一深色），Tailwind 配置在 tailwind.config.ts。
- 优先改 token/主题层 + 布局组件，不改组件交互逻辑。

## 一般规则

- 中文交流；结论先行。
- 改动后提供验证方式（构建通过、页面检查）。
