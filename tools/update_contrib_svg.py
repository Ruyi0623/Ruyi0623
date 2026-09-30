#!/usr/bin/env python3
"""生成主页自述用的等轴测 3D 贡献图 SVG(仅标准库,无第三方依赖)。

数据源是 GitHub 贡献日历的公开聚合接口:GitHub 官方的 contributionsCollection
只在已登录的 GraphQL 里开放,profile README 这种无令牌场景只能取聚合数据。

用法:
    python tools/update_contrib_svg.py

产物:assets/contrib-3d.svg(相对本脚本所在目录的上一级)。
README 里用相对路径 <img src="assets/contrib-3d.svg" /> 引用,GitHub 会经 camo 代理。

约定:
- 画法是纯 <rect>/<polygon>/<text>,不用 foreignObject(GitHub 会把 img 内的它剔掉)。
- 每格 3 个可见面(顶/右/左),按 (周 + 星期) 对角线从后往前画, painter 算法即正确。
- 方块高度对贡献次数取 0.45 次幂:稀疏数据下既看得出"少数几天集中爆发",
  又不会被 53 次那一天撑成塔。
"""

import datetime as dt
import json
import math
import pathlib
import urllib.request

USER = "Ruyi0623"
API = "https://github-contributions-api.jogruber.de/v4/%s?y=last" % USER
OUT = pathlib.Path(__file__).resolve().parent.parent / "assets" / "contrib-3d.svg"

TW, TH = 26.0, 8.5  # 等轴测格子的宽 / 高(约 3:1,压得比较扁,profile 页里不占高度)
H0, HMAX = 6.0, 16.0  # 无贡献格的厚度 / 最高格厚度
EXP = 0.45  # 高度曲线的幂

# 每级三面配色(深色卡片上:顶面最亮、右面中、左面最暗)
FACES = {
    0: ("#2b323b", "#21262d", "#1a1f26"),
    1: ("#1c7a45", "#0e5a33", "#0a4425"),
    2: ("#26a851", "#177a3b", "#0d5a2b"),
    3: ("#45d166", "#29a846", "#1b7c33"),
    4: ("#61ea7d", "#39d353", "#26a83f"),
}
TXT = "#8b949e"
TXT_DIM = "#6e7681"
FONT = "ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

ML, MT, MR, MB = 54, 34, 24, 48  # 卡片内边距(左留星期标签 / 上留月份标签 / 下留图例)


