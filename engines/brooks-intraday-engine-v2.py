#!/usr/bin/env python3
"""
Brooks ES 盘中逐根决策回放引擎 v2（复刻修订版；变更日志见 replication-changelog.md）

与静态版的区别：没有盘前写死的 trigger/止损/目标。引擎逐根喂入 RTH 5 分钟 bar，
每根 bar 收盘后才更新状态（日型 / Always In / 位置）、识别 setup、生成 stop-entry
挂单；挂单只能在后续 bar 成交。决策函数每次只接收截至当前 bar 的数据切片，
结构上无法接触未来 bar。

用法（独立运行）：
  # 跑内置的 5 个回测日（2026-10-16/19/20/21/22，盘前背景已按前日复盘写死在 CONTEXTS）
  python3 brooks-intraday-engine-v2.py --all \
      --out-prefix ~/workspace/goals/es-brooks/hidden_files/backtest-prev5-intraday

  # 跑任意单个交易日（盘前背景全部来自参数 = 前一个交易日的复盘）
  python3 brooks-intraday-engine-v2.py --session 2026-10-20 \
      --prior-high 7773.25 --prior-low 7727.50 --prior-close 7734.75 \
      --magnets 7900 --bias range_slightly_bullish \
      --out-prefix /tmp/one-day

输出：<out-prefix>-decisions.json（逐根决策日志）、<out-prefix>-trades.json（逐笔明细+汇总），
并在 stdout 打印逐日一行摘要。

口径：MES $5/点，手续费 $2/张往返，每笔风险 <=$200（张数=floor(200/(止损点数*5))，
<1 跳过），每天最多 2 笔，日内平仓（最后一根 RTH bar 收盘强平）。
"""
import argparse, json, math, sys, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
POINT_VALUE = 5.0
FEE_PER_CONTRACT = 2.0
MAX_RISK = 200.0
MAX_TRADES_PER_DAY = 2
MIN_STOP_PTS = 8.0        # 5 分钟噪声下限：止损 <8 点的 setup 直接否决（不许收紧硬凑）
PENDING_VALID_BARS = 3    # stop-entry 挂单有效期（根）

CONTEXTS = {
    # 盘前背景只能来自前一个交易日的 Brooks 复盘（与静态版 plans 文件一致）
    "2026-10-16": dict(prior_date="2026-10-15", prior_high=7801.75, prior_low=7717.25,
                       prior_close=7791.0, magnets=[7900, 7800],
                       bias="bull_trend_day_followthrough_expected_but_mid_big_range",
                       review_url="https://www.brookstradingcourse.com/analysis/e-mini-failed-bear-breakout-2/"),
    "2026-10-19": dict(prior_date="2026-10-16", prior_high=7803.25, prior_low=7676.0,
                       prior_close=7703.0, magnets=[7760, 7672.75, 7600],
                       bias="range_lower_edge_buyers_below_second_leg_down_into_support_rejected",
                       review_url="https://www.brookstradingcourse.com/analysis/e-mini-hopeful-for-2nd-leg-down-after-trapped-bulls/"),
    "2026-10-20": dict(prior_date="2026-10-19", prior_high=7773.25, prior_low=7727.50,
                       prior_close=7734.75, magnets=[7900],
                       bias="range_breakout_mode_slightly_bullish_downside_limited",
                       review_url="https://www.brookstradingcourse.com/analysis/e-mini-continues-in-breakout-mode/"),
    "2026-10-21": dict(prior_date="2026-10-20", prior_high=7791.50, prior_low=7710.25,
                       prior_close=7759.0, magnets=[7900, 7800],
                       bias="sideways_to_up_bears_unlikely_below_prior_midpoint",
                       review_url="https://www.brookstradingcourse.com/analysis/e-mini-bulls-want-test-of-7900-round-number/"),
    "2026-10-22": dict(prior_date="2026-10-21", prior_high=7812.25, prior_low=7751.0,
                       prior_close=7799.0, magnets=[7900, 7700, 7600],
                       bias="range_continue_buyers_below_defend_7600",
                       review_url="https://www.brookstradingcourse.com/analysis/e-mini-bulls-want-2nd-leg-up-after-yesterday/"),
}
SESSIONS = list(CONTEXTS.keys())


def fetch_rth_bars(session):
    """从 Yahoo Finance 拉 ES=F 5m、只保留当日 RTH 09:30-16:00 ET 的 78 根。"""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/ES=F?interval=5m&range=1mo"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    res = data["chart"]["result"][0]
    ts, q = res["timestamp"], res["indicators"]["quote"][0]
    bars = []
    for i, t in enumerate(ts):
        dt = datetime.fromtimestamp(t, ET)
        if dt.date().isoformat() != session:
            continue
        mins = dt.hour * 60 + dt.minute
        if not (570 <= mins < 960):
            continue
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        bars.append(dict(idx=len(bars) + 1, time=dt.strftime("%H:%M"),
                         o=round(o, 2), h=round(h, 2), l=round(l, 2), c=round(c, 2)))
    return bars


