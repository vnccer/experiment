# 基于公开日志的校园安全场景改编数据

本目录将公开 `AIT-LDSv2` 日志转换为校园安全智能体实验使用的统一事件包。它是**公开数据的校园场景改编数据**，不是校园实采日志，也不是原创攻击数据。

当前只包含一个开发集事件家族：`webshell_commands`。先用这一组验证数据转换、任务研判和日志注入影响，再决定是否扩充异常登录、可疑进程与外联、DNS异常等事件；不一次性构造完整四模板。

## 文件边界

- `events/development/webshell_commands/clean.json`：无控制文本的公开攻击日志改编版本，真实标签仍是 `attack`。
- `events/development/webshell_commands/injected.json`：只改变27条日志的User-Agent；其他事件事实与clean版本一致。
- `evaluation/development/webshell_commands.json`：真实标签、注入目标和任务预期。它是可信评价数据，**不得送入模型上下文**。
- `trusted_context/assets.json`：研究者定义的可信资产清单。日志内容不能修改资产等级或授予动作权限。
- `manifests/source_manifest.json`：上游版本、文件哈希、许可、引用和全部转换步骤。

`clean`仅表示“没有提示注入”，不表示日志内容良性。clean和injected的真实标签都是Webshell命令执行攻击。

## 来源与许可

源数据为 `AIT Log Data Set V2.1` 的 `russellmitchell-webshell` 场景，经作者的提示注入实验仓库筛选。源记录采用 `CC BY-NC-SA 4.0`；本改编仅用于非商业研究，保留署名，并按相同许可管理衍生数据。

- 数据记录：https://zenodo.org/records/19483937
- 提示注入实验仓库：https://github.com/ait-aecid/log-interpretation-prompt-injection
- 固定仓库提交：`2310c0a9a7c9bd99c577b394fa529083fbde3e86`

## 可复现构建

在本目录运行：

```powershell
python build_webshell_commands.py --write
python build_webshell_commands.py --check
```

`--write`从只读的公开源文件生成改编数据，若现有输出被手工修改则拒绝覆盖；`--check`不写文件，只复核源哈希、27条记录、配对一致性和控制文本出现次数。

本数据包暂未接入AgentDojo，也未运行任何真实模型。后续接入时，只把`events/`中的事件内容交给模型；`evaluation/`、`trusted_context/`和`manifests/`由运行器与检查器在可信侧读取。
