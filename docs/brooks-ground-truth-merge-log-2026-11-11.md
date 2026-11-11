# Brooks ES 真值合并日志（2026-11-11，北京时间）

产物：`hidden_files/replication-ground-truth-merged-v2.json`（主体条目 285 条）。
性质：研究工作文件。未改任何源文件，未覆盖旧主文件，未动冻结引擎，不涉及真实资金。

## 一、做了什么

6 个口述真值升级文件自落档起都挂着「待合并（do not merge yet）」状态。本次按用户拍板把它们合并成一份主真值文件 `replication-ground-truth-merged-v2.json`，各升级文件原样保留在原地（合并前后 sha256 已记录在新文件的 `source_info` 里，逐日可查）。旧主文件 `replication-ground-truth.json` 未被覆盖。

## 二、Schema 差异（合并前实测）

三套 schema 并存，这是本次合并的主要复杂性：

1. **升级文件 schema（6 个文件统一外壳，内容口径分两类）**
   - 外壳统一：`{meta, new_items, upgraded_items, not_upgraded_items, rebuild_estimate}`；条目字段统一为 `{id, bar, dir, type, oral_ts, quote, note}`（`bar` 为 int 或区间字符串，保持原样未规范化；`type` 是自由文本而非枚举，如 `setup: stop entry long above bar 1...`，逐字保留）。
   - 10-26、10-27、10-28、11-05、11-09 五天：全部条目都在 `new_items` 里，`upgraded_items` 与 `not_upgraded_items` 为空——因为旧主文件只覆盖 10-16～10-22，这五天在主文件里原本没有条目可升级。
   - **10-20 是唯一的例外**：它是对旧主文件已有日期的升级，故结构不同——`new_items` 只有 20 条，另有 `upgraded_items` 5 条、`not_upgraded_items` 3 条。这 8 条批注没有独立 id，靠 `ref` 字段引用旧主文件条目（如 `setups[1020-a]`、`ai_flips[bar 21]`），本身不是独立决策点。
   - 11-05、11-09 的 `meta` 里另有 `next_day_expectations`（次日预期 5 条 / 4 条），属 meta 不属条目，合并未计入（与案例库口径一致）。

2. **旧主文件 schema（`replication-ground-truth.json`）**
   - 日级叙述结构：`days{日期: {review_url, author, day_type_final, phase_transitions[], ai_flips[], setups[], exit_logic_quotes[]}}`，覆盖 2026-10-16、10-19、10-20、10-21、10-22。
   - 与条目级 schema 不兼容：一个日期是一个整体叙事对象，setups 有自己的字段组（`signal_bar / entry_bar / basis / expected_exit_family` 等），硬拆成条目会丢失 phase/AI/出场语录的结构且需要发明字段映射。故按「不兼容不硬并」处理，见第四节。

3. **案例库 10-20 的实际来源 schema（`replication-ground-truth-1020-oral-full.json`）**
   - 又一套：`{meta, items[47], scoring, corrections}`，条目字段 `{id, cat, bar, dir, scored, certainty, sources, desc, correction}`，id 体系为 `PH-/AI-/ST-/V-/L-/EX-` 等，与升级文件的 `1020-oral-NN` 完全不同。它是 10-20 的派生合成集（转录 + 升级清单 + 缺口提取 + 旧主条目合成），不是升级文件本身。

## 三、逐日计数与校验

合并主体条目（`items`，= 各升级文件 `new_items` 之和）：

| 日期 | 合并条数 | 案例库登记 | 差 |
|---|---|---|---|
| 2026-10-20 | 20 | 47 | **−27** |
| 2026-10-26 | 50 | 50 | 0 |
| 2026-10-27 | 82 | 82 | 0 |
| 2026-10-28 | 60 | 60 | 0 |
| 2026-11-05 | 35 | 35 | 0 |
| 2026-11-09 | 38 | 38 | 0 |
| **合计** | **285** | **312** | **−27** |

