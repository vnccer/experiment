# AgentDojo 0.1.35 扩展机制核对

## 原生入口和运行过程

以无注入任务为例：

```text
agentdojo.scripts.benchmark.main / benchmark_suite
  → AgentPipeline.from_config
  → benchmark_suite_without_injections
  → run_task_without_injection_tasks
  → TaskSuite.run_task_with_pipeline
      load_and_inject_default_environment
      user_task.init_environment
      deep-copy pre_environment
      FunctionsRuntime(suite.tools)
      agent_pipeline.query(task.PROMPT, runtime, task_environment)
        SystemMessage → InitQuery → LLM.query
        ToolsExecutionLoop([ToolsExecutor, LLM])
          ToolsExecutor.query
            FunctionsRuntime.run_function
              lookup function
              _execute_nested_calls
              Pydantic parameters.model_validate
              Depends.extract_dep_from_env
              Function.__call__ → Python tool function
            append ChatToolResultMessage
          LLM.query (repeat while assistant has tool_calls)
      model_output_from_messages / functions_stack_trace_from_messages
      _check_task_result → _check_user_task_utility
        utility_from_traces (if implemented), otherwise utility
```

`security=True` 在无注入运行时是框架默认返回值，不是已验证所有响应安全。本实验使用自己的拒绝记录和实际沙箱状态。

`functions_stack_trace_from_messages` 收集assistant提出的调用，也包含被拒绝的调用，不能直接当作执行轨迹。另一个版本细节是suite在末条content为None时可重试pipeline，且复用当前状态。本包的 `CampusPipeline` 在循环结束仍有待执行调用时抛出独立 `IterationLimitError`，runner将它记为上限失败，从而防止suite重启同一回合并混合状态。该行为有针对content=None的回归测试。

## 定义与注册

- 推荐按仓库 `examples/counter_benchmark` 示例新增 `examples/campus_security`，不放进 `src/agentdojo/default_suites`。从根目录以 `python -m examples.campus_security.run` 启动，避免依赖当前路径下的裸模块导入。
- environment继承 `TaskEnvironment`，字段使用Pydantic模型。工具使用 `Annotated[Sandbox, Depends('sandbox')]` 注入内部状态；该参数不加入模型工具schema。
- 工具为带类型注解和reStructuredText参数文档的普通Python函数，`make_function` 生成schema、描述、依赖与可执行引用。
- `TaskSuite(name, environment_type, tools, data_path)` 绑定环境与工具。数据目录用相对 `__file__` 的路径，支持不同工作目录下的加载。
- task继承 `BaseUserTask`。类名必须是 `UserTask0`、`UserTask1` 等数字后缀，装饰器自动分配 `user_task_0` / `user_task_1`。
- `PROMPT` 是可信用户任务，`init_environment` 安装该任务的权限并重置状态；`ground_truth` 是仅用于检查的正确工具序列；`utility` 独立比较报告和结果状态。
- `register_suite(task_suite, 'campus_security')` 注册单独benchmark版本；原CLI通过 `-ml examples.campus_security.benchmark` 加载注册模块。

## ToolsExecutor 前后数据

所有pipeline组件都传递并返回五元组：

```python
(query: str, runtime: FunctionsRuntime, env: TaskEnvironment,
 messages: Sequence[ChatMessage], extra_args: dict)
```

执行前，末条是：

```python
{
    'role': 'assistant',
    'content': None,  # 或文本块列表
    'tool_calls': [FunctionCall(
        function='block_ip', args={'ip': '192.0.2.10'}, id='call_3'
    )]
}
```

执行后保留原消息，按调用顺序追加：

```python
{
    'role': 'tool',
    'tool_call': original_function_call,
    'tool_call_id': 'call_3',
    'content': [{'type': 'text', 'content': 'serialized result'}],
    'error': None  # 或拒绝/执行错误字符串
}
```

`env` 是共享的可变内存状态；消息历史记录结果，不能替代状态判定。原生executor会尝试把看似列表的字符串用 `literal_eval` 转成列表，并跳过未知工具的runtime执行；原生runtime还会执行嵌套调用，Pydantic默认也可能忽略额外参数。

因此本包的 `CheckedToolsExecutor` 是独立子类，只重写分派部分，保留原生消息协议：每个提议都交给 `CampusRuntime`，先记录原始参数，再严格校验、检查授权和执行，最后形成与原框架兼容的tool结果。工具函数在状态写入前也调用同一个 `authorize`，防止使用普通runtime时绕过基本权限。

## 未来门控位置

```text
LLM生成候选调用
 → [未来gate / 可选slow path]
 → CheckedToolsExecutor
 → CampusRuntime严格参数检查及最终authorize
 → 工具写入内存状态
 → tool结果消息
 → 下一轮LLM或结束
```

扩展 `build_pipeline` 中的执行循环即可，不需要修改原 `ToolsExecutor`。门控可以查看待执行的assistant.tool_calls、可信任务配置与当前状态；它不能改权限，也不能提前执行工具。改写/拒绝调用时必须保留可追踪的原提议和每个call ID对应的tool结果，避免破坏后续模型协议。

## 保持核心不变的兼容处理

原 `TaskSuite.check` 在检查可注入性时直接调用 `GroundTruthPipeline.query`，没有运行 `init_environment`，并且关闭可注入性检查也会走到这次调用。为避免赋予默认权限，本包用 `CampusSuite.check` 为当前无注入任务执行task-aware ground truth检查，内部仍调用原 `run_task_with_pipeline` 和evaluator。它只支持当前utility-only范围；要求注入检查时会明确返回未支持。

原项目 `src/`、`tests/` 中的Python源码及 `pyproject.toml`、`uv.lock` 合计112个文件，在本次实现前后内容哈希一致；没有修改核心源码或原依赖配置。
