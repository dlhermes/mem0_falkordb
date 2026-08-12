---
version: alpha
name: mem0-dashboard-sentry
description: "mem0 dashboard 整体重构设计规范：Sentry 风格（独立分析，非官方）——深紫午夜画布 (#150f23/#1f1633)、电光青柠 accent (#c2ef4e) 做主 CTA 与高亮、紫 (#6a5fc1) 与粉 (#fa7faa) 做辅助 accent、数据密集仪表盘气质。Rubik/Inter 字体，Monaco 等宽。整体重构范围：布局、组件、样式全面重做，保留现有功能与中文文案。"

colors:
  primary: "#c2ef4e"
  on-primary: "#1a2405"
  primary-hover: "#d4f56e"
  ink-deep: "#1f1633"
  ink: "#f7f6f9"
  ink-muted: "#bdb8c0"
  ink-subtle: "#8b8498"
  ink-faint: "#3f3849"
  canvas: "#150f23"
  canvas-dark: "#1f1633"
  surface-1: "#241a3d"
  surface-2: "#2b2048"
  surface-3: "#332657"
  hairline: "#362d59"
  hairline-strong: "#4a3f6e"
  accent-violet: "#6a5fc1"
  accent-violet-deep: "#422082"
  accent-violet-mid: "#79628c"
  accent-pink: "#fa7faa"
  ring-focus: "#9dc1f5"
  semantic-success: "#27a644"
  semantic-warning: "#f5a623"
  semantic-danger: "#e5484d"

typography:
  heading-xl:
    fontFamily: "Rubik, Inter, -apple-system, system-ui, sans-serif"
    fontSize: 30px
    fontWeight: 600
    lineHeight: 1.2
  heading-lg:
    fontFamily: "Rubik, Inter, -apple-system, system-ui, sans-serif"
    fontSize: 27px
    fontWeight: 600
    lineHeight: 1.25
  heading-md:
    fontFamily: "Rubik, Inter, -apple-system, system-ui, sans-serif"
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.25
  heading-sm:
    fontFamily: "Rubik, Inter, -apple-system, system-ui, sans-serif"
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.3
  body-lg:
    fontFamily: "Rubik, Inter, -apple-system, system-ui, sans-serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
  body:
    fontFamily: "Rubik, Inter, -apple-system, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  body-sm:
    fontFamily: "Rubik, Inter, -apple-system, system-ui, sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
  body-xs:
    fontFamily: "Rubik, Inter, -apple-system, system-ui, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "Rubik, Inter, -apple-system, system-ui, sans-serif"
    fontSize: 11px
    fontWeight: 700
    lineHeight: 1
    letterSpacing: 0.06em
    textTransform: uppercase
  code:
    fontFamily: "Monaco, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: 12.5px
    fontWeight: 400
    lineHeight: 1.5

rounded:
  sm: 6px
  md: 8px
  lg: 12px
  xl: 18px
  full: 9999px

spacing:
  xxs: 2px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
  section: 96px

components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body}"
    fontWeight: 600
    rounded: "{rounded.sm}"
    padding: "8px 14px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body}"
    fontWeight: 600
    rounded: "{rounded.sm}"
    padding: "8px 14px"
  button-dark:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline-strong}"
    typography: "{typography.body}"
    fontWeight: 600
    rounded: "{rounded.sm}"
    padding: "8px 14px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-muted}"
    borderColor: "{colors.hairline}"
    typography: "{typography.body}"
    fontWeight: 600
    rounded: "{rounded.sm}"
    padding: "7px 14px"
  sidebar:
    backgroundColor: "{colors.canvas-dark}"
    textColor: "{colors.ink-muted}"
    borderColor: "{colors.hairline}"
    width: 232px
  sidebar-item:
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.sm}"
    padding: "7px 10px"
  sidebar-item-active:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink}"
    borderLeft: "2px solid {colors.primary}"
  sidebar-label:
    textColor: "{colors.ink-subtle}"
    typography: "{typography.label}"
    padding: "14px 8px 6px 8px"
  topbar:
    backgroundColor: "{colors.canvas-dark}"
    borderColor: "{colors.hairline}"
    height: 52px
    padding: "0 20px"
  stat-card:
    backgroundColor: "{colors.canvas-dark}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    rounded: "{rounded.md}"
    padding: "14px 16px"
    accentBar: "linear-gradient(90deg, #c2ef4e, #6a5fc1, #fa7faa)"
  input:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    rounded: "{rounded.sm}"
    padding: "6px 10px"
    typography: "{typography.body}"
  input-focus:
    borderColor: "{colors.accent-violet}"
    boxShadow: "0 0 0 2px rgba(106,95,193,0.35)"
  badge:
    backgroundColor: "{colors.surface-3}"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.full}"
    padding: "2px 9px"
    typography: "{typography.body-xs}"
    fontWeight: 600
    dot: true
  badge-lime:
    backgroundColor: "rgba(194,239,78,0.12)"
    textColor: "{colors.primary}"
  badge-pink:
    backgroundColor: "rgba(250,127,170,0.12)"
    textColor: "{colors.accent-pink}"
  badge-violet:
    backgroundColor: "rgba(106,95,193,0.2)"
    textColor: "#a89fe0"
  badge-success:
    backgroundColor: "rgba(39,166,68,0.14)"
    textColor: "#4cc38a"
  table-header:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink-subtle}"
    typography: "{typography.label}"
    padding: "9px 16px"
  table-row:
    textColor: "{colors.ink-muted}"
    borderColor: "{colors.hairline}"
    padding: "10px 16px"
  table-row-hover:
    backgroundColor: "{colors.surface-1}"
  pill:
    borderColor: "{colors.hairline}"
    textColor: "{colors.ink-subtle}"
    rounded: "{rounded.full}"
    padding: "4px 12px"
    typography: "{typography.body-sm}"
    fontWeight: 500
  pill-active:
    backgroundColor: "{colors.accent-violet-mid}"
    textColor: "#ffffff"
    rounded: "{rounded.full}"
    padding: "4px 12px"
    typography: "{typography.body-sm}"
    fontWeight: 500