校验结果（脚本断言 + 抽查，全过）：
- 合并总数 285 = 逐日之和（20+50+82+60+35+38），无多无少。
- 逐字一致性：285 条的全部原字段与源文件逐项比对，mismatch = 0；每条只新增 `date` 与 `source_file` 两个标注字段。
- id 全局唯一性：全部 id 带日期前缀（`MMDD-oral-NN`），重复数 = 0，未做任何改名或加前缀处理。
- 另有 10-20 批注 8 条（升级 5 + 未升级 3）原样存入新文件的 `annotations` 节，不计入 285。

## 四、对账差异说明（不静默抹平）

总差 −27 全部来自 10-20，是**来源口径差，不是数据丢失**。10-20 在本项目里有三个数字，分别对应三套东西：

- **20 条**：1020 口述升级文件的 `new_items`——本次合并采用的口径（与另外 5 天同一来源类型、同一条目 schema，可比性最好）。
- **47 条**：`oral-full` 登记集，案例库 v1 采用的口径。它在升级清单之上做了合成与拆分：例如 veto 家族条目被拆成 `V-cS1–S6 / V-cB1–B6` 等多条、补入了 phase/AI/出场语境条目（`PH-/AI-/EX-`）、保留了旧主文件的 `ST-a..d` 等。故 47 与 20 不是同一批条目的两种数法，不能直接相减理解为「少了 27 条」。
- **60 条**：口述严格口径的实测决策点总数（入场 19 / 出场 11 / 明说否决 27 / 隐含否决 3，见 1020 升级文件 `counting_basis` 与密度实测报告），这是「师父那天实际说了多少个决策点」的量，登记成条目的只有其中一部分。

处理决定：`oral-full` 文件不并入本次合并（其内容与 1020 `new_items` 大量重叠，双记必然重复计数），它作为案例库 10-20 的来源继续独立存在、未改动。后续若要统一 10-20 口径，应单独立项做 20↔47 的逐条映射表，而不是在合并里悄悄选边。

## 五、未纳入项及理由

1. **旧主文件中 2026-10-20 的日级对象**：与口述升级日重叠，且其内容已被口述真值升级（升级文件的 5 条批注正是引用它）。未纳入合并主体；原对象保留在旧主文件内不动。
2. **旧主文件其余 4 天（10-16、10-19、10-21、10-22）**：与 6 个升级日不重叠。Schema 为日级叙述结构、与条目级不兼容，不拆分改写；改为**原样整体纳入**新文件的 `legacy_days` 节（每节加 `date` 与 `source_file` 标注）。内容量：4 天共 setups 16 条（id `1016-a..d`、`1019-a..d`、`1021-a..d`、`1022-a..d`）、phase_transitions 9 条、ai_flips 7 条、exit_logic_quotes 7 条。这 4 天是文字版真值（无口述升级），密度口径与 6 天密真值不同，使用时注意。
3. **`replication-ground-truth-1020-oral-full.json`（47 条）**：派生合成集，理由见第四节，未纳入、未改动。
4. **11-05 / 11-09 的次日预期（meta.next_day_expectations，5+4 条）**：是预期不是当日决策点，两边口径一致地不计条目，仍保留在各自源文件 meta 中。

## 六、合并文件结构说明

`replication-ground-truth-merged-v2.json` 顶层五节：

- `meta`：标题/版本/构建日期、主体总数与逐日计数、结构说明、id 唯一性检查结果、与案例库的对账汇总（含 per-day 对照表）、未合并清单及理由、`legacy_days` 逐日计数。
- `source_info`：逐日来源说明——源文件名、sha256 前 16 位、原 status（「待合并」原文）、解说者（有记录的日子）、计数口径、覆盖缺口，逐字引自各升级文件 meta。
- `items`：285 条主体条目，原字段逐字保留 + `date` + `source_file`。
- `annotations`：仅 2026-10-20，`upgraded_items` 5 条 + `not_upgraded_items` 3 条原样。
- `legacy_days`：旧主文件 4 天日级对象原样 + `date` + `source_file`。

后续使用口径：做家族统计/批改对账时用 `items`（285，升级口径）；引用案例库数字（312）时注意其 10-20 为 47 条登记口径，两者相差的 27 只在该日、只因口径，不许混用。
