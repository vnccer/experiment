# Campus Security 运行结果

本目录顶层只保留当前仍需直接查阅的正式结果。早期学习、冒烟和已结束阶段的原始记录收纳在 `archive/`；它们仍是历史证据，未被删除或改写。

## 命名规则

- 正式结果目录：`<purpose>_YYYYMMDD`，全部使用小写 `snake_case`。
- 同日同目的需要独立批次时：`<purpose>_YYYYMMDD_rNN`。
- 未指定 `--output-dir` 的临时运行：自动进入 `adhoc_YYYYMMDD/`。
- 不要把 JSON 直接写在本目录顶层。
- 正式目录优先保留 `plan.json`、`summary.json`、`RESULTS.md` 和 `raw/`；原始 JSON 不删除、不覆盖。

## 当前正式结果

- `identifier_control_20260912/`
- `prompt_trust_frame_ablation_20260913/`
- `upstream_original_webshell_strict_positive_control_20260913/`（20260910 阳性对照的跨日期重跑）
- `attack_validity_20260910/`
- `public_webshell_validity_20260910/`
- `webshell_mechanism_comparison_20260910/`
- `upstream_prompt_positive_control_20260910/`
- `upstream_original_webshell_strict_positive_control_20260910/`

结论及证据优先级以实验根目录的 `每次codex执行前必读prompt.md` 为准。
