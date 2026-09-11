# 校园安全智能体实验文档入口

当前主线是：使用公开派生 Webshell 日志和 Task A，验证日志提示注入能否改变 DeepSeek 的事件分类或研判依据。慢路径、风险门控和工程扩展暂不推进。

## 每次工作只读这两份

1. [思路.md](思路.md)：长期研究问题、实验设计和阶段路线。该文件是研究主线，不随单次实验结果频繁改动。
2. [每次codex执行前必读prompt.md](每次codex执行前必读prompt.md)：当前阶段、已确认结论、不可变边界和结果入口。

只有需要具体证据时，才继续打开运行目录中的 `RESULTS.md`、`summary.json` 或原始 JSON。

## 按用途查阅

| 需求 | 入口 |
| --- | --- |
| 运行校园安全实验 | [实验包 README](agentdojo-0.1.35/examples/campus_security/README.md) |
| 理解 AgentDojo 扩展位置 | [ARCHITECTURE.md](agentdojo-0.1.35/examples/campus_security/ARCHITECTURE.md) |
| 核对公开派生数据 | [数据 README](dataset/campus_security_adapted/README.md) |
| 查看真实运行证据 | `agentdojo-0.1.35/runs/campus_security/` |
| 回看旧阶段 | `agentdojo-0.1.35/examples/campus_security/history/` |
| 阅读概念图解 | [思路_关键图解.md](思路_关键图解.md) |
| 使用文献速览提示词 | `prompts/文献速览提示词.md` |
| 填写最终指标表 | `templates/最终测试汇总表.md` |

## 不属于当前执行入口

- `2026年度教育网络安全专项研究课题/`：正式申请材料和历史版本，仅作课题档案。
- `dataset/log-interpretation-prompt-injection/`：上游公开数据仓库，只读来源。
- `agentdojo-0.1.35/docs/`：AgentDojo 上游说明，需要核对框架机制时再读。
- `.venv/`、`.uv-cache/`：运行环境和依赖缓存，不是研究文档。

历史记录可以保留，但不得用其中的“下一步”覆盖当前状态文档。

## 文档维护约束

1. 每份文档只承担一种职责；同一事实只在权威文档完整记录，其他位置只做摘要和链接。
2. 具体实验状态、最新结论和下一步只写入 `每次codex执行前必读prompt.md`；README 最多保留一句主线摘要，历史记录和 README 不得发布新的执行指令。
3. 当前状态采用替换式更新，不在末尾持续追加历史；旧细节进入对应运行目录或 `history/`。
4. 根目录 Markdown 只允许 `README.md`、`思路.md`、`思路_关键图解.md` 和 `每次codex执行前必读prompt.md`；新增文件须经用户明确同意。
5. 根目录 README 不超过60行，当前状态文档不超过100行，单份运行报告原则上不超过120行。
6. 模型回答全文只保存在 `raw/*.json`；运行报告不得连续复制大段模型原文。
7. 历史文档首屏必须标明“历史归档”或“已停用”，并指向当前状态入口。
8. `思路.md` 和 `2026年度教育网络安全专项研究课题/` 不参与自动移动、合并、删减或状态同步。
9. 新建文档前先判断能否更新现有权威文档；实验结束只更新 raw、对应 RESULTS 和当前状态摘要。
10. Codex 修改实验文档前后应运行 `python scripts/check_document_rules.py`；检查失败时只报告问题，不自动修复或删除文件。
