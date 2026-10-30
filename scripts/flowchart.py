#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flowchart.py — 标准流程图 DSL → Mermaid 源码 + 规范 SVG

用法:
    python flowchart.py spec.json                  # -> spec.svg + spec.mmd，并打印 Mermaid
    python flowchart.py spec.json -o 图.svg --mermaid 图.mmd
    python flowchart.py spec.json --check          # 只校验，不落盘
    python flowchart.py spec.json --print-only     # 只打印 Mermaid 源码
    python flowchart.py spec.json --html out.html  # 可选：额外生成预览页（默认不生成）

五类图形（本技能的唯一符号标准）:
    1. start / end   → 开始/结束   黑色胶囊（stadium），全图唯一入口，出口 1~2 个
    2. process       → 流程        绿色矩形，写动词短语
    3. data          → 数据        橙色平行四边形，写数据/消息/单据名
    4. decision      → 判定        蓝色菱形，写问句，≥2 条出边且每条必标注
    5. edges         → 连线        灰色箭头，标注动作（点击登录）或条件（是/否/账号错误）

设计约定:
    1. 坐标由网格布局自动计算，不手写像素；
    2. 同类图形尺寸全局统一；
    3. 连线只走横/竖两向，交叉处画小半圆跨线；
    4. 判定出边未标注 → 校验器直接报错。

