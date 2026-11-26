# -*- coding: utf-8 -*-
"""
A股双周更新（云端全自动版，无需 AI）
产出：
  1) out/股债对照.png  —— 沪深300全收益 vs 万得二级债基（原图同源数据）
  2) out/三大指数对比.md —— 上证 / 创业板 / 科创50 全景表
  3) 若配置环境变量 SCT_SENDKEY，则通过 Server酱 推送摘要到微信
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
def is_due_week(today=None):
    today = today or dt.date.today()
    anchor = dt.date(2026, 11, 30)
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
                 params={"param": f"{sym},week,2024-01-01,{dt.date.today():%Y-%m-%d},400"})
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
        rows.append(dict(name=name, last=last, last_date=str(last_date.date()),
                         peak=peak, peak_date=str(peak_date.date()),
                         dd=dd, maxdd=maxdd, days=days, chg2w=chg2w,
                         pe=pe_txt, pct=pct_txt))
    return rows

def render_report(rows, be):
    today = dt.date.today().isoformat()
    lines = [
        f"# A股双周更新（{today}）", "",
        f"## 一、股债对照图（数据截至 {be['as_of']}）", "",
        f"- 沪深300全收益：**{be['hs300_last']:,.0f}**，年化 **{be['hs300_cagr']}%**",
        f"- 万得二级债基：**{be['wind_last']:,.0f}**，年化 **{be['wind_cagr']}%**",
        f"- 股/债累计回报比：**{be['hs300_last']/be['wind_last']:.2f} 倍**", "",
        "## 二、三大指数全景对比", "",
        "| 指数 | 最新点位 | 日期 | 年内高点(日期) | 距高点 | 区间最大回撤 | 调整天数 | 近两周 | PE | PE分位 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['last']:,.2f} | {r['last_date']} | {r['peak']:,.0f}（{r['peak_date']}） "
            f"| {r['dd']:.1f}% | {r['maxdd']:.1f}% | {r['days']} 天 | {r['chg2w']:+.1f}% | {r['pe']} | {r['pct']} |")
    lines += ["", "图文件：股债对照.png；本表：三大指数对比.md。自动生成，不构成投资建议。"]
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
    md = render_report(rows, be)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    version = dt.date.today().isoformat()
    img_url = f"https://raw.githubusercontent.com/{repo}/output/out/%E8%82%A1%E5%80%BA%E5%AF%B9%E7%85%A7.png?v={version}" if repo else ""
    desp_lines = [
        f"**数据截至 {be['as_of']}**", "",
        f"沪深300全收益 {be['hs300_last']:,.0f}（年化 {be['hs300_cagr']}%） / 二级债基 {be['wind_last']:,.0f}（年化 {be['wind_cagr']}%）",
        "",
    ]
    for r in rows:
        desp_lines.append(f"- {r['name']}：{r['last']:,.0f} 点，距年内高点 {r['dd']:.1f}%，近两周 {r['chg2w']:+.1f}%")
    if img_url:
        desp_lines += ["", f"![股债对照图]({img_url})", "", f"[查看完整对比表](https://github.com/{repo}/blob/output/out/%E4%B8%89%E5%A4%A7%E6%8C%87%E6%95%B0%E5%AF%B9%E6%AF%94.md)"]
    payload = {"title": f"A股双周更新 {dt.date.today():%m-%d}", "desp": "\n".join(desp_lines)}
    with open(os.path.join(OUT, "推送内容.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    if os.environ.get("DEFER_PUSH") == "1":
        print("[push] 推送内容已保存，待结果发布后再发送")
    else:
        push_serverchan(payload["title"], payload["desp"])
    print("完成：", chart)
    print(md)

if __name__ == "__main__":
    main()