# ---------- bar 特征（只用当前及过去 bar） ----------
def rng(b): return b["h"] - b["l"]
def body(b): return b["c"] - b["o"]
def close_loc(b):
    r = rng(b)
    return (b["c"] - b["l"]) / r if r > 0 else 0.5
def is_strong(b, d):
    r = rng(b)
    if r < 5: return False
    if d > 0: return body(b) >= 0.55 * r and close_loc(b) >= 0.70
    return body(b) <= -0.55 * r and close_loc(b) <= 0.30


class Engine:
    """逐根状态机。step() 一次只喂一根 bar，内部状态从不见未来 bar。"""

    def __init__(self, session, ctx):
        self.session, self.ctx = session, ctx
        self.prior_mid = (ctx["prior_high"] + ctx["prior_low"]) / 2
        self.bars = []                    # 仅已喂入的 bar（决策的全部信息来源）
        self.ai = 0                       # Always In: +1 long / -1 short / 0 neutral
        self.candidate = None             # {dir, bar_idx, mid, hi, lo} 待确认的翻转候选
        self.day_open = None
        self.day_high = -1e9; self.day_low = 1e9
        self.day_high_bar = 0; self.day_low_bar = 0
        self.last_new_extreme = {1: -99, -1: -99}   # 上次创当日新高/新低的 bar
        # 回调计数机（S1）：跟随 ai 方向
        self.leg_extreme = None
        self.pullback = None              # {extreme_swing, a_done, a_bar_extreme, leg2}
        # 交易状态
        self.position = None
        self.pending = None
        self.trades = []
        self.failed = set()               # 当天已失败的 (setup, dir)
        self.cash = 10000.0
        self.log = []
        self.considered = []              # 考虑过又否决/未成交的记录（报告用）
        # ---- v2 新增状态 ----
        self.ema20 = None                 # 20 期 EMA（Brooks 图上的均线，失望出场用）
        self.pending_flip = None          # {dir, extreme, expires} 强位移语境下待极端确认的翻转
        self.cooldown_until = -1          # 翻转平仓后的冷却 bar（解耦：平仓的翻转不能立刻反向开仓）
        self.flip_exit_bar = -99

    # ---------- 工具 ----------
    def levels(self, setup):
        """关键价位：前日高/低、复盘磁吸位、50 点整数位、当日已确立极值
        （>=4 根前创下的当日高/低才算数——刚创的极值是行情本身，不是目标）。
        前日中点只对 S2（区间边缘反手、以中点为天然目标）计入；
        S1/S3 是趋势/突破类，目标看远端边缘与磁吸位，不被中点截断。
        v2 轮2 修正：S3 的目标候选排除当日极值——当日极值正是突破入场的前提本身
        （正在被突破的价位），不是磁吸位；把它当目标会让突破单在入场价上方一点点被否决/截断。"""
        lv = {self.ctx["prior_high"], self.ctx["prior_low"]}
        lv.update(self.ctx["magnets"])
        if setup == "S2": lv.add(self.prior_mid)
        cur = self.bars[-1]["idx"]
        if setup != "S3":
            if self.day_high_bar and cur - self.day_high_bar >= 4: lv.add(self.day_high)
            if self.day_low_bar and cur - self.day_low_bar >= 4: lv.add(self.day_low)
        base = math.floor(self.bars[-1]["c"] / 50) * 50
        for k in range(-3, 4):
            lv.add(base + 50 * k)
        return sorted(lv)

    def pick_target(self, entry, stop, d, setup):
        """目标 = 最近的关键价位；盈亏比不合格则否决（不许越过它去够更远的磁吸位）。
        门槛：S1/S3（趋势/突破，胜率结构性偏低）需 RR>=1.0；
        S2（已确认震荡语境下的边缘假突破反手，兑现概率结构性高）需 RR>=0.75。"""
        dist = abs(entry - stop)
        cands = [x for x in self.levels(setup) if (x - entry) * d > 0.25]
        if not cands: return None, "无方向上关键价位"
        if d < 0: cands = cands[::-1]
        nearest = cands[0]
        if setup == "S2":
            # 区间反手：目标就是最近的关键价位（中点/对沿），门槛 RR>=0.75
            rr = abs(nearest - entry) / dist
            if rr < 0.75: return None, f"最近关键价位 {nearest} 盈亏比 {rr:.2f}<0.75"
            return nearest, f"目标 {nearest}（盈亏比 {rr:.2f}）"
        # v2 C6：S3（突破顺势）改为取最近关键价位作目标，门槛 RR>=0.75
        #（Brooks：到最近 measured move/磁吸位先落袋，不越过它去够更远的价位；
        #   v1 在 S3 上跳过近处价位取 RR>=1 的远位，实测多次持仓过久被反转吃掉）。
        if setup == "S3":
            rr = abs(nearest - entry) / dist
            if rr < 0.75: return None, f"最近关键价位 {nearest} 盈亏比 {rr:.2f}<0.75"
            return nearest, f"目标 {nearest}（最近磁吸位，盈亏比 {rr:.2f}）"
        # S1 趋势/突破类：近处价位是途经的屏障而非目标，
        # 目标取第一个盈亏比 >=1 的关键价位；一个都没有则否决。
        for x in cands:
            rr = abs(x - entry) / dist
            if rr >= 1.0: return x, f"目标 {x}（盈亏比 {rr:.2f}，途经屏障 {nearest}）"
        return None, f"无盈亏比>=1 的关键价位（最近 {nearest} 仅 {abs(nearest-entry)/dist:.2f}）"

    def contracts_for(self, dist):
        return math.floor(MAX_RISK / (dist * POINT_VALUE))

    def note(self, bar, kind, detail):
        self.considered.append(dict(bar=bar["idx"], time=bar["time"], kind=kind, detail=detail))

    # ---------- 状态更新 ----------
    def trend_on(self, d):
        """趋势态：AI 同向 + 收盘在当日区间外侧半区 + 位移达标 + 近期仍有新极值。"""
        if self.ai != d or not self.bars: return False
        b = self.bars[-1]
        loc = (b["c"] - self.day_low) / max(self.day_high - self.day_low, 0.25)
        if d > 0 and loc < 0.5: return False
        if d < 0 and loc > 0.5: return False
        disp = abs(b["c"] - self.day_open)
        leg = (b["c"] - self.day_low) if d > 0 else (self.day_high - b["c"])
        if disp < 15 and leg < 20: return False
        return b["idx"] - self.last_new_extreme[d] <= 14

    def day_type_state(self):
        if self.trend_on(1): return "trend_bull"
        if self.trend_on(-1): return "trend_bear"
        return "range"

    def position_third(self):
        b = self.bars[-1]
        span = max(self.day_high - self.day_low, 0.25)
        loc = (b["c"] - self.day_low) / span
        return ("lower" if loc < 1/3 else "upper" if loc > 2/3 else "middle"), round(loc, 2)

    def _confirm_ok(self, b, cand):
        """翻转确认的第二道门：确认 bar 收盘必须越过候选 bar 之前 5 根的反向摆动极值
        （多头翻转要收在那段最高点之上，空头翻转要收在最低点之下）。
        否则只是通道内的反弹/回落，不算 Always In 翻转。"""
        pre = cand["pre_extreme"]
        if pre is not None:
            if cand["dir"] > 0 and b["c"] <= pre: return False
            if cand["dir"] < 0 and b["c"] >= pre: return False
        # 序列总位移门槛：候选序列极端到确认收盘 <8 点只是紧通道内的漂移，不算翻转
        if cand["dir"] > 0 and b["c"] - min(cand["lo"], b["l"]) < 8: return False
        if cand["dir"] < 0 and max(cand["hi"], b["h"]) - b["c"] < 8: return False
        return True

    def update_ai(self, b):
        """强 bar 只是候选；须跟随确认（次根收盘越过候选 bar 中点且不反向强势，
        或连续第二根同向强 bar）+ 收盘越过此前 5 根摆动极值，才翻转。
        单根 surprise 不翻转。"""
        self._ai_before = self.ai
        event = None
        for d in (1, -1):
            if is_strong(b, d):
                if self.candidate and self.candidate["dir"] == d and b["idx"] - self.candidate["bar"] <= 2:
                    if self.ai != d and self._confirm_ok(b, self.candidate):
                        event = (d, self.candidate["bar"], b["idx"])
                        self.ai = d
                    self.candidate = None
                elif self.ai == d:
                    self.candidate = None
                else:
                    prev5 = self.bars[-6:-1]
                    pre = (max(x["h"] for x in prev5) if d > 0 else min(x["l"] for x in prev5)) if prev5 else None
                    self.candidate = dict(dir=d, bar=b["idx"], mid=(b["h"] + b["l"]) / 2,
                                          hi=b["h"], lo=b["l"], pre_extreme=pre)
                break
        else:
            if self.candidate:
                cand = self.candidate
                d = cand["dir"]
                follow = (b["c"] >= cand["mid"] and close_loc(b) >= 0.45) if d > 0 else \
                         (b["c"] <= cand["mid"] and close_loc(b) <= 0.55)
                beyond = (b["c"] < cand["lo"]) if d > 0 else (b["c"] > cand["hi"])
                if follow and b["idx"] - cand["bar"] <= 2 and self._confirm_ok(b, cand):
                    if self.ai != d:
                        event = (d, cand["bar"], b["idx"])
                        self.ai = d
                    self.candidate = None
                elif beyond or b["idx"] - cand["bar"] >= 2:
                    self.candidate = None
                else:
                    cand["hi"] = max(cand["hi"], b["h"]); cand["lo"] = min(cand["lo"], b["l"])
        if self.candidate and b["idx"] != self.candidate["bar"]:
            self.candidate["hi"] = max(self.candidate["hi"], b["h"])
            self.candidate["lo"] = min(self.candidate["lo"], b["l"])
        # ---- v2 C7（轮2）：初始 AI 确立门槛 ----
        # 开盘最初几根是 opening range 噪声：bar<4 时，除非收盘离日开位移 >=12 点
        # （真 spike），否则不确立 Always In（避免 gap 日开盘一根反向 bar 就把全天锚错方向）。
        if event is not None and getattr(self, '_ai_before', 0) == 0 and b["idx"] < 4:
            if self.day_open is None or abs(b["c"] - self.day_open) < 12:
                self.note(b, "initial_ai_veto",
                          f"bar{b['idx']} 的 AI 确立候选被开盘门槛否决（离日开位移 <12 点，opening range 噪声）")
                self.ai = 0
                event = None
        # ---- v2 C1：翻转确认的语境门 ----
        # 通用规则（Brooks：强趋势/高潮语境里的第一次反向强 bar 默认是 minor reversal，
        # 趋势里的回调反弹不是翻转）：当日振幅已 >=40 点、或收盘离日开 >=30 点时，
        # 反向翻转在常规确认之上还须一根后续 bar 收盘越过候选序列的极端，才算 Always In 翻转；
        # 4 根内未越过则候选作废。初始翻转（ai=0）不设门。
        if event is not None and self.pending_flip is None:
            day_range = self.day_high - self.day_low
            disp = abs(b["c"] - self.day_open) if self.day_open is not None else 0
            # 主导腿位移：日开到主导方向极端的距离（spike/channel 的实际推进幅度）
            leg = 0
            if self.day_open is not None:
                leg = (self.day_open - self.day_low) if event[0] > 0 else (self.day_high - self.day_open)
            prev_ai = getattr(self, '_ai_before', 0)
            # v2 轮4 豁免：翻转发生在当日区间边缘（做多翻转时收盘在下三分之一、
            # 做空翻转时在上三分之一）是 Brooks 的边缘反手语境（双底/双顶复测），
            # 不是趋势中部的抢跑，不设语境门
            loc_now = (b["c"] - self.day_low) / max(day_range, 0.25) if day_range > 0 else 0.5
            at_edge = (event[0] > 0 and loc_now <= 0.35) or (event[0] < 0 and loc_now >= 0.65)
            if prev_ai != 0 and not at_edge and (day_range >= 40 or disp >= 30 or leg >= 25):
                seq = self.bars[event[1] - 1:]
                extreme = (max(x["h"] for x in seq) if event[0] > 0 else min(x["l"] for x in seq))
                self.pending_flip = dict(dir=event[0], extreme=extreme,
                                         expires=b["idx"] + 4, from_bar=b["idx"])
                self.ai = prev_ai
                self.note(b, "flip_gated",
                          f"AI 反向翻转候选（{'多' if event[0]>0 else '空'}）触发语境门（振幅 {day_range:.1f}/离日开 {disp:.1f}/主导腿 {leg:.1f}），"
                          f"须后续 bar 收盘越过 {extreme} 才确认，4 根内未越过作废")
                event = None
        # pending_flip 的极端确认/过期
        if self.pending_flip is not None:
            pf = self.pending_flip
            if b["idx"] > pf["from_bar"]:
                confirmed = (b["c"] > pf["extreme"]) if pf["dir"] > 0 else (b["c"] < pf["extreme"])
                if confirmed:
                    self.ai = pf["dir"]
                    event = (pf["dir"], pf["from_bar"], b["idx"], True)  # 第4元 late=True：经语境门滞后确认
                    self.note(b, "flip_confirmed_late",
                              f"语境门翻转确认：收盘 {b['c']} 越过极端 {pf['extreme']}，AI 翻向{'多' if pf['dir']>0 else '空'}")
                    self.pending_flip = None
                elif b["idx"] >= pf["expires"]:
                    self.note(b, "flip_gated_expired",
                              f"语境门翻转候选在 {pf['expires']} 前未获极端确认，作废（原 AI 方向不变）")
                    self.pending_flip = None
        return event

    # ---------- 回调计数（S1 的 H2/L2） ----------
    def update_pullback(self, b, prev):
        d = self.ai
        if d == 0:
            self.pullback = None; self.leg_extreme = None; return None
        if self.leg_extreme is None:
            self.leg_extreme = b["h"] if d > 0 else b["l"]
        signal = None
        # 趋势方向极值：多头看高点、空头看低点
        ext = (b["h"] - self.leg_extreme) if d > 0 else (self.leg_extreme - b["l"])
        if self.pullback is None:
            if ext > 0:
                self.leg_extreme = b["h"] if d > 0 else b["l"]
            elif (b["c"] - prev["c"]) * d < 0 or abs(b["c"] - self.leg_extreme) >= 5:
                self.pullback = dict(swing_lo=b["l"], swing_hi=b["h"],
                                     a_done=False, a_extreme=None, leg2=False)
        else:
            pb = self.pullback
            pb["swing_lo"] = min(pb["swing_lo"], b["l"]); pb["swing_hi"] = max(pb["swing_hi"], b["h"])
            tex = b["h"] if d > 0 else b["l"]; ptex = prev["h"] if d > 0 else prev["l"]
            is_signal = (b["c"] - prev["c"]) * d > 0 and (tex - ptex) * d > 0 and body(b) * d > 0
            if ext > 0:  # 回调中先创新极值 = 回调结束、计数作废
                self.leg_extreme = b["h"] if d > 0 else b["l"]; self.pullback = None
            elif is_signal:
                if not pb["a_done"]:
                    pb["a_done"] = True
                    pb["a_extreme"] = b["l"] if d > 0 else b["h"]
                    self.note(b, "attempt_marked",
                              f"{'H1' if d>0 else 'L1'} 信号（bar{b['idx']}），只标记不入场，等两腿回调的第二信号")
                elif pb["leg2"]:
                    signal = (d, b, pb)
                    self.pullback = None
            else:
                # v2 C4：两腿之间须有一次 >=3 点的顺势小摆动（Brooks 的“腿”由摆动分隔，
                # 不是单根极值计数）；先确认 bounce，再创新回调极值才算第二腿成立
                if pb["a_done"] and not pb.get("bounce_ok"):
                    if (d > 0 and b["h"] >= pb["a_extreme"] + 3) or (d < 0 and b["l"] <= pb["a_extreme"] - 3):
                        pb["bounce_ok"] = True
                if pb["a_done"] and not pb["leg2"] and pb.get("bounce_ok"):
                    if (d > 0 and b["l"] < pb["a_extreme"]) or (d < 0 and b["h"] > pb["a_extreme"]):
                        pb["leg2"] = True
        return signal

    # ---------- setup 生成 ----------
    def try_create_pending(self, b, setup, d, entry, stop, why):
        dist = abs(entry - stop)
        if self.position or self.pending:
            self.note(b, "veto", f"{setup} 已有持仓/挂单，未另开"); return
        if len(self.trades) >= MAX_TRADES_PER_DAY:
            self.note(b, "veto", f"{setup} 当日已达 {MAX_TRADES_PER_DAY} 笔上限"); return
        # v2 C2：翻转平仓后 5 根内不开新仓（平仓与反向入场解耦，防同一误判被交易两次）
        # 轮3 豁免：S1 回调第二入场是慢机制（须两腿摆动），不是立即反向追单，不受冷却限制
        if b["idx"] <= self.cooldown_until and setup != "S1":
            self.note(b, "veto", f"{setup} 翻转平仓冷却期内（至 bar{self.cooldown_until}），不开新仓"); return
        # v2 C5：预算保留——当日第一笔已亏且仍在午前（bar<49），第二笔只允许
        # S2 边缘反手、或位移 >=20 点的 S3；S1 与弱 S3 留给午后真 setup
        if len(self.trades) == 1 and self.trades[0]["net"] < 0 and b["idx"] < 49:
            if setup == "S1":
                self.note(b, "veto", "S1 预算保留：首笔已亏且午前，第二笔额度留给午后（仅 S2/强 S3 可用）"); return
            if setup == "S3" and abs(entry - stop) < 20:
                self.note(b, "veto", "S3 预算保留：首笔已亏且午前，翻转序列位移 <20 点，额度留给午后"); return
        if (setup, d) in self.failed:
            self.note(b, "veto", f"{setup} 同方向今日已失败一次，不再重复"); return
        if dist < MIN_STOP_PTS:
            self.note(b, "veto", f"{setup} 止损距 {dist:.2f} 点 < {MIN_STOP_PTS} 点噪声下限，否决（不收紧硬凑）"); return
        n = self.contracts_for(dist)
        if n < 1:
            self.note(b, "veto", f"{setup} 止损距 {dist:.2f} 点，张数公式 <1，否决"); return
        target, why_t = self.pick_target(entry, stop, d, setup)
        if target is None:
            self.note(b, "veto", f"{setup} 目标否决：{why_t}"); return
        self.pending = dict(setup=setup, dir=d, entry=entry, stop=stop, target=target,
                            contracts=n, created_bar=b["idx"], valid_until=b["idx"] + PENDING_VALID_BARS,
                            why=why + "；" + why_t)
        self.note(b, "pending_created",
                  f"{setup} {'做多' if d>0 else '做空'} entry {entry} stop {stop} target {target} x{n}（{why}）")

    def setups_at_close(self, b, prev, ai_event, s1_signal):
        # S3：Always In 刚确认翻转 -> 顺势 stop entry（信号序列极端外 0.25）
        if ai_event:
            d, first_bar = ai_event[0], ai_event[1]
            late = len(ai_event) > 3 and ai_event[3]
            seq = self.bars[first_bar - 1:]
            if d > 0:
                entry = max(x["h"] for x in seq) + 0.25; stop = min(x["l"] for x in seq) - 0.25
            else:
                entry = min(x["l"] for x in seq) - 0.25; stop = max(x["h"] for x in seq) + 0.25
            chase_veto = late and b["idx"] - first_bar > 2
            if chase_veto:
                # v2 轮3：滞后确认的翻转只作状态确认，不追价开仓（Brooks：错过原始信号
                # 不追已经走了 20+ 点的行情，等第一次回调的第二入场）
                self.note(b, "veto", f"S3 翻转于 bar{first_bar} 发起、bar{b['idx']} 才经语境门确认，滞后 >2 根，不追价；等回调 S1")
            third, loc = self.position_third()
            ploc = (b["c"] - self.ctx["prior_low"]) / max(self.ctx["prior_high"] - self.ctx["prior_low"], 0.25)
            if chase_veto:
                pass
            elif 1/3 < ploc < 2/3:
                self.note(b, "veto", f"S3 AI 翻转已确认（bar{first_bar}-{b['idx']}），但收盘在前日大区间中部三分之一（loc {ploc:.2f}），规则2 位置否决")
            elif (d > 0 and third == "lower") or (d < 0 and third == "upper"):
                self.note(b, "veto", f"S3 AI 翻转已确认（bar{first_bar}-{b['idx']}），但收盘在当日区间不利三分区（loc {loc}），位置否决")
            else:
                self.try_create_pending(b, "S3", d, entry, stop,
                                        f"AI 于 bar{b['idx']} 确认翻向{'多' if d>0 else '空'}（强 bar bar{first_bar}+跟随）")
        # S1：趋势态中的两腿回调第二入场
        if s1_signal:
            d, sig_bar, pb = s1_signal
            if not self.trend_on(d):
                self.note(b, "veto", f"S1 {'H2' if d>0 else 'L2'} 信号成立但趋势态未确认（trend_on=False），否决")
            else:
                if d > 0: entry, stop = sig_bar["h"] + 0.25, pb["swing_lo"] - 0.25
                else: entry, stop = sig_bar["l"] - 0.25, pb["swing_hi"] + 0.25
                self.try_create_pending(b, "S1", d, entry, stop,
                                        f"趋势态两腿回调第二信号（信号 bar{sig_bar['idx']}）")
        # S2：区间边缘假突破反手（近 2 根刺破前日高/低 >=2 点、当根收回区间内且为强反转 bar）
        if self.day_type_state() == "range" and len(self.bars) >= 2:
            ph, pl = self.ctx["prior_high"], self.ctx["prior_low"]
            last2 = self.bars[-2:]
            if max(x["h"] for x in last2) > ph + 2 and b["c"] < ph and is_strong(b, -1):
                self.try_create_pending(b, "S2", -1, b["l"] - 0.25, max(x["h"] for x in last2) + 0.25,
                                        f"刺破前日高 {ph} 后收回其下 + 强空信号 bar{b['idx']}，假突破反手")
            elif min(x["l"] for x in last2) < pl - 2 and b["c"] > pl and is_strong(b, 1):
                self.try_create_pending(b, "S2", 1, b["h"] + 0.25, min(x["l"] for x in last2) - 0.25,
                                        f"刺破前日低 {pl} 后收回其上 + 强多信号 bar{b['idx']}，假突破反手")

    # ---------- 主循环：逐根喂入 ----------
    def step(self, b):
        prev = self.bars[-1] if self.bars else None
        self.bars.append(b)
        if self.day_open is None: self.day_open = b["o"]
        if b["h"] > self.day_high:
            self.day_high = b["h"]; self.day_high_bar = b["idx"]; self.last_new_extreme[1] = b["idx"]
        if b["l"] < self.day_low:
            self.day_low = b["l"]; self.day_low_bar = b["idx"]; self.last_new_extreme[-1] = b["idx"]
        action = "none"

        # 1) 持仓出场（入场 bar 之后才判；同根止损/目标双触按止损）
        if self.position and b["idx"] > self.position["entry_bar"]:
            p = self.position; d = p["dir"]; exit_px = None; reason = None
            if d > 0:
                if b["l"] <= p["stop"]: exit_px, reason = p["stop"], "止损"
                elif b["h"] >= p["target"]: exit_px, reason = p["target"], "目标"
            else:
                if b["h"] >= p["stop"]: exit_px, reason = p["stop"], "止损"
                elif b["l"] <= p["target"]: exit_px, reason = p["target"], "目标"
            if exit_px is not None:
                self.close_position(b, exit_px, reason); action = f"exit:{reason}"
        # 2) 挂单成交（stop entry；跳空越过按开盘价）
        if not self.position and self.pending and b["idx"] > self.pending["created_bar"]:
            pd = self.pending; filled = None
            if pd["dir"] > 0 and b["h"] >= pd["entry"]: filled = max(pd["entry"], b["o"]) if b["o"] > pd["entry"] else pd["entry"]
            if pd["dir"] < 0 and b["l"] <= pd["entry"]: filled = min(pd["entry"], b["o"]) if b["o"] < pd["entry"] else pd["entry"]
            if filled is not None:
                self.position = dict(setup=pd["setup"], dir=pd["dir"], entry=filled,
                                     stop=pd["stop"], target=pd["target"], contracts=pd["contracts"],
                                     entry_bar=b["idx"], why=pd["why"],
                                     risk_pts=abs(filled - pd["stop"]), mfe_pts=0.0)
                self.note(b, "filled", f"{pd['setup']} 成交 {filled}（bar{b['idx']}）")
                self.pending = None; action = "filled"
            elif b["idx"] >= pd["valid_until"]:
                self.note(b, "pending_expired",
                          f"{pd['setup']} 挂单 entry {pd['entry']} 在 {PENDING_VALID_BARS} 根内未触发，过期")
                self.pending = None; action = "pending_expired"
        # 3) 收盘后更新状态（只用 <= 当前 bar）
        ai_event = self.update_ai(b)
        s1_signal = self.update_pullback(b, prev) if prev else None
        # 3.5) v2 C3：失望出场（Brooks：swing 单失望即走）
        # 先更新 EMA20 与持仓 MFE（只用当前及过去 bar）
        self.ema20 = b["c"] if self.ema20 is None else self.ema20 + (2 / 21) * (b["c"] - self.ema20)
        if self.position and b["idx"] > self.position["entry_bar"]:
            p = self.position; d = p["dir"]
            fav = (b["h"] - p["entry"]) if d > 0 else (p["entry"] - b["l"])
            p["mfe_pts"] = max(p["mfe_pts"], fav)
            held = b["idx"] - p["entry_bar"]; risk = max(p["risk_pts"], 0.25)
            unreal = (b["c"] - p["entry"]) * d
            # v2 轮2 结构守卫：失望类出场还须收盘越过近 10 根（不含当根）的反向极值
            # ——趋势中的普通回调不算 premise 失败，结构被破才算（Brooks 的失望是结构性的）
            prev10 = self.bars[-11:-1]
            struct_break = False
            if len(prev10) >= 5:
                if d > 0 and b["c"] < min(x["l"] for x in prev10): struct_break = True
                if d < 0 and b["c"] > max(x["h"] for x in prev10): struct_break = True
            # A 回吐离场：曾达 >=1R 浮盈，收盘回到 <=0.25R 且（结构被破或收盘穿到 EMA20 反侧）
            ema_adverse = (d > 0 and b["c"] < self.ema20) or (d < 0 and b["c"] > self.ema20)
            if held >= 5 and p["mfe_pts"] >= risk and unreal <= 0.25 * risk and (struct_break or ema_adverse):
                self.close_position(b, b["c"], "回吐离场"); action = "exit:回吐"
            # B 无跟随离场：持 >=10 根、MFE <0.5R、收盘站到 EMA20 反侧且结构被破
            elif held >= 10 and p["mfe_pts"] < 0.5 * risk and struct_break and \
                    ((d > 0 and b["c"] < self.ema20) or (d < 0 and b["c"] > self.ema20)):
                self.close_position(b, b["c"], "失望离场"); action = "exit:失望"
        # 4) 持仓中 AI 确认反向翻转 -> 收盘平仓（Always In 翻转 = 原方向失效）
        if self.position and ai_event and ai_event[0] != self.position["dir"]:
            self.close_position(b, b["c"], "AI翻转平仓"); action = "exit:AI翻转"
            self.cooldown_until = b["idx"] + 5; self.flip_exit_bar = b["idx"]
        # 5) 日终强平
        if self.position and b["idx"] == 78:
            self.close_position(b, b["c"], "日终平仓"); action = "exit:日终"
        # 6) 新 setup（收盘后生成，只能在后续 bar 成交）
        if prev:
            self.setups_at_close(b, prev, ai_event, s1_signal)

        third, loc = self.position_third()
        self.log.append(dict(session=self.session, bar=b["idx"], time=b["time"],
                             o=b["o"], h=b["h"], l=b["l"], c=b["c"],
                             ai=self.ai, day_type=self.day_type_state(),
                             position_third=third, position_loc=loc,
                             vs_prior=("above" if b["c"] > self.ctx["prior_high"] else
                                       "below" if b["c"] < self.ctx["prior_low"] else "inside"),
                             in_position=bool(self.position),
                             pending=(self.pending["setup"] if self.pending else None),
                             action=action))

    def close_position(self, b, exit_px, reason):
        p = self.position
        gross = (exit_px - p["entry"]) * p["dir"] * p["contracts"] * POINT_VALUE
        fee = FEE_PER_CONTRACT * p["contracts"]
        net = gross - fee
        self.cash += net
        if net < 0: self.failed.add((p["setup"], p["dir"]))
        self.trades.append(dict(session=self.session, setup=p["setup"], dir=p["dir"],
                                 entry_bar=p["entry_bar"], entry=p["entry"], stop=p["stop"],
                                 target=p["target"], contracts=p["contracts"],
                                 exit_bar=b["idx"], exit_time=b["time"], exit=exit_px,
                                 exit_reason=reason, hold_bars=b["idx"] - p["entry_bar"],
                                 gross=round(gross, 2), fee=fee, net=round(net, 2), why=p["why"]))
        self.note(b, "exit", f"{p['setup']} {reason} 出场 {exit_px}，净 {net:+.2f}")
        self.position = None


