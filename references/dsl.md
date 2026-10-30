# spec.json 完整参考

渲染器 `scripts/flowchart.py` 的输入是一份 JSON。坐标**不需要写**——由网格布局自动计算；只有在极少数需要人工干预时才用 `row` / `col`。

## 1. 顶层字段

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `title` | string | — | 图标题 |
| `subtitle` | string | — | 副标题；学术版可写成图题「图 1　xxx」 |
| `style` | `"standard"` \| `"academic"` \| `"color"` | `"standard"` | **标准彩色**（五类图形按类别着色）/ **学术黑白** / **浅色分类** |
| `theme` | `"light"` \| `"dark"` | `"light"` | 深色底适配（`standard` 会切到深色配色） |
| `start_shape` | `"stadium"` \| `"hexagon"` | standard→`stadium`，academic→`hexagon` | 开始/结束形状：胶囊（通用）或六边形（ISO 准备作业） |
| `show_legend` | bool | standard `false` / color `true` | 底部图例行 |
| `require_edge_labels` | bool | `false` | 置 `true` 后，任何未标注的连线都报 W25（业务流程图建议开） |
| `mermaid_html` | bool | `true` | Mermaid 标签是否用内联 HTML（`<br/>` 换行、`min-width` 等宽）。目标渲染器关掉了 `htmlLabels` 时置 `false`，标签退回纯文本单行 |
| `mermaid_curve` | `"linear"` \| `"stepAfter"` \| `"step"` | `"linear"` | Mermaid 连线形态：`linear` 两点直连不拐弯（默认）；`stepAfter` 单折直角；`step` 中间再折一次（不推荐） |
| `fragment` | bool | `false` | 片段模式：画跨页的「半张流程图」，跳过入口/出口/可达性检查 |
| `nodes` | array | 必填 | 节点列表，顺序即同层左右顺序 |
| `edges` | array | 必填 | 连线列表，顺序决定分支的左右次序 |
| `notes` | array | `[]` | 批注 |

## 2. 节点 node

