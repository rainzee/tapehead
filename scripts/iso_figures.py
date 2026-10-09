"""生成 tapehead 的等轴测线框插画 (iso figures 风格), 输出到 assets/iso-figures"""

import itertools
import math
from collections.abc import Callable
from pathlib import Path

type P3 = tuple[float, float, float]

C = math.cos(math.pi / 6)
S = 0.5
ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "assets" / "iso-figures"


def proj(x: float, y: float, z: float) -> tuple[float, float]:
    return ((x - y) * C, (x + y) * S - z)


def matrix(o: P3, u: P3, v: P3) -> str:
    """把面内二维坐标系 (原点 o, 轴 u, v) 映射到屏幕的仿射矩阵"""

    (ox, oy), (ux, uy), (vx, vy) = proj(*o), proj(*u), proj(*v)
    return f"matrix({ux:.4f} {uy:.4f} {vx:.4f} {vy:.4f} {ox:.2f} {oy:.2f})"


# 三种面: 顶面 u=+x v=+y, 正面 (y 最大) u=+x v=-z, 侧面 (x 最大) u=-y v=-z
PLANES: dict[str, tuple[P3, P3]] = {
    "top": ((1, 0, 0), (0, 1, 0)),
    "front": ((1, 0, 0), (0, 0, -1)),
    "side": ((0, -1, 0), (0, 0, -1)),
}


# ---------- 面内二维小件 ----------


def rect(x: float, y: float, w: float, h: float, r: float = 0, cls: str = "face recess") -> str:
    return f'<rect class="{cls}" x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{r:g}"/>'


def circ(cx: float, cy: float, r: float, cls: str = "face", extra: str = "") -> str:
    return f'<circle class="{cls}" cx="{cx:g}" cy="{cy:g}" r="{r:g}"{extra}/>'


def ln(x1: float, y1: float, x2: float, y2: float, cls: str = "detail") -> str:
    return f'<line class="{cls}" x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}"/>'


def text(x: float, y: float, s: str, size: float = 5, anchor: str = "start", ls: float = 0.6, cls: str = "label") -> str:
    return (
        f'<text class="{cls}" x="{x:g}" y="{y:g}" font-size="{size:g}" '
        f'text-anchor="{anchor}" letter-spacing="{ls:g}">{s}</text>'
    )


def slits(a0: float, a1: float, step: float, b0: float, b1: float, vertical: bool = True) -> str:
    out, a = [], a0
    while a <= a1 + 1e-6:
        out.append(ln(a, b0, a, b1) if vertical else ln(b0, a, b1, a))
        a += step
    return "".join(out)


def screw(x: float, y: float) -> str:
    return circ(x, y, 3, "face recess") + ln(x - 1.8, y, x + 1.8, y)


def led(x: float, y: float, hot: bool = False, r: float = 1.8, anim: str = "", delay: float = 0) -> str:
    """指示灯, anim 为 blink / breathe / seq 等动画类"""

    cls = ("led hot" if hot else "led") + (f" {anim}" if anim else "")
    extra = ' filter="url(#soft)"' if hot or anim else ""
    if delay:
        extra += f' style="animation-delay:{delay:g}s"'
    return circ(x, y, r, cls, extra)


def halo(x: float, y: float, r: float, anim: str = "") -> str:
    return circ(x, y, r, f"halo {anim}".strip(), ' filter="url(#bloom)"')


