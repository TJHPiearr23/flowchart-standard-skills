# flowchart-standard

> 按 ISO 5807 / GB 1526 绘制标准流程图的 AI 技能：你只描述「有哪些节点、谁连谁、走哪条分支」，脚本负责把图排得横平竖直、分支必标注、不穿框不糊线，并告出不合规之处。

![预览](docs/preview.png)

*上图为 `assets/examples/leave-approval.json` 的渲染结果：学术黑白风格，两次判定、一条虚线回退、两路审批汇聚。*

## 为什么不是 Mermaid

Mermaid 的自动布局无法保证流程图规范里的几条硬要求——同类符号等大、连线正交、分支必标注、单入口单出口、箭头不回调。它能画出「能看」的图，但评审时经不起细看。

本技能换了个思路：**把排版交给确定性渲染器，把规则交给校验器**，模型只负责业务逻辑的表达。

- 节点坐标由网格布局计算，不手写像素；
- 同类符号尺寸全局统一（宽 176）；
- 连线只走横竖两向，遇框自动绕行，无法避免的交叉画成「小半圆跨线」；
- 判定出边漏标注是**错误级**问题，不是建议。

## 能力

| 维度 | 覆盖 |
|---|---|
| 标准符号 | 六边形（准备作业）、矩形（处理）、菱形（判定）、圆角矩形（终止）、文件、已定义处理、输入/输出、圆形/五边形连接符、批注、汇合点 |
| 控制结构 | 顺序、条件（If-Else）、分支（Switch-Case）、循环（While / Do-While） |
| 视觉风格 | `academic` 学术黑白（默认，白底黑线、开口箭头、直角框、无图例）/ `color` 分类着色 |
| 交付格式 | 自包含单文件 HTML（可打印 PDF）+ 纯 SVG（插 Word/PPT） |
| 规范校验 | 20 条规则，E 级阻断交付，W 级提示 |

## 安装

```bash
git clone https://github.com/TJHPiearr23/flowchart-standard.git
cp -r flowchart-standard ~/.workbuddy/skills/
```

Windows 对应目录为 `C:\Users\<用户名>\.workbuddy\skills\flowchart-standard\`。放好后重启 WorkBuddy，在「设置 → 技能 → 已安装」中确认。

技能靠 `description` 自动触发：对话里说「画一张审批流程图」「把这段逻辑画成流程图」即可。

## 快速开始

```bash
python scripts/flowchart.py assets/examples/leave-approval.json -o out.html --svg out.svg
```

输出直接打印校验结果：

```
[校验] 节点 10 / 连线 11 / 判定 2 / 错误 0 / 提示 0
  OK 全部规范检查通过
```

## 描述文件

最小可用 spec（坐标不用写，布局自动算）：

```json
{
  "title": "用户登录流程",
  "subtitle": "图 1　用户登录校验流程",
  "style": "academic",
  "nodes": [
    {"id": "s",  "type": "start",    "text": "开始"},
    {"id": "p1", "type": "process",  "text": "输入账号密码"},
    {"id": "d1", "type": "decision", "text": "密码正确？"},
    {"id": "p2", "type": "process",  "text": "生成令牌"},
    {"id": "p3", "type": "process",  "text": "提示错误"},
    {"id": "e",  "type": "end",      "text": "结束"}
  ],
  "edges": [
    {"from": "s",  "to": "p1"},
    {"from": "p1", "to": "d1"},
    {"from": "d1", "to": "p2", "label": "是"},
    {"from": "d1", "to": "p3", "label": "否"},
    {"from": "p2", "to": "e"},
    {"from": "p3", "to": "e"}
  ]
}
```

字段全表见 [`references/dsl.md`](references/dsl.md)。

## 命令行

```bash
python scripts/flowchart.py spec.json                    # 生成同名 .html
python scripts/flowchart.py spec.json -o 图.html --svg 图.svg
python scripts/flowchart.py spec.json --check            # 只校验不落盘
python scripts/flowchart.py spec.json --check --strict   # 有 E 级问题返回码 1，可做 CI 门禁
```

## 校验规则（节选）

| 码 | 级别 | 含义 |
|---|---|---|
| E01 | 错误 | 开始节点缺失或多于一个 |
| E05 | 错误 | 节点没有出口，流程中断 |
| E06 | 错误 | 判定少于两条出边 |
| E08 | 错误 | 判定分支未标注 是/否/条件值 |
| E09 | 错误 | 判定出口全是回流 → 死循环 |
| E19 | 错误 | 结束节点有出边 |
| E07 | 提示 | 三分支以上缺少「默认」兜底 |
| E20 | 提示 | 存在交叉（已画跳线） |
| W13 | 提示 | 节点文字超过 16 字 |

完整 20 条见 [`references/dsl.md`](references/dsl.md#7-校验码表)。

## 目录结构

```
flowchart-standard/
├── SKILL.md                 技能入口：何时用、怎么走流程
├── scripts/flowchart.py     渲染器 + 校验器（唯一渲染入口，零第三方依赖）
├── references/
│   ├── symbols.md           标准符号表、易混符号取舍、风格约定
│   ├── structures.md        四大控制结构画法
│   ├── rules.md             五大排版铁律、错误对照、自检清单
│   └── dsl.md               spec 字段全表、布局规则、校验码
└── assets/examples/         5 份可直接改造的样例
```

## 环境

Python 3.8+，无第三方依赖。渲染结果为纯 HTML + 内联 SVG，不依赖任何 JS 运行时。