DSL 完整说明见 references/dsl.md
"""

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------- 常量

VGAP = 52          # 行间距（行与行之间的净空）
HGAP = 80          # 列间距（列与列之间的净空）
MARGIN = 48        # 画布内边距
TITLE_H = 68       # 标题区高度
FS = 15            # 正文字号
FS_D = 14          # 判定框字号
LH = 1.5           # 行高倍数

FONT = "'Microsoft YaHei','PingFang SC','Noto Sans SC',system-ui,-apple-system,sans-serif"

# 图形定义：五类核心图形 + 扩展图形（尺寸全局统一，同类同尺寸）
SHAPE_DEFS = {
    # 1. 开始 / 结束 —— 黑色胶囊
    "start":         dict(w=132, h=46, shape="stadium",       pal="start",     max_lines=1),
    "end":           dict(w=132, h=46, shape="stadium",       pal="end",       max_lines=1),
    # 2. 流程 —— 绿色矩形
    "process":       dict(w=168, h=56, shape="rect",          pal="process",   max_lines=2),
    # 3. 数据 —— 橙色平行四边形（io 为兼容别名）
    "data":          dict(w=168, h=56, shape="parallelogram", pal="data",      max_lines=2),
    "io":            dict(w=168, h=56, shape="parallelogram", pal="data",      max_lines=2),
    # 4. 判定 —— 蓝色菱形
    "decision":      dict(w=176, h=96, shape="diamond",       pal="decision",  max_lines=3),
    # 扩展：子流程 / 文件 / 跨页连接符 / 汇合点
    "predefined":    dict(w=168, h=56, shape="predef",        pal="predef",    max_lines=2),
    "document":      dict(w=168, h=64, shape="document",      pal="document",  max_lines=2),
    "connector_in":  dict(w=52,  h=52, shape="circle",        pal="connector", max_lines=1),
    "connector_out": dict(w=52,  h=52, shape="pentagon",      pal="connector", max_lines=1),
    "junction":      dict(w=14,  h=14, shape="dot",           pal="connector", max_lines=0),
}

# 判定分支的「主路径」标签：这些走下方端口，其余走右侧端口
YES_LABELS = {"是", "y", "yes", "真", "true", "成立", "通过", "存在", "成功", "满足", "正确"}
DEFAULT_LABELS = {"默认", "其他", "其它", "else", "default", "剩余"}

PALETTES = {
    # 标准彩色（默认）：对齐通用业务流程图 / 教材配色
    "standard": {
        "canvas": "#FFFFFF", "ink": "#1F2933", "sub": "#4B5563", "edge": "#7A8699",
        "note": "#9AA3AF",
        "start_f": "#1F1F1F", "start_s": "#1F1F1F", "start_t": "#FFFFFF",
        "end_f": "#1F1F1F", "end_s": "#1F1F1F", "end_t": "#FFFFFF",
        "process_f": "#4CAF50", "process_s": "#3F9A44", "process_t": "#FFFFFF",
        "decision_f": "#2F80ED", "decision_s": "#2A72D4", "decision_t": "#FFFFFF",
        "data_f": "#F5A623", "data_s": "#DE9412", "data_t": "#FFFFFF",
        "predef_f": "#7B61FF", "predef_s": "#6A50E8", "predef_t": "#FFFFFF",
        "document_f": "#17A2B8", "document_s": "#138496", "document_t": "#FFFFFF",
        "io_f": "#F5A623", "io_s": "#DE9412", "io_t": "#FFFFFF",
        "connector_f": "#FFFFFF", "connector_s": "#6B7280", "connector_t": "#374151",
    },
    # 学术黑白：论文/毕设/评审文档用，纯墨线、不填色
    "mono": {
        "canvas": "#FFFFFF", "ink": "#111111", "sub": "#3D3D3D", "edge": "#111111",
        "note": "#767676",
        "start_f": "#FFFFFF", "start_s": "#111111", "start_t": "#111111",
        "end_f": "#FFFFFF", "end_s": "#111111", "end_t": "#111111",
        "process_f": "#FFFFFF", "process_s": "#111111", "process_t": "#111111",
        "decision_f": "#FFFFFF", "decision_s": "#111111", "decision_t": "#111111",
        "predef_f": "#FFFFFF", "predef_s": "#111111", "predef_t": "#111111",
        "document_f": "#FFFFFF", "document_s": "#111111", "document_t": "#111111",
        "data_f": "#FFFFFF", "data_s": "#111111", "data_t": "#111111",
        "io_f": "#FFFFFF", "io_s": "#111111", "io_t": "#111111",
        "connector_f": "#FFFFFF", "connector_s": "#111111", "connector_t": "#111111",
    },
    "light": {
        "canvas": "#FFFFFF", "ink": "#1F2933", "sub": "#6B7785", "edge": "#5A6472",
        "note": "#9AA3AF",
        "start_f": "#E1F4E9", "start_s": "#2F9E63", "start_t": "#0F5132",
        "end_f": "#E1F4E9", "end_s": "#2F9E63", "end_t": "#0F5132",
        "process_f": "#E8F1FC", "process_s": "#3B7DD8", "process_t": "#12395E",
        "decision_f": "#FFF3DC", "decision_s": "#D99B24", "decision_t": "#6A4708",
        "predef_f": "#EFECFA", "predef_s": "#6E5BC9", "predef_t": "#33296B",
        "document_f": "#E6F5F8", "document_s": "#2F93A8", "document_t": "#0E4653",
        "data_f": "#FDECEF", "data_s": "#C9536B", "data_t": "#6E2130",
        "io_f": "#FDECEF", "io_s": "#C9536B", "io_t": "#6E2130",
        "connector_f": "#F3F4F6", "connector_s": "#6B7280", "connector_t": "#374151",
    },
    "dark": {
        "canvas": "#14171C", "ink": "#E8ECF2", "sub": "#9BA6B4", "edge": "#A7B0BE",
        "note": "#7C8794",
        "start_f": "#0B0C0E", "start_s": "#4ADE80", "start_t": "#E8ECF2",
        "end_f": "#0B0C0E", "end_s": "#4ADE80", "end_t": "#E8ECF2",
        "process_f": "#1E6B33", "process_s": "#4ADE80", "process_t": "#EAFBF0",
        "decision_f": "#1B4C86", "decision_s": "#5B9BE8", "decision_t": "#E6F0FC",
        "predef_f": "#3B2E7A", "predef_s": "#9B8AE8", "predef_t": "#EDE9FE",
        "document_f": "#0F4A55", "document_s": "#4FB8CE", "document_t": "#DCF5FA",
        "data_f": "#8A5A0B", "data_s": "#E0A83A", "data_t": "#FDF3E0",
        "io_f": "#8A5A0B", "io_s": "#E0A83A", "io_t": "#FDF3E0",
        "connector_f": "#24272E", "connector_s": "#8B93A1", "connector_t": "#E5E7EB",
    },
}

# 视觉风格：standard = 标准彩色（默认），academic = 学术黑白，color = 浅色分类
STYLES = {
    "standard": dict(pal="standard", box_sw=1.4, edge_sw=1.5, rx=3, arrow="solid",
                     title_size=19, center_title=True, legend=False, bold=True),
    "academic": dict(pal="mono", box_sw=1.25, edge_sw=1.1, rx=0, arrow="open",
                     title_size=15, center_title=True, legend=False, bold=False),
    "color": dict(pal=None, box_sw=1.6, edge_sw=1.7, rx=4, arrow="solid",
                  title_size=21, center_title=False, legend=True, bold=True),
}

# Mermaid 图形映射：与 SVG 一一对应，保证两边语义一致
MERMAID_SHAPES = {
    "start":         ("([", "])"),   # 胶囊
    "end":           ("([", "])"),
    "process":       ("[", "]"),     # 矩形
    "decision":      ("{", "}"),     # 菱形
    "data":          ("[/", "/]"),   # 平行四边形
    "io":            ("[/", "/]"),
    "predefined":    ("[[", "]]"),
    "document":      ("[\\", "\\]"),
    "connector_in":  ("((", "))"),
    "connector_out": ("((", "))"),
    "junction":      ("((", "))"),
}


# ---------------------------------------------------------------- 数据结构

@dataclass
class Node:
    id: str
    type: str
    text: str
    idx: int = 0
    row: int = None
    col: int = None
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    lines: list = field(default_factory=list)

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2


@dataclass
class Edge:
    s: str
    t: str
    label: str = ""
    back: bool = False
    auto_back: bool = False
    style: str = "solid"
    route: str = "auto"
    idx: int = 0
    pts: list = field(default_factory=list)
    entry: str = "top"
    entry_off: float = 0.0


@dataclass
class Note:
    text: str
    near: str = ""
    x: float = 0.0
    y: float = 0.0
    w: float = 210.0
    h: float = 0.0
    leader: bool = True
    lines: list = field(default_factory=list)


# ---------------------------------------------------------------- 文本工具

def char_w(ch, fs):
    return fs if ord(ch) > 0x2E80 else fs * 0.56


def text_w(s, fs):
    return sum(char_w(c, fs) for c in s)


def wrap_text(s, max_w, fs):
    s = (s or "").strip()
    if not s:
        return [""]
    lines, cur, curw = [], "", 0.0
    for ch in s:
        cw = char_w(ch, fs)
        if curw + cw > max_w and cur:
            lines.append(cur)
            cur, curw = ch, cw
        else:
            cur += ch
            curw += cw
    if cur:
        lines.append(cur)
    return lines


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


# ---------------------------------------------------------------- 图

class Diagram:
    def __init__(self, spec):
        self.spec = spec
        self.title = spec.get("title", "")
        self.subtitle = spec.get("subtitle", "")
        self.style = spec.get("style", "standard")
        self.cfg = STYLES.get(self.style, STYLES["standard"])
        self.theme = spec.get("theme", "light")
        if self.cfg["pal"]:
            self.palette_name = self.cfg["pal"]
            if self.palette_name == "standard" and self.theme == "dark":
                self.palette_name = "dark"
        else:
            self.palette_name = self.theme if self.theme in PALETTES else "light"
        self.c = PALETTES[self.palette_name]
        self.show_legend = spec.get("show_legend", self.cfg["legend"])
        self.fragment = bool(spec.get("fragment", False))
        # 开始符号形状：stadium = 黑色胶囊（标准/默认）；hexagon = ISO 准备作业
        self.start_shape = spec.get("start_shape", "hexagon" if self.style == "academic" else "stadium")
        self.require_edge_labels = bool(spec.get("require_edge_labels", False))
        # Mermaid 标签是否允许内联 HTML（<br/> 换行、min-width 等宽）；渲染器不支持 htmlLabels 时关掉
        self.mermaid_html = bool(spec.get("mermaid_html", True))
        self.nodes = []
        self.edges = []
        self.notes = []
        self.issues = []      # (level, code, msg)
        self.canvas_w = 720
        self.canvas_h = 480
        self.left_pad = 0
        self._parse()
        # 回流边标签写在车道左侧，且多条回流边各占一条车道，需要额外左侧留白
        cnt = {}
        for e in self.edges:
            if e.back:
                cnt[e.t] = cnt.get(e.t, 0) + 1
        n_lane = max(cnt.values()) if cnt else 0
        w = max([text_w(e.label, 12.5) for e in self.edges
                 if e.back and (e.label or "").strip()] + [0])
        self.left_pad = (34 + max(0, n_lane - 1) * 20 + w + 18) if (w or n_lane) else 0

    # ---------- 解析
    def _parse(self):
        for i, raw in enumerate(self.spec.get("nodes", [])):
            t = raw.get("type", "process")
            if t not in SHAPE_DEFS:
                self.issues.append(("E", "E00", f"未知节点类型 {t!r}（id={raw.get('id')}）；"
                                                f"可用：{'/'.join(SHAPE_DEFS)}"))
                t = "process"
            d = SHAPE_DEFS[t]
            self.nodes.append(Node(
                id=raw.get("id") or f"n{i}", type=t, text=raw.get("text", ""),
                idx=i, row=raw.get("row"), col=raw.get("col"),
                w=d["w"], h=d["h"],
            ))
        index = {n.id: n for n in self.nodes}
        self.index = index
        for i, raw in enumerate(self.spec.get("edges", [])):
            s, t = raw.get("from"), raw.get("to")
            if s not in index or t not in index:
                self.issues.append(("E", "E04", f"连线引用了不存在的节点：{s} → {t}"))
                continue
            self.edges.append(Edge(s=s, t=t, label=raw.get("label", ""),
                                   back=bool(raw.get("back")), style=raw.get("style", "solid"),
                                   route=raw.get("route", "auto"), idx=i))
        for n in self.spec.get("notes", []):
            self.notes.append(Note(text=n.get("text", ""), near=n.get("near", "")))

    # ---------- 图查询
    def out_edges(self, nid, skip_back=True):
        return [e for e in self.edges if e.s == nid and not (skip_back and e.back)]

    def in_edges(self, nid, skip_back=True):
        return [e for e in self.edges if e.t == nid and not (skip_back and e.back)]

    def norm(self, label):
        return (label or "").strip().lower()

    def is_primary(self, e):
        src_out = self.out_edges(e.s)
        lab = self.norm(e.label)
        if lab in YES_LABELS:
            return True
        if lab and lab not in YES_LABELS:
            if src_out and src_out[0].idx == e.idx and len(
                    [x for x in src_out if self.norm(x.label) in YES_LABELS or not x.label]) == len(src_out):
                return True
            return False
        return bool(src_out) and src_out[0].idx == e.idx

    # ---------- 布局
    def layout(self):
        nodes = self.nodes
        if not nodes:
            return
        manual = all(n.row is not None and n.col is not None for n in nodes)
        if manual:
            for n in nodes:
                n.row, n.col = int(n.row), int(n.col)
        else:
            self._auto_levels()
            self._auto_cols()
        self._place()
        self._wrap_all()
        self._route_all()
        self._place_notes()

    def _detect_back_edges(self):
        """DFS 标记回流边：指向当前递归栈内节点的边即循环回流。"""
        color = {n.id: 0 for n in self.nodes}
        found = []

        def dfs(u):
            color[u] = 1
            for e in self.edges:
                if e.s != u or e.back:
                    continue
                if color[e.t] == 1:
                    found.append(e)
                elif color[e.t] == 0:
                    dfs(e.t)
            color[u] = 2

        sys.setrecursionlimit(10000)
        for n in self.nodes:
            if color[n.id] == 0:
                dfs(n.id)
        for e in found:
            e.back = True
            e.auto_back = True
            self.issues.append(("W", "W14",
                                f"连线「{self.index[e.s].text}」→「{self.index[e.t].text}」构成回环，"
                                f"已按回流边绘制（建议显式写 \"back\": true）"))

    def _auto_levels(self):
        """最长路径分层；back 边（循环回流）不参与分层。"""
        self._detect_back_edges()
        indeg = {n.id: 0 for n in self.nodes}
        for e in self.edges:
            if not e.back:
                indeg[e.t] += 1
        level = {n.id: 0 for n in self.nodes}
        queue = [n.id for n in self.nodes if indeg[n.id] == 0]
        order = []
        while queue:
            cur = queue.pop(0)
            order.append(cur)
            for e in self.out_edges(cur):
                level[e.t] = max(level[e.t], level[cur] + 1)
                indeg[e.t] -= 1
                if indeg[e.t] == 0:
                    queue.append(e.t)
        for n in self.nodes:
            if n.row is None:
                n.row = level[n.id]
        self._topo = order

    def _auto_cols(self):
        """主干恒在 col 0；判定旁路向右展开；多路分支按兄弟序递增。"""
        used = set()
        order = sorted(self.nodes, key=lambda n: (n.row, n.idx))
        for n in order:
            preds = [e for e in self.in_edges(n.id)]
            if not preds:
                col = 0
            elif len(preds) > 1:
                col = min(self.index[e.s].col or 0 for e in preds)
            else:
                e = preds[0]
                src = self.index[e.s]
                base = src.col if src.col is not None else 0
                if self.is_primary(e) or len(self.out_edges(src.id)) <= 1:
                    col = base
                else:
                    col = base + 1
            while (n.row, col) in used:
                col += 1
            used.add((n.row, col))
            n.col = col

    def _place(self):
        rows = sorted({n.row for n in self.nodes})
        cols = sorted({n.col for n in self.nodes})
        row_h = {r: max([n.h for n in self.nodes if n.row == r] + [0]) for r in rows}
        col_w = {c: max([n.w for n in self.nodes if n.col == c] + [0]) for c in cols}
        y_of, cur_y = {}, TITLE_H + (32 if self.subtitle else 0) + 14
        for r in rows:
            y_of[r] = cur_y
            cur_y += row_h[r] + VGAP
        x_of, cur_x = {}, MARGIN + self.left_pad
        for c in cols:
            x_of[c] = cur_x
            cur_x += col_w[c] + HGAP
        content_w = cur_x - HGAP + MARGIN
        for n in self.nodes:
            n.x = x_of[n.col] + (col_w[n.col] - n.w) / 2
            n.y = y_of[n.row] + (row_h[n.row] - n.h) / 2
        self.canvas_w = max(content_w, 700 + self.left_pad)
        self.content_x0 = MARGIN + self.left_pad
        self.base_h = cur_y - VGAP + MARGIN
        self.canvas_h = self.base_h + (84 if self.show_legend else 0)

    def _wrap_all(self):
        for n in self.nodes:
            if n.type == "decision":
                n.lines = wrap_text(n.text, n.w * 0.56, FS_D)
            elif n.type in ("connector_in", "connector_out"):
                n.lines = [n.text.strip()[:3]]
            elif n.type == "junction":
                n.lines = []
            elif n.type in ("data", "io"):
                n.lines = wrap_text(n.text, n.w - 52, FS)
            else:
                n.lines = wrap_text(n.text, n.w - 26, FS)
            limit = SHAPE_DEFS[n.type]["max_lines"]
            if limit and len(n.lines) > limit:
                self.issues.append(("W", "W11",
                                    f"节点「{n.text}」文字过长（{len(n.lines)} 行，上限 {limit} 行），"
                                    f"建议改为短语，说明移到 notes"))

    def _route_all(self):
        groups = {}
        for e in self.edges:
            if not e.back:
                groups.setdefault(e.t, []).append(e)
        for tgt, es in groups.items():
            tn = self.index[tgt]
            multi = len(es) > 1
            for i, e in enumerate(es):
                sn = self.index[e.s]
                if e.back:
                    e.entry = "left"
                    continue
                if abs(sn.cx - tn.cx) < 1:
                    e.entry = "top"
                    e.entry_off = 0.0
                elif sn.col < tn.col:
                    e.entry = "top"
                    e.entry_off = 0.0 if not multi else (i - (len(es) - 1) / 2) * 26
                else:
                    e.entry = "right"
                    e.entry_off = 0.0 if not multi else (i - (len(es) - 1) / 2) * 13
        # 回流边分配独立车道，避免多条虚线叠在一起
        lanes = {}
        for e in self.edges:
            sn, tn = self.index[e.s], self.index[e.t]
            if e.back or tn.cy < sn.cy - 2:
                lanes.setdefault(e.t, []).append(e)
        for tgt, es in lanes.items():
            for k, e in enumerate(es):
                e.lane_off = k
                e.lane_n = len(es)
        for e in self.edges:
            sn, tn = self.index[e.s], self.index[e.t]
            e.pts = self._route(sn, tn, e)

    def _route(self, s, t, e):
        gap = max((t.y - (s.y + s.h)), 28)
        if e.back or t.y < s.y - 2:
            # 回流：左侧专用车道。车道数 = 汇入同一目标的回流边数，逐条外扩
            lo = min(s.x, t.x)
            k, n = getattr(e, "lane_off", 0), getattr(e, "lane_n", 1)
            lane = lo - 34 - k * 20
            ty = t.cy + (k - (n - 1) / 2) * 12
            ty = max(t.y + 8, min(t.y + t.h - 8, ty))
            if self._hits_node(s.x - 2, s.cy, lane, (s.id, t.id)):
                # 左侧同排有符号挡路 → 先贴左缘进到行间空隙，再横移到车道
                gy = s.y - 16 if ty < s.cy else s.y + s.h + 16
                stub = s.x - 18
                return [(s.x, s.cy), (stub, s.cy), (stub, gy), (lane, gy), (lane, ty), (t.x, ty)]
            return [(s.x, s.cy), (lane, s.cy), (lane, ty), (t.x, ty)]
        if abs(s.cx - t.cx) < 1:
            return [(s.cx, s.y + s.h), (t.cx, t.y)]
        if t.col > s.col:
            if self._hits_node(s.x + s.w, s.cy, t.cx, (s.id, t.id)):
                jx = s.x + s.w + 14
                gy = s.y + s.h + min(16, max(gap / 3, 8))
                return [(s.x + s.w, s.cy), (jx, s.cy), (jx, gy), (t.cx, gy), (t.cx, t.y)]
            return [(s.x + s.w, s.cy), (t.cx, s.cy), (t.cx, t.y)]
        ey = t.cy + e.entry_off
        if self._hits_node(s.cx, ey, t.x + t.w, (s.id, t.id)):
            gy = t.y - min(28, max(gap / 2, 12))
            return [(s.cx, s.y + s.h), (s.cx, gy), (t.cx, gy), (t.cx, t.y)]
        return [(s.cx, s.y + s.h), (s.cx, ey), (t.x + t.w, ey)]

    def _hits_node(self, x1, y, x2, exclude=()):
        lo, hi = min(x1, x2), max(x1, x2)
        for n in self.nodes:
            if n.id in exclude:
                continue
            if n.y - 1 < y < n.y + n.h + 1 and not (hi <= n.x or lo >= n.x + n.w):
                return True
        return False

    def _place_notes(self):
        placed = []
        for nt in self.notes:
            nt.w = 210
            nt.lines = wrap_text(nt.text, nt.w - 24, 12.5)
            nt.h = max(44, len(nt.lines) * 12.5 * 1.55 + 18)
            anchor = self.index.get(nt.near)
            if anchor is None:
                nt.x, nt.y, nt.leader = MARGIN, self.base_h + 26, False
                placed.append(nt)
                continue
            cands = []
            for dy in (0, -40, 40, -80, 80, -124, 124, -168, 168):
                cands.append((anchor.x + anchor.w + 46, anchor.cy - nt.h / 2 + dy))
            for dy in (0, -40, 40, -80, 80):
                cands.append((anchor.x - nt.w - 46, anchor.cy - nt.h / 2 + dy))
            cands.append((anchor.cx - nt.w / 2, anchor.y - nt.h - 26))
            cands.append((anchor.cx - nt.w / 2, anchor.y + anchor.h + 32))
            spot = None
            for x, y in cands:
                if x < MARGIN or y < TITLE_H + 4:
                    continue
                if not self._note_free(x, y, nt.w, nt.h, placed):
                    continue
                spot = (x, y)
                break
            if spot:
                nt.x, nt.y, nt.leader = spot[0], spot[1], True
            else:
                nt.x, nt.y, nt.leader = MARGIN, self.base_h + 26, False
                nt.lines = wrap_text(f"〔{anchor.text}〕{nt.text}", nt.w - 24, 12.5)
                nt.h = max(44, len(nt.lines) * 12.5 * 1.55 + 18)
            placed.append(nt)
            self.canvas_w = max(self.canvas_w, nt.x + nt.w + MARGIN)

        foot = [t for t in placed if not t.leader]
        if foot:
            x, y, rowh = MARGIN, self.base_h + 22, 0
            for t in foot:
                if x + t.w > self.canvas_w - MARGIN:
                    x, y = MARGIN, y + rowh + 12
                t.x, t.y = x, y
                x += t.w + 14
                rowh = max(rowh, t.h)
            self.canvas_h = y + rowh + MARGIN + (84 if self.show_legend else 0)

    def _note_free(self, x, y, w, h, placed):
        for n in self.nodes:
            if not (x + w < n.x - 8 or x > n.x + n.w + 8 or y + h < n.y - 8 or y > n.y + n.h + 8):
                return False
        for e in self.edges:
            pts = e.pts
            for i in range(len(pts) - 1):
                (x1, y1), (x2, y2) = pts[i], pts[i + 1]
                if not (x + w < min(x1, x2) - 20 or x > max(x1, x2) + 20
                        or y + h < min(y1, y2) - 20 or y > max(y1, y2) + 20):
                    return False
        for t in placed:
            if not (x + w < t.x - 10 or x > t.x + t.w + 10 or y + h < t.y - 10 or y > t.y + t.h + 10):
                return False
        return True

    # ---------- SVG（颜色全部内联，SVG 单独拿走也能正常显示）
    def _shape(self, n):
        x, y, w, h = n.x, n.y, n.w, n.h
        k = SHAPE_DEFS[n.type]["shape"]
        p = SHAPE_DEFS[n.type]["pal"]
        c = self.c
        sw = self.cfg["box_sw"]
        rx = self.cfg["rx"]
        if n.type == "start" and self.start_shape == "hexagon":
            k = "hexagon"
        if n.type == "end" and self.start_shape == "hexagon":
            k = "hexagon"
        st = f'fill="{c[p + "_f"]}" stroke="{c[p + "_s"]}" stroke-width="{sw}"'
        if k == "hexagon":
            cw = h * 0.32
            pts = f"{x+cw},{y} {x+w-cw},{y} {x+w},{y+h/2} {x+w-cw},{y+h} {x+cw},{y+h} {x},{y+h/2}"
            return f'<polygon points="{pts}" {st} stroke-linejoin="miter"/>'
        if k == "stadium":
            return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2}" ry="{h/2}" {st}/>'
        if k == "rect":
            return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" {st}/>'
        if k == "diamond":
            pts = f"{x+w/2},{y} {x+w},{y+h/2} {x+w/2},{y+h} {x},{y+h/2}"
            return f'<polygon points="{pts}" {st} stroke-linejoin="miter"/>'
        if k == "predef":
            return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" {st}/>'
                    f'<line x1="{x+11}" y1="{y}" x2="{x+11}" y2="{y+h}" stroke="{c[p+"_s"]}" stroke-width="{sw}"/>'
                    f'<line x1="{x+w-11}" y1="{y}" x2="{x+w-11}" y2="{y+h}" stroke="{c[p+"_s"]}" stroke-width="{sw}"/>')
        if k == "document":
            wy = y + h - 10
            path = (f"M{x},{y} H{x+w} V{wy} "
                    f"C{x+w*0.75},{wy+13} {x+w*0.55},{wy-11} {x+w*0.32},{wy+2} "
                    f"C{x+w*0.18},{wy+9} {x+w*0.08},{wy-6} {x},{wy+1} Z")
            return f'<path d="{path}" {st}/>'
        if k == "parallelogram":
            s = 15
            pts = f"{x+s},{y} {x+w},{y} {x+w-s},{y+h} {x},{y+h}"
            return f'<polygon points="{pts}" {st} stroke-linejoin="miter"/>'
        if k == "circle":
            return f'<circle cx="{x+w/2}" cy="{y+h/2}" r="{w/2}" {st}/>'
        if k == "pentagon":
            pts = (f"{x+9},{y} {x+w-9},{y} {x+w},{y+h*0.46} {x+w/2},{y+h} {x},{y+h*0.46}")
            return f'<polygon points="{pts}" {st}/>'
        if k == "dot":
            return f'<circle cx="{x+w/2}" cy="{y+h/2}" r="{w/2}" fill="{c["edge"]}" stroke="none"/>'
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {st}/>'

    def _label(self, n):
        if not n.lines or all(not s for s in n.lines):
            return ""
        fs = FS_D if n.type == "decision" else FS
        if n.type in ("connector_in", "connector_out"):
            fs = 16
        top = n.cy - (len(n.lines) - 1) * fs * LH / 2
        span = "".join(
            f'<tspan x="{n.cx:.1f}" y="{top + i*fs*LH:.1f}">{esc(s)}</tspan>'
            for i, s in enumerate(n.lines))
        weight = "600" if self.cfg["bold"] else "400"
        p = SHAPE_DEFS[n.type]["pal"]
        return (f'<text text-anchor="middle" font-size="{fs}" font-weight="{weight}" '
                f'fill="{self.c[p + "_t"]}" '
                f'style="paint-order:stroke;stroke:{self.c[p + "_f"]};stroke-width:0.1">{span}</text>')

    def _arrow(self, p_from, p_to):
        dx, dy = p_to[0] - p_from[0], p_to[1] - p_from[1]
        L = (dx * dx + dy * dy) ** 0.5 or 1
        ux, uy = dx / L, dy / L
        if self.cfg["arrow"] == "open":
            ln, ang = 12.0, 0.34
            ca, sa = math.cos(ang), math.sin(ang)
            bx, by = -ux, -uy
            a = (bx * ca - by * sa, bx * sa + by * ca)
            b = (bx * ca + by * sa, -bx * sa + by * ca)
            return (f'<path d="M{p_to[0] + a[0]*ln:.1f},{p_to[1] + a[1]*ln:.1f} '
                    f'L{p_to[0]:.1f},{p_to[1]:.1f} '
                    f'L{p_to[0] + b[0]*ln:.1f},{p_to[1] + b[1]*ln:.1f}" fill="none" '
                    f'stroke="{self.c["edge"]}" stroke-width="{self.cfg["edge_sw"]}" '
                    f'stroke-linejoin="miter" stroke-linecap="round"/>')
        bx, by = p_to[0] - ux * 10, p_to[1] - uy * 10
        px, py = -uy * 4.8, ux * 4.8
        return (f'<polygon points="{p_to[0]:.1f},{p_to[1]:.1f} '
                f'{bx+px:.1f},{by+py:.1f} {bx-px:.1f},{by-py:.1f}" fill="{self.c["edge"]}"/>')

    def _compute_jumps(self):
        segs = []
        for e in self.edges:
            for i in range(len(e.pts) - 1):
                segs.append((e, i, e.pts[i], e.pts[i + 1]))
        jumps, count = {}, 0
        for i in range(len(segs)):
            for j in range(i + 1, len(segs)):
                e1, i1, a1, a2 = segs[i]
                e2, i2, b1, b2 = segs[j]
                if {e1.s, e1.t} & {e2.s, e2.t}:
                    continue
                h1, h2 = abs(a1[1] - a2[1]) < 0.5, abs(b1[1] - b2[1]) < 0.5
                if h1 == h2:
                    continue
                if not h1:
                    e1, i1, a1, a2, e2, i2, b1, b2 = e2, i2, b1, b2, e1, i1, a1, a2
                y, x = a1[1], b1[0]
                if not (min(a1[0], a2[0]) + 0.5 < x < max(a1[0], a2[0]) - 0.5):
                    continue
                if not (min(b1[1], b2[1]) + 0.5 < y < max(b1[1], b2[1]) - 0.5):
                    continue
                jumps.setdefault((e1.idx, i1), []).append((x, a2[0] > a1[0]))
                count += 1
        self.jumps = jumps
        self.cross_count = count

    def _edge_svg(self, e):
        pts = e.pts
        if not pts or len(pts) < 2:
            return ""
        p_end, p_prev = pts[-1], pts[-2]
        dx, dy = p_end[0] - p_prev[0], p_end[1] - p_prev[1]
        L = (dx * dx + dy * dy) ** 0.5 or 1
        tip = p_end
        if L > 12:
            pts = list(pts[:-1]) + [(p_end[0] - dx / L * 9, p_end[1] - dy / L * 9)]
        R = 5.5
        d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
        for i in range(len(pts) - 1):
            p, q = pts[i], pts[i + 1]
            horizontal = abs(p[1] - q[1]) < 0.5
            js = self.jumps.get((e.idx, i), []) if horizontal else []
            if js:
                right = q[0] > p[0]
                for x, _ in sorted(js, key=lambda t: t[0], reverse=not right):
                    if right:
                        d.append(f"L{x - R:.1f},{p[1]:.1f}")
                        d.append(f"A{R} {R} 0 0 1 {x + R:.1f},{p[1]:.1f}")
                    else:
                        d.append(f"L{x + R:.1f},{p[1]:.1f}")
                        d.append(f"A{R} {R} 0 0 0 {x - R:.1f},{p[1]:.1f}")
            d.append(f"L{q[0]:.1f},{q[1]:.1f}")
        dash = ' stroke-dasharray="6 5"' if e.style == "dashed" else ""
        return (f'<path d="{" ".join(d)}" fill="none" stroke="{self.c["edge"]}" '
                f'stroke-width="{self.cfg["edge_sw"]}" '
                f'stroke-linejoin="miter" stroke-linecap="butt"{dash}/>'
                + self._arrow(p_prev, tip))

    def _edge_label(self, e):
        if not (e.label or "").strip() or len(e.pts) < 2:
            return ""
        p0, p1 = e.pts[0], e.pts[1]
        first_len = abs(p0[0] - p1[0]) + abs(p0[1] - p1[1])
        if not e.back and first_len < 30 and len(e.pts) > 2:
            p0, p1 = max(zip(e.pts, e.pts[1:]),
                         key=lambda t: abs(t[0][0] - t[1][0]) + abs(t[0][1] - t[1][1]))
        halo = (f'style="paint-order:stroke;stroke:{self.c["canvas"]};stroke-width:4.5px;'
                f'stroke-linejoin:round"')
        if e.back:
            vs = [(abs(p[1] - q[1]), p, q) for p, q in zip(e.pts, e.pts[1:])
                  if abs(p[0] - q[0]) < 0.5]
            if vs:
                _, p, q = max(vs, key=lambda t: t[0])
                k, n = getattr(e, "lane_off", 0), getattr(e, "lane_n", 1)
                ly = (p[1] + q[1]) / 2 + (k - (n - 1) / 2) * 20 + 4
                return (f'<text x="{p[0] - 8:.1f}" y="{ly:.1f}" text-anchor="end" '
                        f'font-size="12.5" fill="{self.c["sub"]}" {halo}>{esc(e.label)}</text>')
            x, y, anchor = p0[0] - 7, p0[1] - 8, "end"
        elif abs(p0[0] - p1[0]) < 1:
            x, y = p0[0] + 12, (p0[1] + p1[1]) / 2 + 4
            anchor = "start"
        else:
            x, y = (p0[0] + p1[0]) / 2, p0[1] - 9
            anchor = "middle"
        return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="12.5" '
                f'fill="{self.c["sub"]}" {halo}>{esc(e.label)}</text>')

    LEGEND_ITEMS = [("start", "开始/结束"), ("process", "流程"), ("data", "数据"),
                    ("decision", "判定"), ("connector_in", "连接符")]

    def _legend_width(self):
        if not self.show_legend:
            return 0
        x = 0
        for t, lab in self.LEGEND_ITEMS:
            w = 20 if t == "connector_in" else 36
            x += w + 8 + text_w(lab, 12.5) + 26
        return x - 26 + 2 * MARGIN

    def _legend(self, y0):
        if not self.show_legend:
            return ""
        x = MARGIN
        out = []
        for t, lab in self.LEGEND_ITEMS:
            w, h = (34, 20) if t not in ("connector_in",) else (20, 20)
            sub = Node(id="_lg", type=t, text="", w=w, h=h)
            sub.x, sub.y = x, y0
            out.append(self._shape(sub))
            out.append(f'<text x="{x + w + 8}" y="{y0 + h/2 + 4.5}" font-size="12.5" '
                       f'fill="{self.c["sub"]}">{esc(lab)}</text>')
            x += w + 8 + text_w(lab, 12.5) + 26
        return f'<g>{"".join(out)}</g>'

    def to_svg(self):
        self._compute_jumps()
        self.canvas_w = max(self.canvas_w, self._legend_width())
        o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.canvas_w:.0f} {self.canvas_h:.0f}" '
             f'width="{self.canvas_w:.0f}" height="{self.canvas_h:.0f}" '
             f'font-family="{FONT}" role="img" aria-label="{esc(self.title or "流程图")}">',
             f'<rect width="100%" height="100%" fill="{self.c["canvas"]}"/>']
        if self.title:
            cx_title = (getattr(self, "content_x0", MARGIN) + self.canvas_w - MARGIN) / 2
            if self.cfg["center_title"]:
                o.append(f'<text x="{cx_title:.0f}" y="{MARGIN + 2}" text-anchor="middle" '
                         f'font-size="{self.cfg["title_size"]}" font-weight="600" '
                         f'fill="{self.c["ink"]}">{esc(self.title)}</text>')
                if self.subtitle:
                    o.append(f'<text x="{cx_title:.0f}" y="{MARGIN + 24}" text-anchor="middle" '
                             f'font-size="12" fill="{self.c["sub"]}">{esc(self.subtitle)}</text>')
            else:
                o.append(f'<text x="{self.content_x0}" y="{MARGIN + 4}" '
                         f'font-size="{self.cfg["title_size"]}" font-weight="600" '
                         f'fill="{self.c["ink"]}">{esc(self.title)}</text>')
                if self.subtitle:
                    o.append(f'<text x="{MARGIN}" y="{MARGIN + 30}" font-size="13" '
                             f'fill="{self.c["sub"]}">{esc(self.subtitle)}</text>')
        elif self.subtitle:
            o.append(f'<text x="{self.canvas_w/2 if self.cfg["center_title"] else MARGIN:.0f}" '
                     f'y="{MARGIN + 4}" font-size="12" fill="{self.c["sub"]}">{esc(self.subtitle)}</text>')
        o.append('<g id="edges">' + "".join(self._edge_svg(e) for e in self.edges) + "</g>")
        o.append('<g id="nodes">' + "".join(self._shape(n) + self._label(n) for n in self.nodes) + "</g>")
        o.append('<g id="edge-labels">' + "".join(self._edge_label(e) for e in self.edges) + "</g>")
        if self.notes:
            nb = []
            for nt in self.notes:
                nb.append(f'<rect x="{nt.x}" y="{nt.y}" width="{nt.w}" height="{nt.h}" rx="3" '
                          f'fill="none" stroke="{self.c["note"]}" stroke-width="1.2" stroke-dasharray="5 4"/>')
                for i, line in enumerate(nt.lines):
                    nb.append(f'<text x="{nt.x+12}" y="{nt.y + 21 + i*12.5*1.55:.1f}" font-size="12.5" '
                              f'fill="{self.c["sub"]}">{esc(line)}</text>')
                a = self.index.get(nt.near)
                if a and nt.leader:
                    nb.append(f'<line x1="{a.x + a.w}" y1="{a.cy}" x2="{nt.x}" y2="{nt.y + nt.h/2}" '
                              f'stroke="{self.c["note"]}" stroke-width="1.2" stroke-dasharray="4 4"/>')
            o.append('<g id="notes">' + "".join(nb) + "</g>")
        o.append(self._legend(self.canvas_h - 56))
        o.append("</svg>")
        return "\n".join(o)

    # ---------- Mermaid
    def _mid(self, nid):
        """Mermaid 节点 id：只留字母数字下划线，且不以数字开头。"""
        s = re.sub(r"[^\w]", "_", nid)
        if not s or s[0].isdigit():
            s = "n_" + s
        return s

    def _mermaid_edge_order(self):
        """保持 spec 中的连线顺序。

        Mermaid 的 dagre 用全局最少交叉做排序，声明顺序只是弱提示；实测强行重排
        「是」优先会把主干顶偏、主流程线出现折角，反而更不像标准图，因此不做干预。
        """
        return list(self.edges)

    def _mermaid_label(self, n, uniform):
        """节点标签：按 SVG 的换行结果输出 <br/>；同类型图形用 min-width 对齐宽度。

        标准图要求「同类图形等大」，而 Mermaid 默认按文字自适应宽度，同一列会出现
        4 字框和 9 字框混排。这里用 inline-block + min-width 把同类标签撑到统一宽度，
        文字仍然居中，视觉上就与 SVG 的等宽矩形一致。
        """
        lines = [x for x in (n.lines or [n.text]) if x != ""] or [n.text or ""]
        if not self.mermaid_html:
            # 纯文本模式：不能出现 <br/>，长句用空格分隔
            return " ".join(lines).replace('"', "#quot;")
        txt = "<br/>".join(lines).replace('"', "#quot;")
        em = uniform.get(n.type)
        if not em:
            return txt
        return (f"<span style='display:inline-block;min-width:{em}em;text-align:center'>"
                f"{txt}</span>")

    def to_mermaid(self):
        """输出可二次编辑的 Mermaid 源码。

        为了让 Mermaid 渲染结果尽量贴近标准流程图，源码里固定写入四件事：
        1. init 指令：curve=step（正交折线，不用默认的贝塞尔曲线）、加大 rank/node 间距；
        2. 节点文字按 SVG 同样的规则换行（<br/>），避免长文本把框拉成横条；
        3. 同类图形用 min-width 撑成等宽（可用 "mermaid_html": false 关闭）；
        4. classDef 与 SVG 同色同线宽，边标签底色 = 画布色。
        """
        c = self.c
        cfg = {
            "theme": "base",
            "themeVariables": {
                "fontFamily": "Microsoft YaHei, PingFang SC, Noto Sans SC, sans-serif",
                "fontSize": "14px",
                "lineColor": c["edge"],
                "edgeLabelBackground": c["canvas"],
                "primaryTextColor": c["ink"],
                "primaryBorderColor": c["edge"],
            },
            "flowchart": {
                "curve": "step",
                "htmlLabels": True,
                "useMaxWidth": False,
                "nodeSpacing": 44,
                "rankSpacing": 58,
                "padding": 12,
            },
        }
        # 同类图形的统一宽度（em）：取该类型中最宽的一行文字 + 内边距
        # 菱形要在左右顶点收窄处留白，胶囊要够宽才像「开始/结束」，因此各类型留白不同
        pad = {"decision": 2.6, "start": 3.2, "end": 3.2, "document": 1.0}
        uniform = {}
        for t in ("process", "data", "io", "predefined", "document", "decision"):
            ws = [max(text_w(l, 14) for l in (n.lines or [n.text]))
                  for n in self.nodes if n.type == t]
            if ws:
                uniform[t] = round(max(ws) / 14 + pad.get(t, 0.8), 1)
        # 开始/结束同类同尺寸：取两者中较宽的一条，两个胶囊等宽
        se = [max(text_w(l, 14) for l in (n.lines or [n.text]))
              for n in self.nodes if n.type in ("start", "end")]
        if se:
            uniform["start"] = uniform["end"] = round(max(se) / 14 + 3.2, 1)

        L = ["%%{init: " + json.dumps(cfg, ensure_ascii=False) + "}%%"]
        if self.title:
            L.append(f"%% {self.title}")
        if self.subtitle:
            L.append(f"%% {self.subtitle}")
        L.append("flowchart TD")

        for n in self.nodes:
            l, r = MERMAID_SHAPES.get(n.type, ("[", "]"))
            # 学术风格用六边形「准备作业」时，Mermaid 也跟着换，保证两边同形
            if n.type in ("start", "end") and self.start_shape == "hexagon":
                l, r = ("{{", "}}")
            L.append(f'    {self._mid(n.id)}{l}"{self._mermaid_label(n, uniform)}"{r}')

        for e in self._mermaid_edge_order():
            a = "-.->" if (e.back or e.style == "dashed") else "-->"
            lab = (e.label or "").strip().replace('"', "#quot;")
            if lab:
                L.append(f'    {self._mid(e.s)} {a}|"{lab}"| {self._mid(e.t)}')
            else:
                L.append(f'    {self._mid(e.s)} {a} {self._mid(e.t)}')

        defs = [
            ("startEnd", c["start_f"], c["start_s"], c["start_t"]),
            ("process", c["process_f"], c["process_s"], c["process_t"]),
            ("decision", c["decision_f"], c["decision_s"], c["decision_t"]),
            ("data", c["data_f"], c["data_s"], c["data_t"]),
            ("predef", c["predef_f"], c["predef_s"], c["predef_t"]),
            ("doc", c["document_f"], c["document_s"], c["document_t"]),
            ("connector", c["connector_f"], c["connector_s"], c["connector_t"]),
        ]
        L.append("")
        for name, f, s, t in defs:
            L.append(f"    classDef {name} fill:{f},stroke:{s},stroke-width:1.4px,color:{t};")
        buckets = {}
        for n in self.nodes:
            key = {"start": "startEnd", "end": "startEnd", "process": "process",
                   "decision": "decision", "data": "data", "io": "data",
                   "predefined": "predef", "document": "doc"}.get(n.type, "connector")
            buckets.setdefault(key, []).append(self._mid(n.id))
        for key, ids in buckets.items():
            L.append(f"    class {','.join(ids)} {key};")
        L.append(f"    linkStyle default stroke:{c['edge']},stroke-width:1.5px;")
        if self.notes:
            L.append("")
            for nt in self.notes:
                anchor = self.index.get(nt.near)
                pre = f"〔{anchor.text}〕" if anchor else ""
                L.append(f"    %% 注释：{pre}{nt.text}")
        return "\n".join(L)

    def to_html(self):
        """可选：把自包含 SVG 包成一张可打印的预览页（默认不生成）。"""
        svg = self.to_svg()
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>{esc(self.title or "流程图")}</title>
<style>
  html,body{{margin:0;background:{self.c['canvas']};color:{self.c['ink']};font-family:{FONT}}}
  body{{display:flex;justify-content:center;padding:24px 20px}}
  svg{{display:block;max-width:100%;height:auto}}
  @media print{{body{{padding:0}}@page{{margin:12mm}}}}
</style>
</head>
<body>
{svg}
</body>
</html>
"""

    # ---------- 校验
    def validate(self):
        if not hasattr(self, "cross_count"):
            self._compute_jumps()
        issues = list(self.issues)
        idx = self.index
        starts = [n for n in self.nodes if n.type == "start"]
        ends = [n for n in self.nodes if n.type == "end"]
        decisions = [n for n in self.nodes if n.type == "decision"]

        # 规则 1：开始 / 结束
        if len(starts) == 0 and not self.fragment:
            issues.append(("E", "E01", "缺少开始节点：必须有且仅有一个 type=start（开始胶囊）"))
        if len(starts) > 1:
            issues.append(("E", "E01", f"开始节点有 {len(starts)} 个：一份流程图只能有一个入口"))
        if not ends and not self.fragment:
            issues.append(("E", "E02", "缺少结束节点：必须有 type=end（结束胶囊）"))
        if len(ends) > 2:
            issues.append(("W", "W02", f"结束节点有 {len(ends)} 个，建议收敛为 1~2 个（主流程 + 异常出口）"))

        for n in self.nodes:
            if n.type == "start" and self.in_edges(n.id, skip_back=False):
                issues.append(("E", "E18", f"开始节点「{n.text}」不应有入边"))
            if n.type == "end" and self.out_edges(n.id, skip_back=False):
                issues.append(("E", "E19", f"结束节点「{n.text}」不应有出边"))
            if (n.type not in ("end", "connector_out") and not self.out_edges(n.id, skip_back=False)
                    and not self.fragment):
                issues.append(("E", "E05", f"节点「{n.text}」没有出口，流程在此中断"
                                           f"（若非终止请改用 end 或 connector_out）"))
            if not n.text.strip() and n.type not in ("junction",):
                issues.append(("W", "E16", f"节点 {n.id} 文字为空"))

        # 规则 4：判定
        for d in decisions:
            outs = self.out_edges(d.id)
            all_out = self.out_edges(d.id, skip_back=False)
            if len(all_out) < 2:
                issues.append(("E", "E06", f"判定「{d.text}」只有 {len(all_out)} 条出边：判定必须至少「是/否」两路"))
            for e in all_out:
                if not (e.label or "").strip():
                    issues.append(("E", "E08", f"判定「{d.text}」→「{idx[e.t].text}」的分支未标注，"
                                               f"必须写 是/否/Y/N 或条件值"))
            if len(outs) >= 3:
                labs = {self.norm(e.label) for e in outs}
                # 已枚举「是 + 各异常」的判定视为覆盖完整；纯多值分支才要求「默认」兜底
                if not (labs & DEFAULT_LABELS) and not (labs & YES_LABELS):
                    issues.append(("W", "E07", f"判定「{d.text}」有 {len(outs)} 个分支，缺少「默认/其他」兜底路径"))
            if not (d.text or "").strip().endswith(("？", "?")):
                issues.append(("W", "E12", f"判定「{d.text}」建议写成问句并以「？」结尾"))
            if not self.out_edges(d.id):
                issues.append(("E", "E09", f"判定「{d.text}」的所有出口都是回流边：缺少跳出循环的出口，可能死循环"))

        # 规则 2：流程框不应写成问句（应改判定）
        for n in self.nodes:
            if n.type == "process" and (n.text or "").strip().endswith(("？", "?")):
                issues.append(("W", "W21", f"流程「{n.text}」是问句：多走向节点请改用 type=decision（菱形）"))

        # 规则 3：数据图形
        for n in self.nodes:
            if n.type in ("data", "io"):
                t = (n.text or "").strip()
                if t.endswith(("？", "?")):
                    issues.append(("W", "W22", f"数据框「{t}」不应写问句：判定请用 decision"))
                elif len(t) > 14:
                    issues.append(("W", "W23", f"数据框「{t}」过长（>14 字），只写数据/消息名，细节移到 notes"))

        # 规则 5：连线标注
        for e in self.edges:
            if (e.label or "").strip():
                continue
            src = idx[e.s]
            outs = self.out_edges(e.s)
            if src.type != "decision" and len(outs) > 1:
                issues.append(("W", "W24", f"「{src.text}」有多条出边，其中一条未标注动作：请补 label"))
            elif self.require_edge_labels and src.type not in ("start", "junction"):
                issues.append(("W", "W25", f"连线「{src.text}」→「{idx[e.t].text}」未标注动作"
                                           f"（如「点击登录」「提交表单」）"))

        # 可达性
        roots = [n.id for n in self.nodes if n.type in ("start", "connector_in")] if self.fragment \
            else ([starts[0].id] if starts else [])
        if roots:
            seen, q = set(roots), list(roots)
            while q:
                cur = q.pop()
                for e in self.edges:
                    if e.s == cur and e.t not in seen:
                        seen.add(e.t)
                        q.append(e.t)
            for n in self.nodes:
                if n.id not in seen:
                    issues.append(("W", "E10", f"节点「{n.text or n.id}」从入口不可达"))

        cross = getattr(self, "cross_count", 0)
        if cross:
            issues.append(("W", "E20", f"检测到 {cross} 处连线交叉：已自动绘制「小半圆跨线」，"
                                       f"如需彻底消除请调整分支顺序或拆分主流程/子流程"))

        for n in self.nodes:
            if len((n.text or "").strip()) > 16 and n.type not in ("document",):
                issues.append(("W", "W13", f"节点「{n.text}」超过 16 字，建议压缩为短语"))
        return issues


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description="标准流程图渲染：Mermaid 源码 + 规范 SVG")
    ap.add_argument("spec", help="spec.json 路径")
    ap.add_argument("-o", "--out", default=None, help="输出 SVG（默认同名 .svg）")
    ap.add_argument("--mermaid", default=None, help="输出 Mermaid 源码（默认同名 .mmd）")
    ap.add_argument("--html", default=None, help="可选：额外输出 HTML 预览页（默认不生成）")
    ap.add_argument("--print-only", action="store_true", help="只把 Mermaid 打到标准输出，不落盘")
    ap.add_argument("--no-print", action="store_true", help="不打印 Mermaid 源码")
    ap.add_argument("--check", action="store_true", help="只做规范校验")
    ap.add_argument("--strict", action="store_true", help="存在 E 级问题时退出码为 1")
    args = ap.parse_args()

    p = Path(args.spec)
    if not p.exists():
        print(f"[x] 找不到文件：{p}")
        sys.exit(2)
    spec = json.loads(p.read_text(encoding="utf-8"))
    dg = Diagram(spec)
    dg.layout()
    mermaid = dg.to_mermaid()

    if not args.check and not args.print_only:
        out = Path(args.out) if args.out else p.with_suffix(".svg")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dg.to_svg(), encoding="utf-8")
        print(f"[+] SVG    : {out}")

        mm = Path(args.mermaid) if args.mermaid else p.with_suffix(".mmd")
        mm.parent.mkdir(parents=True, exist_ok=True)
        mm.write_text(mermaid, encoding="utf-8")
        print(f"[+] Mermaid: {mm}")

        if args.html:
            hp = Path(args.html)
            hp.parent.mkdir(parents=True, exist_ok=True)
            hp.write_text(dg.to_html(), encoding="utf-8")
            print(f"[+] HTML   : {hp}（可选产物）")

    if not args.check and not args.no_print:
        print("\n----- MERMAID -----")
        print(mermaid)
        print("----- END -----\n")

    if not args.print_only:
        issues = dg.validate()
        E = [i for i in issues if i[0] == "E"]
        W = [i for i in issues if i[0] == "W"]
        tag = "（片段模式：跳过入口/出口/可达性检查）" if dg.fragment else ""
        print(f"[校验] 节点 {len(dg.nodes)} / 连线 {len(dg.edges)} / 判定 "
              f"{len([n for n in dg.nodes if n.type=='decision'])} / 错误 {len(E)} / 提示 {len(W)}{tag}")
        for lvl, code, msg in E + W:
            print(f"  {'[E]' if lvl == 'E' else '[W]'} {code} {msg}")
        if not issues:
            print("  OK 全部规范检查通过")
        if args.strict and E:
            sys.exit(1)


if __name__ == "__main__":
    main()