def footprint(x: float, y: float, w: float, d: float, r: float, n: int = 16) -> list[tuple[float, float]]:
    """圆角矩形外形的采样点, 按顺时针排列"""

    if r <= 0:
        return [(x, y), (x + w, y), (x + w, y + d), (x, y + d)]
    pts = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + d - r, 0), (x + r, y + d - r, 90), (x + r, y + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def hull(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """二维凸包, 单调链算法"""

    ps = sorted({(round(a, 3), round(b, 3)) for a, b in pts})

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    upper: list[tuple[float, float]] = []
    for p in ps:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(ps):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


# ---------- 动画 ----------

CLIP_IDS = itertools.count()


def g(inner: str, cls: str, style: str = "") -> str:
    s = f' style="{style}"' if style else ""
    return f'<g class="{cls}"{s}>{inner}</g>'


def spin(cx: float, cy: float, inner: str, dur: float = 6, rev: bool = False) -> str:
    """在面内坐标系里绕 (cx, cy) 旋转, 投影后就是等轴测平面上的转动"""

    return g(inner, "spin rev" if rev else "spin", f"transform-origin:{cx:g}px {cy:g}px;animation-duration:{dur:g}s")


def clip(w: float, h: float, inner: str) -> str:
    """面内矩形裁剪, 让走带的帧格不越出带面"""

    cid = f"clip{next(CLIP_IDS)}"
    return f'<clipPath id="{cid}"><rect width="{w:g}" height="{h:g}"/></clipPath><g clip-path="url(#{cid})">{inner}</g>'


def reel(cx: float, cy: float, r: float, wound: float = 0) -> str:
    """俯视的带轮: 轮盘, 带饼, 轮毂与三个减重孔"""

    s = circ(cx, cy, r)
    if wound:
        s += circ(cx, cy, wound, "detail")
    s += circ(cx, cy, r * 0.36, "face top") + circ(cx, cy, r * 0.13, "face recess")
    for t in (90, 210, 330):
        a = math.radians(t)
        s += circ(cx + r * 0.62 * math.cos(a), cy + r * 0.62 * math.sin(a), r * 0.16, "face recess")
    return s


class Fig:
    """一幅等轴测插画, 按画家算法顺序收集 svg 片段"""

    def __init__(self, key: str, name: str, note: str):
        self.key, self.name, self.note = key, name, note
        self.parts: list[str] = []
        self.bounds: list[tuple[float, float]] = []

    def track(self, *pts: P3):
        self.bounds.extend(proj(*p) for p in pts)

    def on(self, plane: str, o: P3, w: float, h: float, inner: str, filt: str = ""):
        """在某个面上绘制面内二维内容, o 为该面局部坐标原点"""

        u, v = PLANES[plane]
        m = matrix(o, u, v)
        self.track(o, tuple(o[i] + u[i] * w + v[i] * h for i in range(3)))
        f = f' filter="url(#{filt})"' if filt else ""
        self.parts.append(f'<g transform="{m}"{f}>{inner}</g>')

    def box(
        self,
        x: float, y: float, z: float, w: float, d: float, h: float, r: float = 0,
        cls: str = "", top: str = "", front: str = "", side: str = "", filt: str = "",
    ):
        """圆角长方体, 即圆角矩形底面竖直拉伸

        侧壁是一整块轮廓 (上下两圈外形的凸包), 圆角处用两条切线示意,
        再盖上顶面, 正面与侧面只承载面内细节, 因此接缝处是连续的圆角
        """

        c = f" {cls}" if cls else ""
        r = min(r, w / 2, d / 2)
        if filt:
            self.parts.append(f'<g filter="url(#{filt})">')
        ring = footprint(x, y, w, d, r)
        wall = hull([proj(px, py, z) for px, py in ring] + [proj(px, py, z + h) for px, py in ring])
        self.bounds.extend(wall)
        self.parts.append(f'<path class="face{c}" d="M' + "L".join(f"{a:.2f} {b:.2f}" for a, b in wall) + 'Z"/>')
        seams = [(x + w, y + d - r), (x + w - r, y + d)] if r > 0 else [(x + w, y + d)]
        for sx, sy in seams:
            self.path([(sx, sy, z), (sx, sy, z + h)], "detail" if r > 0 else "wire")
        if side:
            self.on("side", (x + w, y + d, z + h), d, h, side)
        if front:
            self.on("front", (x, y + d, z + h), w, h, front)
        self.on("top", (x, y, z + h), w, d, rect(0, 0, w, d, r, "face top" + c) + top)
        if filt:
            self.parts.append("</g>")

    def plate(self, w: float, d: float, h: float = 5, label: str = ""):
        top = rect(8, 8, w - 16, d - 16, 7, "detail")
        top += "".join(screw(a, b) for a in (15, w - 15) for b in (15, d - 15))
        if label:
            top += text(24, d - 12, label, 4.2, ls=1.2)
        self.box(0, 0, 0, w, d, h, 10, top=top)

    def cyl(self, cx: float, cy: float, z: float, r: float, h: float, cls: str = "", top: str = "", rings: tuple = ()):
        """竖直圆柱, 侧面用两段椭圆弧闭合, 顶面走顶面矩阵"""

        c = f" {cls}" if cls else ""
        (x0, y0), (x1, y1) = proj(cx, cy, z), proj(cx, cy, z + h)
        rx, ry = r * math.sqrt(2) * C, r * math.sqrt(2) * S
        self.track((cx - r, cy + r, z), (cx + r, cy - r, z + h), (cx + r, cy + r, z), (cx - r, cy - r, z + h))
        self.parts.append(
            f'<path class="face{c}" d="M{x1 - rx:.2f} {y1:.2f}L{x0 - rx:.2f} {y0:.2f}'
            f'A{rx:.2f} {ry:.2f} 0 0 0 {x0 + rx:.2f} {y0:.2f}L{x1 + rx:.2f} {y1:.2f}'
            f'A{rx:.2f} {ry:.2f} 0 0 0 {x1 - rx:.2f} {y1:.2f}Z"/>'
        )
        for k in rings:
            xk, yk = proj(cx, cy, z + k)
            self.parts.append(f'<path class="detail" d="M{xk - rx:.2f} {yk:.2f}A{rx:.2f} {ry:.2f} 0 0 0 {xk + rx:.2f} {yk:.2f}"/>')
        self.on("top", (cx, cy, z + h), 0, 0, circ(0, 0, r, "face top" + c) + top)

    def path(self, pts: list[P3], cls: str = "wire", closed: bool = False, filt: str = ""):
        self.track(*pts)
        d = "M" + "L".join(f"{a:.2f} {b:.2f}" for a, b in (proj(*p) for p in pts)) + ("Z" if closed else "")
        f = f' filter="url(#{filt})"' if filt else ""
        self.parts.append(f'<path class="{cls}" d="{d}"{f}/>')

    def dot(self, p: P3, r: float, cls: str = "spark", delay: float = 0):
        x, y = proj(*p)
        self.track(p)
        self.parts.append(
            f'<circle class="{cls}" cx="{x:.2f}" cy="{y:.2f}" r="{r:g}" style="animation-delay:{delay:.2f}s" filter="url(#soft)"/>'
        )

    def open(self, cls: str, style: str = ""):
        """开启一个动画分组, 需与 close 配对"""

        s = f' style="{style}"' if style else ""
        self.parts.append(f'<g class="{cls}"{s}>')

    def close(self):
        self.parts.append("</g>")

    def pulse(self, pts: list[P3], delay: float = 0, dur: float = 2.4):
        """沿三维折线流动的高亮脉冲"""

        d = "M" + "L".join(f"{a:.2f} {b:.2f}" for a, b in (proj(*p) for p in pts))
        self.parts.append(
            f'<path class="pulse" pathLength="1000" d="{d}" filter="url(#glow)" '
            f'style="animation-delay:{delay:g}s;animation-duration:{dur:g}s"/>'
        )

    def shift(self, v: P3) -> str:
        """三维位移对应的屏幕位移, 写成 css 变量供 run, drop, bob 使用"""

        x, y = proj(*v)
        return f"--dx:{x:.2f}px;--dy:{y:.2f}px"

    def svg(self) -> str:
        xs, ys = [p[0] for p in self.bounds], [p[1] for p in self.bounds]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        m = 0.08 * max(x1 - x0, y1 - y0)
        w, h = x1 - x0 + 2 * m, y1 - y0 + 2 * m
        ox, oy = m - x0, m - y0
        if w / h < 4 / 3:
            ox += (h * 4 / 3 - w) / 2
            w = h * 4 / 3
        else:
            oy += (w * 3 / 4 - h) / 2
            h = w * 3 / 4
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.1f} {h:.1f}"><style>{STANDALONE_CSS}{FIG_CSS}</style>{DEFS}'
            f'<g transform="translate({ox:.2f} {oy:.2f})">{"".join(self.parts)}</g></svg>'
        )