---

## Overview

mem0 dashboard 整体重构采用 Sentry 风格（独立分析）：**深紫午夜画布**（#150f23 最底层 / #1f1633 面板）是视觉基调，**电光青柠 #c2ef4e** 是唯一主 CTA/高亮色（深色文字），**紫 #6a5fc1 与粉 #fa7faa** 做辅助 accent（数据点、状态、装饰性强调），**hairline 紫边框 #362d59** 定义结构。整体气质：数据密集、开发者工具、有辨识度的色彩体系——与常见的深黑中性仪表盘拉开差距。

重构范围（发哥确认的定义）：**布局、组件、样式全面重做**，保留现有功能、路由、中文文案、业务逻辑。

## 布局（Layout）

- **侧边栏 232px**：canvas-dark 底色，分组标签（大写 11px label），active 项 = surface-2 背景 + 左侧 2px 青柠条，count 用 tabular-nums 徽标。
- **顶栏 52px**：左侧组织选择器（surface-1 底 + 青柠圆点 + 名称 + ▾），中间搜索框（focus 紫色光环），右侧操作按钮（ghost 导出 + primary 青柠新建）。
- **内容区 padding 20px**，卡片间距 12px——数据密集但不拥挤。
- **统计卡片**：canvas-dark 底 + 紫 hairline 边框 + 顶部 2px 渐变 accent 条（青柠→紫→粉），数值 26px/700 tabular-nums，delta 用青柠色（正）/灰（平）。可加 sparkline（紫/青柠柱）。
- **表格**：表头 canvas 底 + 大写 11px label，行 hover surface-1，行高 10px 16px（紧凑），状态徽章彩色圆点。

## 组件（Components）

- **按钮**：主操作 = 青柠底深字（#c2ef4e/#1a2405）；次操作 = 黑紫底白字 + hairline-strong 边框（#150f23）；幽灵 = 透明 + 紫 hairline 边框 + muted 文字。禁用 = 半透明。
- **徽章**：圆点前缀 + 彩色系（lime/pink/violet/success），底色为对应色 10-20% 透明。
- **输入框**：surface-1 底 + hairline 边框，focus = 紫边框 + 2px 紫光环（rgba(106,95,193,0.35)）。
- **卡片**：canvas-dark 底 + hairline 边框 + 8px 圆角；强调卡可用 accent-violet-deep 底。
- **Pill 筛选**：透明底 + hairline 边框；active = violet-mid 底白字。
- **弹层/浮层**：surface-3 底 + hairline-strong 边框，可带阴影（弹层是唯一允许阴影的地方）。

## 色彩纪律（Do's and Don'ts）

**Do:**
- 青柠 #c2ef4e 只用于：主 CTA、active 高亮、正值 delta、极少量品牌强调——它是"能量色"，用多了廉价。
- 紫 #6a5fc1 用于：focus 光环、辅助强调、sparkline、次级状态。
- 粉 #fa7faa 用于：数据点、装饰性 accent、对话类徽章。
- 背景层级：night #150f23（最底）→ canvas-dark #1f1633（面板）→ surface-1/2/3（递进）。
- 边框统一 hairline #362d59，强调用 hairline-strong #4a3f6e。
- 数字用 tabular-nums；代码/ID 用 Monaco 等宽。

**Don't:**
- 不要把青柠当背景色大面积使用。
- 不要引入第 4 个高饱和 accent 色（保持 lime/violet/pink 三色体系）。
- 不要在 dark 画布上用纯黑 #000（用 #150f23）。
- 不要用灰阶蓝（shadcn 默认 zinc/slate 系）作为主色调——本规范以紫调为底。
- 语义状态：success #27a644 / warning #f5a623 / danger #e5484d，仅此三个。

## 响应式

- <1024px：侧边栏折叠为抽屉。
- <768px：统计卡 2 列→1 列，表格横向滚动。
- 触摸目标 ≥32px。

## Agent Prompt Guide

- "使用 Sentry 风格：紫午夜画布 #150f23/#1f1633，青柠 #c2ef4e 主 CTA，紫 #6a5fc1 与粉 #fa7faa 辅助 accent，hairline 紫边框 #362d59。"
- "按钮：主=青柠底深字，次=黑紫底白字，幽灵=透明紫边框。"
- "徽章：圆点+彩色（lime/pink/violet/success）。"
- "统计卡：顶部渐变 accent 条 + tabular-nums 数值。"
- "布局：232px 侧边栏（active 青柠左边条）+ 52px 顶栏（组织选择器）。"
