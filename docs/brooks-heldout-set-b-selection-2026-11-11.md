# 留出集 B 选样清单（历史扩充，挑拣版）

日期：2026-11-11（北京时间）。决定依据：用户 2026-11-11 17:58 点选「按挑拣版开工，往前扩 4–6 天留出集」。
状态：**选样已定，回收未开始。名单自本文件落档起冻结——回收后只测不调参；若拿其中任何一天调过规格，该日即降入训练集、切分作废重切。**

## 选样纪律

- 候选一律取 2026-10-16 之前：10-16/19/21/22 的文字真值已用于 v2 复刻/回测（legacy_days），不算干净留出，排除。
- 与现有集合零重叠：训练集（10-20、10-26、10-27、11-05、11-09）、留出集 A（10-28、11-10）均不在内。
- 日型以官网分类为准（视频标题 + 官网 tag 归档），不是事后看图自封：强趋势看视频标题的 Trend Day 定性，区间看官网 Trading Range Day / Failed Breakout tag。
- 只回收有官方终盘视频者；下列 6 天均已在选样阶段核到视频存在的证据（视频元数据标题或官网 Video 归档列表），回收时仍须逐日复核视频 ID 并留档。
- 历史留出是二等留出：只作快速筛选，最终达标仍以规格冻结后的新 session 为准（规格 v0 第 6/7 节口径不变）。

## 名单（6 天）

| # | 日期（US） | 角色 | 官网定性（证据） | 解说 | 用途 |
|---|---|---|---|---|---|
| 1 | 2026-10-15（周四） | 强趋势·多 | 视频标题「Opening Bull V Reversal Spike & Channel Bull Trend Day」；文章题「E-mini Failed Bear Breakout」 | Brad Wolff | 测 S3 命中（多头 spike 开盘） |
| 2 | 2026-10-14（周三） | 强趋势·空 | 视频标题「Small Pullback Bear Trend」；文章题「E-mini Bears Getting Strong Breakout」 | Joseph Imbornone | 测 S3 命中（空头小回调趋势） |
| 3 | 2026-10-13（周二） | 区间 | 官网 Trading Range Day tag 收录；官网 Video 归档列表（page 2）收录、当日条目带「end of day video review」 | 待回收时确认 | 测 S2 假阳/命中 + 区间日 S3 假阳 |
| 4 | 2026-10-08（周四） | 区间·核心 | 视频标题「Trading Range Day With Failed Bull Surprise Bar 2nd Leg Trap」（24:12）；官网 Trading Range Day 与 Failed Breakout 两 tag 均收录 | 待回收时确认 | 测 S2 核心：假突破 + 二腿陷阱正是 S2 家族标本 |
| 5 | 2026-10-12（周一） | 混合 | 视频标题「Lower High Major Trend Reversal」；文章题「E-mini Bulls Expect Test of All-Time High」 | Brad Wolff | 混合/反转日：测日型翻转下的门控行为 |
| 6 | 2026-10-07（周三） | 混合 | 视频标题「Bull Trending Trading Range Day」；文章题「E-mini Pullback after Test of 7,900 Round Number」 | Joseph Imbornone | 趋势型区间日：介于趋势与区间之间，测日型判定边界 |

备选（名单内某天回收失败时按序递补，不另行请示）：2026-10-09（周五，视频标题「Relentless Bull Channel」，Joseph，多头趋势）。

## 文章页（已核实 URL，仅列已确认者）

- 10-15：https://www.brookstradingcourse.com/analysis/e-mini-failed-bear-breakout-2/
- 10-14：https://www.brookstradingcourse.com/analysis/e-mini-bears-getting-strong-breakout/
- 10-12：https://www.brookstradingcourse.com/analysis/e-mini-bulls-expect-test-of-all-time-high/
- 10-07：https://www.brookstradingcourse.com/analysis/e-mini-pullback-after-test-of-7900-round-number/
- 10-13、10-08：经官网 Video 归档（/blog/video/）与 Trading Range Day tag 页（/tag/trading-range-day/）定位，不凭猜测拼 URL。

## 回收与封存口径（与阶段 1 同法）

1. 文章页取嵌入 YouTube 视频 ID → YouTube 观看页展开简介点「Show transcript」→ 滚动加载后存页 PDF → 本机 pdftotext 审计（段数/时间覆盖/缺口）→ 缺段屏读补齐。
2. 清洗版转录存 `hidden_files/brooks-<MMDD>-transcript.txt`（+ raw PDF）；转录全文永不进公开仓（公开边界不变）。
3. 按严口径提取（入场/出场/明说否决，逐条 bar 锚定 + 时间戳 + 转述、引文极短）存 `hidden_files/replication-ground-truth-<MMDD>-oral-upgrade.json`，meta 标注 `heldout_set: B`、`sealed: true`、`used_for_tuning: false`。
4. 提取完成后只登记计数与封存状态，不在本阶段拿它对规格逐条打分——打分是规格冻结后的阶段 3 工作；提前看细目只许到「计数与完整性」为止，避免污染。