DEFS = (
    "<defs>"
    '<filter id="glow" filterUnits="userSpaceOnUse" x="-2000" y="-2000" width="6000" height="6000">'
    '<feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/>'
    '<feMergeNode in="SourceGraphic"/></feMerge></filter>'
    '<filter id="soft" filterUnits="userSpaceOnUse" x="-2000" y="-2000" width="6000" height="6000">'
    '<feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
    '<filter id="bloom" filterUnits="userSpaceOnUse" x="-2000" y="-2000" width="6000" height="6000">'
    '<feGaussianBlur stdDeviation="9"/></filter>'
    "</defs>"
)

FIG_CSS = (
    "text{font-family:var(--mono)}"
    ".face{fill:var(--body);stroke:var(--line);stroke-width:1;vector-effect:non-scaling-stroke;stroke-linejoin:round}"
    ".face.top{fill:var(--deck)}.face.recess{fill:var(--recess)}"
    ".detail{fill:none;stroke:var(--detail);stroke-width:1;vector-effect:non-scaling-stroke;stroke-linecap:round}"
    ".label{fill:var(--ink)}"
    ".wire{fill:none;stroke:var(--line);stroke-width:1;vector-effect:non-scaling-stroke;stroke-linecap:round;stroke-linejoin:round}"
    ".dash{stroke-dasharray:3 3}"
    ".led{fill:var(--detail)}.led.hot,.spark{fill:var(--accent)}"
    ".halo{fill:var(--accent);opacity:.22}"
    ".face.hot{fill:var(--accent);stroke:var(--accent-hi)}.face.top.hot{fill:var(--accent-hi)}"
    ".face.glass{fill:var(--glass-on);stroke:var(--accent)}"
    ".zone{fill:var(--accent-dim);stroke:var(--accent);stroke-width:1;vector-effect:non-scaling-stroke}"
    ".wire.hot,.detail.hot{stroke:var(--accent)}.label.hot{fill:var(--accent)}"
    # 动画
    ".pulse{fill:none;stroke:var(--accent-hi);stroke-width:2.2;vector-effect:non-scaling-stroke;stroke-linecap:round;"
    "stroke-dasharray:70 1200;stroke-dashoffset:70;opacity:0;animation:pulse 2.4s linear infinite}"
    "@keyframes pulse{0%{stroke-dashoffset:70;opacity:1}60%{stroke-dashoffset:-1000;opacity:1}61%,100%{opacity:0}}"
    ".spin{animation:spin 6s linear infinite}.spin.rev{animation-direction:reverse}"
    "@keyframes spin{to{transform:rotate(360deg)}}"
    ".blink{animation:blink 1.2s steps(1) infinite}@keyframes blink{50%{opacity:.12}}"
    ".breathe{animation:breathe 2.4s ease-in-out infinite}@keyframes breathe{50%{opacity:.3}}"
    ".halo.breathe{animation-name:halo}@keyframes halo{50%{opacity:.05}}"
    ".seq{animation:seq 2.4s steps(1) infinite;opacity:.15}@keyframes seq{0%,30%{opacity:1}}"
    ".flow{animation:flow .6s linear infinite}@keyframes flow{to{stroke-dashoffset:-6}}"
    ".run{animation:run 1.2s linear infinite}@keyframes run{to{transform:translate(var(--dx),var(--dy))}}"
    ".spark{animation:spark 1.6s ease-out infinite;opacity:0}@keyframes spark{0%{opacity:0}15%{opacity:1}60%,100%{opacity:0}}"
    ".drop{animation:drop 3.2s cubic-bezier(.5,0,.3,1) infinite}"
    "@keyframes drop{0%{transform:translate(var(--dx),var(--dy));opacity:0}12%{opacity:1}"
    "40%{transform:none}46%{transform:translateY(1.5px)}52%,82%{transform:none;opacity:1}100%{opacity:0}}"
    ".rise{animation:rise 3.6s ease-out infinite;opacity:0}"
    "@keyframes rise{0%{opacity:0;transform:translateY(10px)}18%,80%{opacity:1;transform:none}100%{opacity:0}}"
    ".bob{animation:bob 1.6s ease-in-out infinite}@keyframes bob{50%{transform:translate(var(--dx),var(--dy))}}"
    "@media (prefers-reduced-motion:reduce){*{animation:none!important}.rise,.spark,.seq{opacity:1}}"
    ".still *{animation:none!important}.still .rise,.still .spark,.still .seq{opacity:1}"
)