def fetch():
    req = urllib.request.Request(API, headers={"User-Agent": "profile-contrib-svg"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def x0(w, r):
    return (w - r) * (TW / 2)


def y0(w, r):
    return (w + r) * (TH / 2)


def f(v):
    return "%.1f" % v


def cube(cx, cy, h, faces):
    """把中心在 (cx, cy)、厚 h 的等轴测立方体写成 3 个 polygon。

    基面菱形四角:T(上) R(右) B(下) L(左);向上挤出 h 得到顶面同一菱形,
    可见侧面是 B→L 与 B→R 这两个四边形。
    """
    hw, hh = TW / 2, TH / 2
    tt = (cx, cy - hh - h)
    rt = (cx + hw, cy - h)
    bt = (cx, cy + hh - h)
    lt = (cx - hw, cy - h)
    rb = (cx + hw, cy)
    bb = (cx, cy + hh)
    lb = (cx - hw, cy)
    top, right, left = faces
    return (
        '<polygon points="%s,%s %s,%s %s,%s %s,%s" fill="%s"/>'
        % (f(lt[0]), f(lt[1]), f(bt[0]), f(bt[1]), f(bb[0]), f(bb[1]), f(lb[0]), f(lb[1]), left)
        + '<polygon points="%s,%s %s,%s %s,%s %s,%s" fill="%s"/>'
        % (f(bt[0]), f(bt[1]), f(rt[0]), f(rt[1]), f(rb[0]), f(rb[1]), f(bb[0]), f(bb[1]), right)
        + '<polygon points="%s,%s %s,%s %s,%s %s,%s" fill="%s"/>'
        % (f(tt[0]), f(tt[1]), f(rt[0]), f(rt[1]), f(bt[0]), f(bt[1]), f(lt[0]), f(lt[1]), top)
    )


def main():
    data = fetch()
    days = data["contributions"]
    if not days:
        raise SystemExit("接口没返回任何贡献数据,放弃生成(不要写一张空图冒充)")

    first = dt.date.fromisoformat(days[0]["date"])
    last = dt.date.fromisoformat(days[-1]["date"])
    # 网格以周日开头(GitHub 贡献表的列就是周日开头的周)
    sunday0 = first - dt.timedelta(days=(first.weekday() + 1) % 7)
    peak = max(d["count"] for d in days)
    total = sum(d["count"] for d in days)
    active = sum(1 for d in days if d["count"] > 0)

    cells = []
    for d in days:
        day = dt.date.fromisoformat(d["date"])
        off = (day - sunday0).days
        w, r = off // 7, off % 7
        count = d["count"]
        h = H0 + (HMAX - H0) * (count / peak) ** EXP if count else H0
        cells.append((w, r, h, FACES[min(d.get("level", 0), 4)], count))

    # 几何范围(用于定位标签与计算画布)
    minx = min(x0(w, r) - TW / 2 for w, r, _, _, _ in cells)
    maxx = max(x0(w, r) + TW / 2 for w, r, _, _, _ in cells)
    miny = min(y0(w, r) - h for w, r, h, _, _ in cells)
    maxy = max(y0(w, r) + TH / 2 for w, r, _, _, _ in cells)
    gx, gy = ML - minx, MT - miny
    width = int(math.ceil(ML + (maxx - minx) + MR))
    height = int(math.ceil(MT + (maxy - miny) + MB))

    body = []
    # 立方体:对角线 (周+星期) 越大越靠前,后画的盖住先画的
    for w, r, h, faces, _ in sorted(cells, key=lambda c: (c[0] + c[1],)):
        body.append(cube(gx + x0(w, r), gy + y0(w, r), h, faces))

    labels = []
    seen = set()
    for d in days:
        day = dt.date.fromisoformat(d["date"])
        key = (day.year, day.month)
        if key in seen or day.day != 1:
            continue
        seen.add(key)
        off = (day - sunday0).days
        w = off // 7
        labels.append(
            '<text x="%s" y="%s" font-size="11" fill="%s" font-family="%s">%s</text>'
            % (f(gx + x0(w, 0) - TW / 2), f(gy + y0(0, 0) - HMAX - 10), TXT, FONT,
               dt.date(day.year, day.month, 1).strftime("%b"))
        )
    for r, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        labels.append(
            '<text x="%s" y="%s" font-size="10" fill="%s" font-family="%s" text-anchor="end">%s</text>'
            % (f(gx + x0(0, r) - TW / 2 - 8), f(gy + y0(0, r) + TH / 2 + 3), TXT_DIM, FONT, name)
        )

    # 图例:Less ▢▢▢▢▢ More
    lw, lh = 11.0, 5.5
    ly = height - MB + 22
    lx = width - MR - 150
    legend = ['<text x="%s" y="%s" font-size="10" fill="%s" font-family="%s">Less</text>'
              % (f(lx), f(ly + 3), TXT_DIM, FONT)]
    for i, lvl in enumerate(range(5)):
        legend.append(cube(lx + 30 + i * (lw + 4), ly, lh, FACES[lvl]))
    legend.append('<text x="%s" y="%s" font-size="10" fill="%s" font-family="%s">More</text>'
                  % (f(lx + 30 + 5 * (lw + 4) + 6), f(ly + 3), TXT_DIM, FONT))

    caption = (
        '<text x="%d" y="%d" font-size="11" fill="%s" font-family="%s">'
        "%s — %s · %d contributions · %d active days</text>"
        '<text x="%d" y="%d" font-size="10" fill="%s" font-family="%s">updated %s</text>'
        % (20, height - MB + 22, TXT, FONT, first.isoformat(), last.isoformat(), total, active,
           20, height - MB + 36, TXT_DIM, FONT, dt.date.today().isoformat())
    )

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" role="img" aria-labelledby="t d">'
        "<title id=\"t\">%s's GitHub contributions, last 12 months</title>"
        "<desc id=\"d\">Isometric 3D bar view of daily contribution counts from %s to %s: "
        "%d contributions across %d active days, peak %d in one day.</desc>"
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#0d1117"/><stop offset="1" stop-color="#121a23"/>'
        "</linearGradient></defs>"
        '<rect x="0.5" y="0.5" width="%d" height="%d" rx="14" fill="url(#bg)" '
        'stroke="#30363d" stroke-width="1"/>'
        "%s%s%s%s"
        "</svg>"
    ) % (width, height, width, height, USER, first.isoformat(), last.isoformat(), total,
         active, peak, width - 1, height - 1, "".join(labels), "".join(body),
         "".join(legend), caption)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8", newline="\n")
    print("wrote %s (%d x %d, %d days, peak %d)" % (OUT, width, height, len(days), peak))


if __name__ == "__main__":
    main()