```json
{"id": "d1", "type": "decision", "text": "是否注册？"}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 唯一标识，供 `edges` 引用，建议语义化（`d1`、`p_check`） |
| `type` | 是 | `start` `end` `process` `data`（别名 `io`）`decision` `predefined` `document` `connector_in` `connector_out` `junction` |
| `text` | 是 | 框内文字：流程写动词短语；判定写问句带「？」；数据写名词/消息；连接符只写编号 |
| `row` / `col` | 否 | 手动布局，**两者同时给出**才生效 |

## 3. 连线 edge

```json
{"from": "p1", "to": "p2", "label": "点击登录", "back": false, "style": "solid"}
```

| 字段 | 默认 | 说明 |
|---|---|---|
| `from` / `to` | 必填 | 节点 id |
| `label` | 空 | 判定出边**必须**填（是/否/条件值）；流程之间建议填动作（点击登录/提交表单） |
| `back` | `false` | 回流边（循环折返）。自动识别，但**显式写更稳** |
| `style` | `"solid"` | `"dashed"` 用于回流或弱化的辅助线 |

## 4. 批注 note

```json
{"text": "最多 3 次重试，超限锁定 15 分钟。", "near": "d2"}
```

`near` 指定锚点节点。渲染器按「右侧 → 上下避让 → 左侧 → 下方」找空位；都被占时落到图底批注区，并在文字前加 `〔锚点文字〕`。Mermaid 中以 `%% 注释：` 输出在末尾。

## 5. 自动布局规则

1. **分层**：从 `start` 出发做最长路径分层，一层一行。回流边不参与分层。
2. **分列**：主干恒在第 0 列；判定的旁路分支向右展开；多路分支按 `edges` 书写顺序依次占 0,1,2… 列。
3. **回流车道**：汇入同一节点的多条回流边各占一条左侧车道（逐条外扩 20px），不叠线；左侧同排有符号挡路时，先贴左缘进入行间空隙再横移到车道。
4. **汇入**：同一目标的多条入边自动错开入口，避免箭头堆在一起。
5. **连线**：只走横竖。向下直连；向右绕行从右侧出口进目标顶部；向左回汇从目标左侧进入，不横穿主干。
6. **避让**：横段会压到同层符号时，自动改成「贴右缘下行 → 行间空隙横移 → 下折入顶」的台阶路径。
7. **跳线**：不可避免的交叉自动画「小半圆跨线」，并报 E20 提示条数。
8. **尺寸**：同类图形尺寸全局统一（流程/数据 168×56，判定 176×96，起止 132×46）。

## 6. 命令行

```bash
python scripts/flowchart.py spec.json                    # -> spec.svg + spec.mmd，并打印 Mermaid
python scripts/flowchart.py spec.json -o 图.svg --mermaid 图.mmd
python scripts/flowchart.py spec.json --print-only       # 只打印 Mermaid 源码，不落盘
python scripts/flowchart.py spec.json --no-print         # 只落盘，不打印
python scripts/flowchart.py spec.json --check            # 只校验不落盘
python scripts/flowchart.py spec.json --check --strict   # 有 E 级问题返回码 1
python scripts/flowchart.py spec.json --html 图.html      # 可选：额外生成 HTML 预览页（默认不生成）
```

- **默认产物是 SVG + Mermaid**，SVG 内颜色全部内联，单独打开/插 Word/PPT 都正常显示，不依赖 CSS 变量或 JS。
- Mermaid 与 SVG 的图形一一对应（胶囊/矩形/平行四边形/菱形），classDef 与 SVG 同色，粘到支持 mermaid 的编辑器里就是同一张图的矢量版。
- 为了让 Mermaid 更接近标准流程图，源码头部固定带一段 `%%{init: ...}%%`：`curve: "linear"`（两点直连，不做多余拐弯；`mermaid_curve` 可改成 `stepAfter` 走直角）、`rankSpacing/nodeSpacing`（行距列距）、`edgeLabelBackground`（标签底色 = 画布色）；节点标签用 `<br/>` 按 SVG 同样规则换行，并用 `min-width` 把同类图形撑成等宽。**注意**：Mermaid 的 dagre 布局会自行决定分支左右（可能把「否」排到左边），这一项无法在源码里约束。

## 7. 校验码表

| 码 | 级别 | 含义 | 处理 |
|---|---|---|---|
| E00 | 错误 | 未知节点类型 | 改用 `start/end/process/data/decision` 等 |
| E01 | 错误 | 开始节点缺失或多于一个 | 补/删 start |
| E02 | 错误 | 缺结束节点 | 补 end |
| E04 | 错误 | 连线引用了不存在的节点 id | 改 id |
| E05 | 错误 | 节点没有出口（流程中断） | 补连线，或改类型为 end / connector_out |
| E06 | 错误 | 判定少于 2 条出边 | 补分支 |
| E08 | 错误 | 判定分支未标注 | 补 是/否/条件值 |
| E09 | 错误 | 判定出口全是回流 → 死循环 | 补终止出口 |
| E18 | 错误 | 开始节点有入边 | 删掉入边 |
| E19 | 错误 | 结束节点有出边 | 删掉出边 |
| E07 | 提示 | 纯多值判定（≥3 支）缺「默认」兜底 | 补默认分支 |
| E10 | 提示 | 节点从入口不可达 | 接线或删除 |
| E12 | 提示 | 判定文字未以「？」结尾 | 改成问句 |
| E16 | 提示 | 节点文字为空 | 补文字 |
| E20 | 提示 | 存在交叉（已画跳线） | 调分支顺序或拆图 |
| W02 | 提示 | 结束节点 >2 | 收敛出口 |
| W11 | 提示 | 文字超过该图形可容纳行数 | 压缩文字 |
| W13 | 提示 | 节点文字 >16 字 | 压成短语 |
| W14 | 提示 | 识别到未标注的回流边 | 显式写 `"back": true` |
| W21 | 提示 | 流程框写成问句 | 改用 `decision` 菱形 |
| W22 | 提示 | 数据框写成问句 | 判定请用 `decision` |
| W23 | 提示 | 数据框文字 >14 字 | 只写数据/消息名，细节移到 notes |
| W24 | 提示 | 多出口节点有连线未标注动作 | 补 `label` |
| W25 | 提示 | 连线未标注动作（`require_edge_labels` 开启时） | 补「点击登录」这类动作 |

`--strict` 只对 E 级返回非零，W 级不阻断交付。