STANDALONE_CSS = (
    ":root{--mono:'DM Mono',ui-monospace,Menlo,Consolas,monospace;--line:#8e9397;--detail:#c3c6c8;--body:#ececeb;"
    "--deck:#f3f3f2;--recess:#e2e4e4;--ink:#6a6f73;--glass-on:#f3e6da;--accent:#f06a00;--accent-hi:#ff8c2e;"
    "--accent-dim:rgba(240,106,0,.08)}"
    "@media (prefers-color-scheme:dark){:root{--line:#3d4144;--detail:#2b2e30;--body:#17181a;--deck:#1b1d1f;"
    "--recess:#0e0f10;--ink:#868b8f;--glass-on:#1a1410;--accent:#ff7a1a;--accent-hi:#ffb070;--accent-dim:rgba(255,122,26,.10)}}"
)

FIGS: list[Fig] = []


def fig(key: str, name: str, note: str):
    def deco(fn: Callable[[Fig], None]):
        f = Fig(key, name, note)
        fn(f)
        FIGS.append(f)
        return fn

    return deco


def cells(w: float, d: float, n: int, hot: int = -1, labels: bool = True, run: int = 0) -> str:
    """磁带条顶面的帧格与序号, run 为走带方向 (1 向 +x, -1 向 -x, 0 静止)"""

    step = w / n
    if run:
        lines = "".join(ln(i * step, 0, i * step, d) for i in range(-1, n + 2))
        s = clip(w, d, g(lines, "run", f"--dx:{step * run:g}px;--dy:0px"))
    else:
        s = "".join(ln(i * step, 0, i * step, d) for i in range(1, n))
    if hot >= 0:
        s += rect(hot * step, 0, step, d, 0, "zone breathe")
    if labels:
        s += "".join(text(i * step + 2.5, 6, f"{i:03d}", 3.2, cls="label hot" if i == hot else "label") for i in range(n))
    return s


def frame_box(f: Fig, x: float, y: float, i: int, w: float = 28, d: float = 44, h: float = 20, cls: str = "", note: str = ""):
    """一帧: 正面印序号, 顶面一条记录摘要"""

    hot = "hot" in cls or "glass" in cls
    f.box(
        x, y, 5, w, d, h, 3, cls,
        top=rect(5, 7, w - 10, 3, 1.5, "detail") + rect(5, 14, w - 16, 3, 1.5, "detail"),
        front=text(w / 2, 9, f"{i:03d}", 5.5, "middle", cls="label hot" if hot else "label") + (text(w / 2, 16, note, 3.4, "middle") if note else ""),
        side="" if hot else ln(6, h - 5, d - 6, h - 5),
        filt="soft" if "hot" in cls else "",
    )


# ---------- 磁带本体 ----------