def run_session(session, ctx, bars=None):
    bars = bars if bars is not None else fetch_rth_bars(session)
    assert len(bars) == 78, f"{session}: RTH bars = {len(bars)} != 78"
    eng = Engine(session, ctx)
    for b in bars:
        eng.step(b)          # 逐根喂入：step 内部只能看到已喂入的 bar
    return eng


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session"); ap.add_argument("--all", action="store_true")
    ap.add_argument("--prior-high", type=float); ap.add_argument("--prior-low", type=float)
    ap.add_argument("--prior-close", type=float); ap.add_argument("--magnets", default="")
    ap.add_argument("--bias", default="custom"); ap.add_argument("--out-prefix", required=True)
    a = ap.parse_args()
    jobs = []
    if a.all:
        jobs = [(s, CONTEXTS[s]) for s in SESSIONS]
    else:
        ctx = dict(prior_date="custom", prior_high=a.prior_high, prior_low=a.prior_low,
                   prior_close=a.prior_close,
                   magnets=[float(x) for x in a.magnets.split(",") if x],
                   bias=a.bias, review_url="")
        jobs = [(a.session, ctx)]
    all_decisions, all_trades, summary = [], [], []
    for session, ctx in jobs:
        eng = run_session(session, ctx)
        all_decisions.extend(eng.log)
        all_trades.extend(eng.trades)
        day_net = sum(t["net"] for t in eng.trades)
        wins = sum(1 for t in eng.trades if t["net"] > 0)
        final_type = eng.log[-1]["day_type"]
        # 日型稳定 bar（事后从日志统计，非交易决策）：最后一次状态 != 最终状态的 bar +1
        last_diff = max([l["bar"] for l in eng.log if l["day_type"] != final_type], default=0)
        ai_flips = [n for n in eng.considered if n["kind"] == "pending_created"]
        summary.append(dict(session=session, trades=len(eng.trades), wins=wins,
                            net=round(day_net, 2), final_day_type=final_type,
                            day_type_stable_from_bar=last_diff + 1,
                            end_cash=round(eng.cash if session == jobs[-1][0] else 0, 2),
                            considered=eng.considered))
        print(f"{session}: trades={len(eng.trades)} wins={wins} net={day_net:+.2f} "
              f"final_day_type={final_type} stable_from_bar{last_diff + 1}")
        for t in eng.trades:
            print(f"   {t['setup']} {'L' if t['dir']>0 else 'S'} bar{t['entry_bar']}@{t['entry']} -> "
                  f"bar{t['exit_bar']}@{t['exit']} ({t['exit_reason']}) x{t['contracts']} net {t['net']:+.2f}")
    total = sum(t["net"] for t in all_trades)
    wins = sum(1 for t in all_trades if t["net"] > 0)
    print(f"TOTAL: trades={len(all_trades)} wins={wins} net={total:+.2f} final_cash={10000 + total:.2f}")
    with open(a.out_prefix + "-decisions.json", "w") as f:
        json.dump(all_decisions, f, ensure_ascii=False, indent=1)
    with open(a.out_prefix + "-trades.json", "w") as f:
        json.dump(dict(trades=all_trades, summary=summary,
                       total_net=round(total, 2), wins=wins,
                       final_cash=round(10000 + total, 2)), f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
