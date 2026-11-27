# -*- coding: utf-8 -*-
"""
A股双周更新（云端全自动版，无需 AI）
产出：
  1) out/股债对照.png  —— 沪深300全收益 vs 万得二级债基（原图同源数据）
  2) out/三大指数对比.png / .md —— 上证 / 创业板 / 科创50 完整全景表
  3) 若配置环境变量 SCT_SENDKEY，则通过 Server酱 将两张图片推送到微信
频率控制：由调用方每周一触发，本脚本仅在“双周周”真正执行（以 2026-11-30 为第 0 周）。
"""
import os, sys, json, datetime as dt
import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# ---------- 中文字体 ----------
for f in ["Noto Sans CJK SC", "Noto Sans CJK JP", "Microsoft YaHei", "SimHei"]:
    try:
        font_manager.findfont(f, fallback_to_default=False)
        plt.rcParams["font.sans-serif"] = [f]
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

def get_json(url, params=None, headers=None, timeout=45, tries=4):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
    raise last

# ---------- 双周门控 ----------
def beijing_today():
    """云端服务器使用 UTC，统一按北京时间标注日期。"""
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()


def is_due_week(today=None):
    today = today or beijing_today()
    anchor = dt.date(2026, 11, 30)  # 首次执行周（周一）
    days = (today - anchor).days
    if days < 0:
        return False
    return (days // 7) % 2 == 0

# ---------- 数据：股债对照 ----------
def fetch_bond_equity():
    j = get_json("https://www.jzzglod.site/api/market/bond-equity",
                 headers={**UA, "Referer": "https://www.jzzglod.site/"})
    return j

def draw_bond_equity(j):
    dates = pd.to_datetime(j["dates"])
    stock, wind = j["hs300"], j["wind"]
    fig, ax = plt.subplots(figsize=(13, 6.8))
    ax.plot(dates, stock, color="#1a1a1a", lw=1.5, zorder=3)
    ax.plot(dates, wind, color="#8e8e93", lw=1.5, zorder=2)
    ax.annotate(f"{stock[-1]:,.0f}", xy=(dates[-1], stock[-1]), xytext=(10, 4),
                textcoords="offset points", fontsize=13, fontweight="bold", color="#1a1a1a")
    ax.annotate(f"{wind[-1]:,.0f}", xy=(dates[-1], wind[-1]), xytext=(10, 4),
                textcoords="offset points", fontsize=13, fontweight="bold", color="#8e8e93")
    ax.legend(handles=[
        plt.Line2D([], [], color="#1a1a1a", lw=1.8,
                   label=f"沪深300全收益（H00300.CSI）— 年化 {j['hs300_cagr']}%"),
        plt.Line2D([], [], color="#8e8e93", lw=1.8,
                   label=f"万得二级债基（885007.WI）— 年化 {j['wind_cagr']}%"),
    ], loc="upper left", fontsize=11.5, frameon=False)
    ax.set_title("股债长期收益对照（2004-12-31 = 1000）", fontsize=15, fontweight="bold", loc="left", pad=14)
    ax.set_ylabel("指数（基期 = 1000）")
    ax.set_xlim(pd.Timestamp("2004-01-01"), dates[-1] + pd.Timedelta(days=560))
    ax.grid(color="#ececec", zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.text(0, -0.10, f"数据：中证指数官网 + 万得；截至 {j['as_of']}，周频。自动生成，不构成投资建议。",
            transform=ax.transAxes, fontsize=9, color="#999")
    path = os.path.join(OUT, "股债对照.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path

# ---------- 数据：三大指数 ----------
def tx_weekly(sym):
    j = get_json("https://web.ifzq.gtimg.cn/appstock/app/kline/kline",
                 params={"param": f"{sym},week,2024-01-01,{beijing_today():%Y-%m-%d},400"})
    rows = j["data"][sym]["week"]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df[0])
    df["close"] = df[2].astype(float)
    return df.set_index("date")["close"]

def danjuan_valuation():
    """蛋卷估值（含 PE 与分位），失败则返回空 dict"""
    try:
        j = get_json("https://danjuanfunds.com/djapi/index_eva/dj", headers=UA, tries=2)
        items = j["data"]["items"]
        out = {}
        for it in items:
            out[it["index_code"]] = it
        return out
    except Exception:
        return {}


def historical_pe_at(dj_code, peak_date):
    """取距离高点日最近的一条同源 PE 记录；无记录时返回空值。"""
    try:
        j = get_json(f"https://danjuanfunds.com/djapi/index_eva/pe_history/{dj_code}",
                     params={"day": "all"}, headers=UA, tries=2)
        items = j.get("data", {}).get("index_eva_pe_growths", [])
        if not items:
            return None, None
        target = pd.Timestamp(peak_date)
        best = min(items, key=lambda it: abs(pd.to_datetime(it["ts"], unit="ms") - target))
        return float(best["pe"]), str(pd.to_datetime(best["ts"], unit="ms").date())
    except Exception:
        return None, None


INDEXES = [
    ("上证指数", "sh000001", "SH000001"),
    ("创业板指", "sz399006", "SZ399006"),
    ("科创50", "sh000688", "SH000688"),
]


def build_index_table():
    val = danjuan_valuation()
    rows = []
    for name, sym, dj_code in INDEXES:
        s = tx_weekly(sym)
        last_date, last = s.index[-1], float(s.iloc[-1])
        ytd = s[s.index >= f"{last_date.year}-01-01"]
        peak_date, peak = ytd.idxmax(), float(ytd.max())
        after = s[s.index >= peak_date]
        trough = float(after.min())
        dd = (last / peak - 1) * 100
        maxdd = (trough / peak - 1) * 100
        days = (last_date - peak_date).days
        chg2w = (last / float(s.iloc[-3]) - 1) * 100 if len(s) >= 3 else None
        v = val.get(dj_code, {})
        pe = v.get("pe")
        pct = v.get("pe_percentile")
        pe_txt = f"{pe:.1f} 倍" if pe else "—"
        pct_txt = f"{pct*100:.1f}%" if isinstance(pct, (int, float)) and pct <= 1 else (f"{pct:.1f}%" if pct else "—")
        peak_pe, peak_pe_date = historical_pe_at(dj_code, str(peak_date.date()))
        rows.append(dict(name=name, last=last, last_date=str(last_date.date()),
                         peak=peak, peak_date=str(peak_date.date()),
                         dd=dd, maxdd=maxdd, days=days, chg2w=chg2w,
                         pe=pe_txt, pct=pct_txt, peak_pe=peak_pe,
                         peak_pe_date=peak_pe_date))
    return rows


def render_index_image(rows):
    """把完整指标表渲染成适合微信查看的竖向图片。"""
    index_date = max(r["last_date"] for r in rows)
    labels = ["本轮高点", "最新点位", "距本轮高点", "区间最大回撤", "调整时长",
              "近两周涨跌", "当前 PE-TTM", "估值历史分位", "高点时 PE"]
    data = []
    for r in rows:
        peak_pe = f"{r['peak_pe']:.1f} 倍" if r["peak_pe"] is not None else "—"
        if r["peak_pe_date"]:
            peak_pe += f"\n{r['peak_pe_date'][5:]}"
        data.append([
            f"{r['peak']:,.2f}\n{r['peak_date'][5:]}",
            f"{r['last']:,.2f}\n{r['last_date'][5:]}",
            f"{r['dd']:.1f}%", f"{r['maxdd']:.1f}%", f"{r['days']} 天",
            f"{r['chg2w']:+.1f}%", r["pe"], r["pct"], peak_pe,
        ])
    fig, ax = plt.subplots(figsize=(12, 10.5), facecolor="white")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.04, 0.955, "三大指数全景对比", fontsize=25, fontweight="bold", color="#17233c")
    ax.text(0.04, 0.918, f"行情截至 {index_date}｜估值为蛋卷口径", fontsize=12, color="#718096")
    lefts = [0.04, 0.27, 0.51, 0.75]
    for x, text in zip(lefts, ["维度"] + [r["name"] for r in rows]):
        ax.text(x, 0.855, text, fontsize=15, fontweight="bold", color="#17233c")
    top, bottom = 0.81, 0.13
    step = (top - bottom) / len(labels)
    for i, label in enumerate(labels):
        y = top - i * step
        if i % 2 == 0:
            ax.add_patch(plt.Rectangle((0.025, y - step + 0.008), 0.95, step,
                                       color="#f6f8fb", zorder=0))
        ax.text(lefts[0], y - step * 0.55, label, fontsize=13.5,
                fontweight="bold" if i in (2, 3) else "normal", color="#344054", va="center")
        for j in range(3):
            ax.text(lefts[j + 1], y - step * 0.55, data[j][i], fontsize=13.5,
                    color="#101828", va="center", linespacing=1.5)
        ax.plot([0.03, 0.97], [y - step + 0.008, y - step + 0.008], color="#e5eaf0", lw=0.7)
    ax.text(0.04, 0.065, "注：高点时 PE 取距离高点日最近的同源记录；— 表示暂无同源数据。", fontsize=10.5, color="#718096")
    ax.text(0.04, 0.035, "数据：腾讯行情、蛋卷基金。自动生成，不构成投资建议。", fontsize=10.5, color="#98a2b3")
    path = os.path.join(OUT, "三大指数对比.png")
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path

def render_report(rows, be):
    today = beijing_today().isoformat()
    lines = [
        f"# A股双周更新（{today}）", "",
        f"## 一、股债对照图（数据截至 {be['as_of']}）", "",
        f"- 沪深300全收益：**{be['hs300_last']:,.0f}**，年化 **{be['hs300_cagr']}%**",
        f"- 万得二级债基：**{be['wind_last']:,.0f}**，年化 **{be['wind_cagr']}%**",
        f"- 股/债累计回报比：**{be['hs300_last']/be['wind_last']:.2f} 倍**", "",
        "## 二、三大指数全景对比", "",
        "| 指数 | 最新点位 | 日期 | 年内高点(日期) | 距高点 | 区间最大回撤 | 调整天数 | 近两周 | PE | PE分位 | 高点时PE(记录日期) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        peak_pe = f"{r['peak_pe']:.1f} 倍（{r['peak_pe_date']}）" if r["peak_pe"] is not None else "—"
        lines.append(
            f"| {r['name']} | {r['last']:,.2f} | {r['last_date']} | {r['peak']:,.2f}（{r['peak_date']}） "
            f"| {r['dd']:.1f}% | {r['maxdd']:.1f}% | {r['days']} 天 | {r['chg2w']:+.1f}% | {r['pe']} | {r['pct']} | {peak_pe} |")
    lines += ["", "图文件：股债对照.png、三大指数对比.png；表格文本：三大指数对比.md。自动生成，不构成投资建议。"]
    md = "\n".join(lines)
    with open(os.path.join(OUT, "三大指数对比.md"), "w", encoding="utf-8") as f:
        f.write(md)
    return md

# ---------- Server酱 推送 ----------
def push_serverchan(title, desp):
    key = os.environ.get("SCT_SENDKEY")
    if not key:
        print("[push] 未配置 SCT_SENDKEY，跳过推送")
        return False
    try:
        r = requests.post(f"https://sctapi.ftqq.com/{key}.send",
                          data={"title": title, "desp": desp}, timeout=30)
        print("[push]", r.text[:200])
        return r.ok
    except Exception as e:
        print("[push] 失败:", e)
        return False

def main():
    if not is_due_week() and os.environ.get("FORCE_RUN") != "1":
        print("本周非双周执行周，跳过。")
        return
    be = fetch_bond_equity()
    chart = draw_bond_equity(be)
    rows = build_index_table()
    table_image = render_index_image(rows)
    md = render_report(rows, be)
    # 两张图片均使用已验证可见的 CDN 线路，并保留文字链接兜底。
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    version = beijing_today().isoformat()
    img_url = f"https://cdn.jsdmirror.com/gh/{repo}@output/out/%E8%82%A1%E5%80%BA%E5%AF%B9%E7%85%A7.png?v={version}" if repo else ""
    table_url = f"https://cdn.jsdmirror.com/gh/{repo}@output/{requests.utils.quote('out/三大指数对比.png')}?v={version}" if repo else ""
    index_date = max(r["last_date"] for r in rows)
    desp_lines = [
        f"**股债图：截至 {be['as_of']}（源站周频）**",
        f"**三大指数行情：截至 {index_date}**", "",
        f"沪深300全收益 {be['hs300_last']:,.0f}（年化 {be['hs300_cagr']}%） / 二级债基 {be['wind_last']:,.0f}（年化 {be['wind_cagr']}%）",
        "",
    ]
    for r in rows:
        desp_lines.append(f"- {r['name']}：{r['last']:,.2f} 点，距高点 {r['dd']:.1f}%，近两周 {r['chg2w']:+.1f}%")
    if img_url and table_url:
        desp_lines += [
            "", "**① 股债长期收益对照**", f"![股债对照图]({img_url})",
            "", "**② 三大指数全景对比（完整指标）**", f"![三大指数全景对比]({table_url})",
            "", f"[查看股债图]({img_url}) ｜ [查看完整对比表图片]({table_url})",
        ]
    payload = {"title": f"A股双周更新 {beijing_today():%m-%d}", "desp": "\n".join(desp_lines)}
    with open(os.path.join(OUT, "推送内容.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    if os.environ.get("DEFER_PUSH") == "1":
        print("[push] 推送内容已保存，待结果发布后再发送")
    else:
        push_serverchan(payload["title"], payload["desp"])
    print("完成：", chart, table_image)
    print(md)

if __name__ == "__main__":
    main()