@fig("cassette", "Tape", "磁带: 唯一的事实来源, 一盘就是一个持久化的会话 · 带轮转动, REC 闪烁")
def cassette(f: Fig):
    f.plate(200, 150, label="TAPEHEAD · TYPE 0")
    top = rect(8, 8, 124, 60, 4, "detail")
    top += text(14, 19, "TAPE · 01", 6.5, ls=1.5) + text(126, 19, "APPEND ONLY", 3.8, "end", 1)
    top += rect(28, 28, 84, 30, 15) + spin(48, 43, reel(48, 43, 10)) + spin(92, 43, reel(92, 43, 10))
    top += circ(48, 43, 13.5, "detail")
    top += '<path class="detail" d="M30 90L36 75L104 75L110 90"/>'
    top += circ(46, 82.5, 2.2, "face recess") + circ(94, 82.5, 2.2, "face recess") + rect(63, 79, 14, 6, 1.5)
    top += "".join(circ(a, b, 1.6, "face recess") for a in (6, 134) for b in (6, 84))
    top += led(124, 38, True, anim="blink") + text(124, 47, "REC", 3.2, "middle")
    front = "".join(rect(u, 4, 9, 6, 1.5) for u in (44, 65.5, 87)) + text(8, 9.5, "A", 5)
    side = slits(12, 40, 3, 4, 10)
    f.box(30, 30, 5, 140, 90, 14, 6, top=top, front=front, side=side)


@fig("spool", "Spool", "带饼: 绕好的磁带, 尾端拉出带帧 · 带饼转动, 带往外走")
def spool(f: Fig):
    f.plate(230, 150)
    f.box(84, 93, 5, 136, 22, 1.5, top=cells(136, 22, 6, 5, False, run=1))
    f.cyl(80, 60, 5, 52, 3)
    wound = "".join(circ(0, 0, r, "detail") for r in range(18, 43, 4))
    hub = circ(0, 0, 13, "face recess") + circ(0, 0, 6, "face top") + circ(0, 0, 2.4, "face recess")
    hub += "".join(circ(9.5 * math.cos(math.radians(t)), 9.5 * math.sin(math.radians(t)), 1.6, "face top") for t in (0, 120, 240))
    f.cyl(80, 60, 8, 44, 12, top=wound + spin(0, 0, hub, 4))
    f.on("top", (200, 93, 6.5), 0, 0, halo(10, 11, 16, "breathe"))


@fig("archive", "Archive", "多盘磁带叠放, 最上面一盘正在录 · 顶盘指示灯呼吸")
def archive(f: Fig):
    f.plate(190, 150)
    for i in range(3):
        hot = i == 2
        top = rect(6, 6, 108, 48, 4, "detail") + text(12, 16, f"TAPE · 0{i + 1}", 5.5, ls=1.2)
        reels = circ(41, 35, 7) + circ(79, 35, 7)
        if hot:
            reels = spin(41, 35, reel(41, 35, 7), 5) + spin(79, 35, reel(79, 35, 7), 5)
        top += rect(24, 24, 72, 22, 11) + reels + led(104, 16, hot, anim="breathe" if hot else "")
        f.box(36 - i * 6, 30 + i * 6, 5 + i * 13, 120, 76, 11, 5, top=top, front=text(8, 8, f"#{i}", 4.5))


# ---------- 磁头与帧 ----------


@fig("head", "R/W head", "磁头骑在带上, 缝隙对准当前帧 · 带从磁头下走过")
def head(f: Fig):
    f.plate(220, 130, label="TRANSPORT")
    f.box(10, 50, 5, 200, 30, 1.5, top=cells(200, 30, 10, 5, False, run=1))
    f.on("top", (110, 65, 6.5), 0, 0, halo(0, 0, 18, "breathe"))
    f.box(96, 32, 5, 28, 12, 40, 2, side=slits(3, 9, 3, 6, 34, True))
    f.box(105, 56, 9, 10, 18, 36, 1.5, front=ln(5, 0, 5, 36, "detail hot breathe"))
    f.box(96, 86, 5, 28, 12, 40, 2, front=text(14, 34, "L", 4, "middle"))
    top = slits(8, 28, 3, 12, 58)
    front = text(18, 7, "R/W", 5, "middle", 1.4)
    side = text(35, 7, "HEAD · 01", 4.2, "middle", 1) + led(8, 5, True, 1.4, "blink")
    f.box(92, 30, 45, 36, 70, 10, 3, top=top, front=front, side=side)


@fig("frames", "Frames", "帧: 序号即位置, 从 0 连续无空洞 · 新帧落进末尾那一格")
def frames(f: Fig):
    f.plate(272, 90, label="SEQ 000 → 006")
    for i in range(6):
        frame_box(f, 12 + i * 36, 22, i)
    f.on("top", (228, 22, 5), 28, 44, rect(0, 0, 28, 44, 3, "zone dash") + halo(14, 22, 16, "breathe") + text(14, 25, "NEXT", 4.5, "middle", 1.2, "label hot"))
    f.open("drop", f.shift((0, 0, 46)))
    frame_box(f, 228, 22, 6, cls="glass")
    f.close()


