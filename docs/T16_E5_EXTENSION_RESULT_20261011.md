# E5 扩展结果（2026-10-11）

## 1. Italy 更大位姿偏移

入口：`scripts/m5_pose_sweep.ps1` → `scripts/m5_pose_sweep.py`，资格化结果目录：
`logs/experiments/e5_pose_sweep_large_20261011/`。

请求矩阵：横向偏移 `{+1.5,+2.0}` m × 航向偏移 `{0,+10}`°；其它配置固定为
Italy、strict + sensor、`seg_model_hand`、25 s、6 m/s、墙钟上限 150 s、`production_alignment`。

| pose | status | qualified | 原因 |
|---|---|---:|---|
| d=+1.5 m, Δψ=0° | invalid | 否 | telemetry exposure too short |
| d=+1.5 m, Δψ=+10° | completed | 是 | — |
| d=+2.0 m, Δψ=0° | invalid | 否 | telemetry exposure too short |
| d=+2.0 m, Δψ=+10° | completed | 是 | — |

**解释边界**：两个 `completed` 结果通过资格入口的配置/退出/清理检查；两个 `invalid` 结果保留，
不能当作驾驶成功或失败。这个批次没有产生足够的固定实际位姿等曝光对照，因此不支持把「更大偏移」
的路径可用率与基线做因果比较。

## 2. Mountain 第二路段

入口同上；结果目录：`logs/experiments/e5_pose_sweep_mountain_20261011/`。
请求矩阵：anchor `(729.6,763.9,45°)`、goal `(616.2,894.5)`，横向 `{0,+0.5}` m × 航向 `{0,+5}`°，
其它配置与 Italy 扩展相同。

| pose 数量 | completed | qualified | unplaceable | 启动失败 |
|---:|---:|---:|---:|---:|
| 4 | 0 | 0 | 4 | 0 |

四个位姿均为 `placement_rc=3` / `placement deadline; no equal-exposure drive measurement`，没有进入等曝光
驾驶测量；这只能报告为「第二路段未获得放置」，不能读成第二路段的驾驶质量或安全结论。

## 3. 清理与复现

* 两批使用资格化 runner：request/session/result、实际放置位姿、退出码、资格原因与 owned cleanup 均保留；
* 所有 UNKNOWN 与失败原因原样保留；
* 收尾后 `game_pids() = set()`；
* 两批都不改模型、不放宽 strict、不倒车、不消费封存最终集、不新增人工标注。

## 4. 结论

E5 扩展已经**尝试完成**，但没有产生第二路段的合格驾驶证据：Italy 更大偏移批次有 2 个 qualified、2 个
exposure-invalid；Mountain 4/4 unplaceable。论文因此只写「扩展边界与失败原因」，不把这些结果包装成泛化或安全提升。

## 5. 固定实际位姿契约重跑（2026-10-11）

为消除旧批次的 `production_alignment` 歧义，使用 `pose_contract=fixed_actual_pose`、位置容差 0.10 m、航向容差 1° 重跑：

| 批次 | 请求数 | 结果 | 原因 |
|---|---:|---|---|
| Italy 更大偏移 | 4 | 4/4 `unplaceable` | `placement_rc=4`，生产放置位置漂移 2.57–3.08 m（固定实际位姿契约在曝光前拒绝） |
| Mountain 第二路段 | 4 | 4/4 `unplaceable` | `placement_rc=3`，放置截止，无等曝光驾驶测量 |

这次重跑没有把生产放置后的其它位置冒充请求位置；两批仍不提供等曝光驾驶因果证据。
结果目录：`logs/experiments/e5_pose_sweep_large_fixed_20261011/`、`logs/experiments/e5_pose_sweep_mountain_fixed_20261011/`。

## 6. 反锚定 fixed_actual_pose 重跑（2026-10-11）

为满足“至少一组 qualified 等曝光扩展位姿”，从此前唯一合格 baseline 的实际放置位姿反锚定：

* 请求 anchor：`(779.4392068, 734.5823346, -13.107691°)`；
* contract：`fixed_actual_pose`；位置容差 `0.10 m`，航向容差 `1°`；
* 其余配置：Italy / sensor / strict / `seg_model_hand` / 25 s / 6 m/s / `max_wall_s=150`。

结果：**1/1 completed、qualified=true**；`placement_rc=0`、`drive_started=true`、实际 drive elapsed `26.609 s`。
请求与实际放置偏差为：位置 `0.0215 m`、航向 `0.076°`，均在契约容差内；owned cleanup `closed=true`、
`unverified=[]`、`still_running=[]`。这是一组合格的等曝光固定实际位姿观察，但它是**反锚定的 baseline 重复**，
不是大偏移因果对照；大偏移与 mountain 的固定实际位姿批次仍分别为 4/4 rc=4 与 4/4 rc=3。