@fig("append", "Append only", "只追加: 只能叠在最上面, 已录的不改不删不重排 · 新帧落到顶上")
def append(f: Fig):
    f.plate(130, 130)
    f.path([(16, 16, 5), (16, 16, 104)], "wire")
    for i in range(4):
        f.box(20, 20, 5 + i * 13, 90, 90, 11, 4, front=text(8, 7.5, f"#{i}", 4.5) + led(82, 5.5), side=slits(10, 30, 3, 3, 8))
    for x, y in ((110, 110), (20, 110), (110, 20)):
        f.path([(x, y, 68), (x, y, 96)], "wire hot dash flow")
    f.open("drop", f.shift((0, 0, 34)))
    f.box(20, 20, 57, 90, 90, 11, 4, "glass", top=halo(45, 45, 30), front=text(8, 7.5, "#4", 4.5, cls="label hot") + led(82, 5.5, True))
    f.close()
    for x, y in ((114, 114), (16, 114), (114, 16)):
        f.path([(x, y, 5), (x, y, 104)], "wire")


@fig("writer", "Single writer", "单写者: 同一时刻只有一个写头 · 写头在末尾落下新帧")
def writer(f: Fig):
    f.plate(290, 120, label="LOCK · 1 WRITER")
    f.box(10, 16, 5, 270, 6, 6, 1.5)
    for i in range(6):
        frame_box(f, 20 + i * 36, 34, i, d=52, h=16)
    f.on("top", (236, 34, 5), 28, 52, rect(0, 0, 28, 52, 3, "zone") + halo(14, 26, 18, "breathe"))
    f.open("drop", f.shift((0, 0, 14)))
    frame_box(f, 236, 34, 6, d=52, h=16, cls="glass")
    f.close()
    f.box(236, 15, 11, 28, 10, 34, 2)
    f.open("bob", f.shift((0, 0, -3)))
    f.box(244, 52, 26, 12, 16, 19, 1.5, front=led(6, 10, True, 1.5, "blink"))
    f.close()
    f.box(10, 98, 5, 270, 6, 6, 1.5)
    f.box(236, 95, 11, 28, 10, 34, 2)
    f.box(232, 13, 45, 36, 94, 10, 3, top=slits(8, 28, 3, 14, 80), front=text(18, 7, "W", 5, "middle"), side=text(47, 7, "WRITER · 01", 4.2, "middle", 1))


@fig("repair", "Repair by append", "未闭合的帧不去改它, 追加一帧把它闭合 · 闭合信号回指")
def repair(f: Fig):
    f.plate(200, 100)
    frame_box(f, 12, 26, 0)
    f.box(48, 26, 5, 28, 44, 10, 3, top=rect(4, 4, 20, 36, 2), front=text(14, 8, "001", 5, "middle"))
    for x, y in ((48, 70), (76, 70), (76, 26)):
        f.path([(x, y, 15), (x, y, 25)], "wire dash")
    f.path([(48, 70, 25), (76, 70, 25), (76, 26, 25)], "wire dash")
    frame_box(f, 84, 26, 2)
    arc = [(156 - 94 * (1 - math.cos(math.radians(t))) / 2, 48, 27 + 34 * math.sin(math.radians(t))) for t in range(0, 181, 6)]
    f.path(arc, "wire hot dash flow", filt="soft")
    f.pulse(arc, dur=2.2)
    f.path([(59, 48, 20), (62, 48, 16), (65, 48, 20)], "wire hot", filt="soft")
    frame_box(f, 120, 26, 3, cls="glass", note="close 001")


@fig("deltas", "Deltas stay off tape", "流式增量只在实时流中闪过 · 光点流过却不落地, 落下的只有完整帧")
def deltas(f: Fig):
    f.plate(250, 100, label="STREAM ≠ TAPE")
    for i in range(4):
        frame_box(f, 12 + i * 36, 26, i)
    f.on("top", (156, 26, 5), 28, 44, rect(0, 0, 28, 44, 3, "zone dash"))
    for k in range(14):
        t = k / 13
        f.dot((240 - 70 * t, 48 - 8 * t, 92 - 46 * t + 14 * math.sin(t * math.pi)), 1.4 + 0.6 * t, delay=t * 0.9)
    f.open("drop", f.shift((0, 0, 30)) + ";animation-delay:.6s")
    frame_box(f, 156, 26, 4, cls="glass")
    f.close()


@fig("replay", "Replay", "模型看到的消息不单独存储, 从磁带回放得出 · 带走进读头, 消息逐条升起")
def replay(f: Fig):
    f.plate(280, 120)
    f.box(12, 45, 5, 120, 30, 1.5, top=cells(120, 30, 6, labels=False, run=1))
    front = text(22, 12, "REPLAY", 5, "middle", 1.4) + led(22, 22, True, anim="blink")
    f.box(118, 28, 5, 44, 64, 34, 5, top=rect(8, 22, 28, 20, 3) + slits(12, 32, 3, 26, 38), front=front, side=slits(10, 54, 3, 8, 14))
    roles = ("user", "assistant", "tool")
    for i, z in enumerate((10, 30, 50)):
        hot = i == 2
        top = text(8, 9, roles[2 - i], 4, cls="label hot" if hot else "label")
        top += ln(8, 18, 46, 18) + ln(8, 25, 60, 25) + ln(8, 32, 38, 32)
        f.open("rise", f"animation-delay:{i * 0.5:g}s")
        f.path([(162, 60, 20 + i * 5), (188, 62, z + 1)], "wire hot dash flow" if hot else "wire dash flow")
        f.box(188, 30, z, 70, 56, 1.5, 3, "glass" if hot else "", top=top, filt="soft" if hot else "")
        f.close()


# ---------- 介质与磁带库 ----------


@fig("media", "Media", "mem / fs / db 平等并列, 实现同一套 Tape 与 Silo 协议 · 同一条总线来回")
def media(f: Fig):
    f.plate(290, 115, label="ONE PROTOCOL · TAPE / SILO")
    bus = [(46, 78, 5.2), (46, 92, 5.2), (254, 92, 5.2), (254, 81, 5.2)]
    f.path(bus, "wire hot", filt="soft")
    f.path([(132, 78, 5.2), (132, 92, 5.2)], "wire hot", filt="soft")
    f.pulse(bus, 0, 3)
    f.pulse(bus[::-1], 1.5, 3)
    f.box(18, 28, 5, 56, 50, 6, 2, top=rect(14, 12, 28, 26, 2) + text(28, 27, "MEM", 4.5, "middle", 1) + led(36, 18, False, 1.4, "seq"))
    for i in range(6):
        f.box(23 + i * 8.5, 78, 5, 3, 5, 2)
        f.box(74, 33 + i * 7.5, 5, 5, 3, 2)
    top = text(32, 22, "FS", 6, "middle", 2) + slits(8, 56, 4, 32, 42)
    f.box(100, 28, 5, 64, 50, 26, 4, top=top, front=rect(6, 9, 38, 7, 3) + led(54, 12.5, True, anim="seq", delay=0.8), side=slits(8, 42, 3, 6, 20))
    f.cyl(254, 53, 5, 28, 36, rings=(12, 24), top=text(0, 2.5, "DB", 6, "middle", 2) + circ(0, 0, 16, "detail") + led(0, -10, True, 1.6, "seq", 1.6))


@fig("silo", "Silo", "磁带库: 负责磁带的存放与出入库 · 指示灯巡检, 被取出的那盘常亮")
def silo(f: Fig):
    f.plate(130, 125)
    front = ""
    for i in range(8):
        v = 8 + i * 18
        front += rect(6, v, 68, 14, 2) + text(10, v + 9, f"T-{i:02d}", 3.6) + ln(28, v + 7, 56, v + 7)
        front += led(66, v + 7, True, 1.6, "breathe") if i == 3 else led(66, v + 7, False, 1.6, "seq", i * 0.3)
    side = slits(12, 58, 4, 20, 60) + slits(12, 58, 4, 100, 140)
    f.box(20, 20, 5, 80, 70, 160, 4, top=text(40, 37, "SILO", 7, "middle", 3) + slits(14, 66, 4, 48, 58), front=front, side=side)
    f.on("front", (20, 90, 165), 80, 160, halo(40, 69, 22, "breathe"))
    f.open("bob", f.shift((0, 4, 0)) + ";animation-duration:2.4s")
    f.box(28, 90, 91, 56, 26, 10, 2, top=rect(14, 8, 28, 10, 5) + text(4, 24, "T-03", 3.4), front=text(4, 7, "TAPE", 3.4))
    f.close()


@fig("deck", "Deck", "开盘机: 两个带盘之间走带, 中间过磁头 · 转盘, 走带, 录音")
def deck(f: Fig):
    f.plate(230, 160)
    top = rect(8, 8, 190, 90, 6, "detail") + text(10, 128, "REEL · TO · REEL", 4.5, ls=1.4)
    front = text(10, 11, "TH-2", 5, ls=1.2) + slits(120, 196, 3, 4, 14)
    f.box(12, 12, 5, 206, 136, 18, 8, top=top, front=front, side=slits(20, 116, 3, 4, 14))
    f.cyl(70, 56, 23, 34, 3, top=spin(0, 0, reel(0, 0, 34, 30), 7))
    f.cyl(160, 56, 23, 34, 3, top=spin(0, 0, reel(0, 0, 34, 18), 5))
    tape = [(70, 90, 26), (104, 106, 26), (132, 106, 26), (160, 90, 26)]
    f.path(tape, "wire hot", filt="soft")
    f.pulse(tape, 0, 1.6)
    f.box(108, 102, 23, 20, 10, 8, 1.5, front=ln(10, 0, 10, 8, "detail hot breathe"))
    for i, name in enumerate(("REW", "PLAY", "FF", "REC")):
        rec = name == "REC"
        f.open("breathe" if rec else "")
        f.box(22 + i * 20, 112, 23, 16, 16, 3, 2, "hot" if rec else "", top=text(8, 9.5, name, 3.2, "middle"), filt="soft" if rec else "")
        f.close()


# ---------- Provider 与 Tool ----------


@fig("provider", "Provider", "内核只认 Provider 协议, 由 host 插进来 · 响应沿线流回内核")
def provider(f: Fig):
    f.plate(250, 130)
    top = text(10, 15, "TAPEHEAD", 7, ls=2.4) + text(10, 23, "kernel", 4.5) + slits(60, 90, 3, 46, 70)
    side = rect(30, 14, 22, 14, 2) + led(37, 21, True, 1.4, "seq", 1.2) + led(45, 21, False, 1.4, "seq", 1.5)
    f.box(18, 22, 5, 100, 80, 42, 6, top=top, front=text(8, 12, "HOST PLUGS IN", 4.2, ls=1) + rect(8, 26, 30, 6, 3), side=side)
    f.box(118, 55, 20, 7, 12, 10, 1.5)
    pts = [(125, 61, 25)] + [(125 + 6 * t, 61, 25 - 19.8 * (1 - math.cos(t * math.pi / 8)) / 2) for t in range(1, 9)] + [(184, 61, 5.2)]
    f.path(pts, "wire hot", filt="soft")
    f.pulse(pts[::-1], 0, 2.4)
    top = text(26, 20, "PROVIDER", 5, "middle", 1.4) + text(26, 28, "openai-compat", 3.4, "middle")
    f.box(184, 38, 5, 52, 48, 30, 5, top=top, front=led(44, 8, True, anim="blink") + slits(6, 30, 3, 6, 24), side=slits(8, 40, 3, 6, 24))


@fig("tools", "Tools", "工具由 host 提供, 内核只负责派发 · 轮流派发到三个工具")
def tools(f: Fig):
    f.plate(230, 170)
    front = "".join(led(25 + i * 20, 10, True, 1.6, "seq", i * 0.8) for i in range(3)) + text(80, 11, "DISPATCH", 4.2, "end", 1)
    f.box(70, 16, 5, 90, 56, 34, 6, top=text(45, 26, "KERNEL", 6, "middle", 2.4) + slits(14, 76, 4, 36, 46), front=front)
    names = ("read", "write", "shell")
    for i in range(3):
        wire = [(95 + i * 20, 72, 5.2), (95 + i * 20, 92, 5.2), (47 + i * 68, 92, 5.2), (47 + i * 68, 112, 5.2)]
        f.path(wire, "wire")
        f.pulse(wire, i * 0.8, 2.4)
    for i in range(3):
        top = text(27, 16, f"tool.{names[i]}", 4.2, "middle") + rect(10, 22, 34, 8, 4)
        f.box(20 + i * 68, 112, 5, 54, 38, 18, 4, top=top, front=led(46, 9, True, 1.6, "seq", i * 0.8 + 0.6) + text(6, 11, "fn()", 4))


# ---------- 标志方向 ----------


@fig("mark-cube", "Mark · Cube", "Logo 方向: 圆角立方体顶面开磁带窗 · 带轮转动")
def mark_cube(f: Fig):
    top = rect(12, 26, 56, 28, 14) + spin(27, 40, reel(27, 40, 8), 5) + spin(53, 40, reel(53, 40, 8), 5) + led(66, 12, True, anim="blink")
    front = text(40, 46, "tapehead", 7, "middle", 1.2) + slits(16, 64, 3, 58, 68)
    f.box(0, 0, 0, 80, 80, 80, 10, top=top, front=front, side=slits(16, 64, 3, 58, 68))


@fig("mark-wedge", "Mark · Wedge", "Logo 方向: 楔形磁头压在一帧上 · 带从楔下走过")
def mark_wedge(f: Fig):
    f.box(0, 18, 0, 140, 40, 3, 2, top=cells(140, 40, 7, 3, False, run=1))
    f.on("top", (70, 38, 3), 0, 0, halo(0, 0, 20, "breathe"))
    f.path([(52, 24, 64), (88, 24, 64), (88, 52, 64), (52, 52, 64)], "face top", True)
    f.path([(88, 24, 64), (88, 52, 64), (70, 52, 10), (70, 24, 10)], "face", True)
    f.path([(52, 52, 64), (88, 52, 64), (70, 52, 10)], "face", True)
    f.path([(70, 52, 64), (70, 52, 10)], "detail hot", filt="soft")
    f.pulse([(70, 52, 64), (70, 52, 10)], 0, 1.6)
    f.on("front", (52, 52, 64), 36, 54, text(18, 10, "R/W", 4.5, "middle", 1.2))


@fig("mark-stack", "Mark · Stack", "Logo 方向: 三片帧叠成的方块 · 顶片循环落下")
def mark_stack(f: Fig):
    for i in range(3):
        hot = i == 2
        if hot:
            f.open("drop", f.shift((0, 0, 28)))
        top = halo(35, 35, 24) + rect(8, 8, 54, 54, 4, "detail hot") if hot else ""
        f.box(0, 0, i * 22, 70, 70, 18, 6, "glass" if hot else "", top=top, front=text(8, 11, f"{i:03d}", 5, cls="label hot" if hot else "label"))
        if hot:
            f.close()


def build():
    """每幅插画输出一个 svg"""

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    for f in FIGS:
        (OUT / f"{f.key}.svg").write_text(f.svg(), encoding="utf-8")


if __name__ == "__main__":
    build()
