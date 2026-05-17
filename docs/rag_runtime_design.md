# RAG 运行时设计备忘

本文记录本项目规则书 RAG 的原设计、撤下原因，以及后续可探索的“方案 3：机会型并行 RAG”。当前结论是：规则书检索暂时只通过工具触发，主 agent 每轮输入不再自动塞入静态规则证据。

## 当前边界

- 规则数据源只使用中文三本核心书索引：PHB、DMG、MM。
- `consult_rules_handbook` 是当前唯一的规则书查询入口。
- 自动静态 RAG 已撤下：运行状态帧中不再自动出现 `[规则证据候选]`。
- 剧情节点事实、路径记忆、战斗状态、后台运行指令属于必需上下文，不能因为 RAG 优化而丢弃。
- 后续探索不得改动“序列帧残留清理”相关逻辑，避免旧运行状态帧再次泄漏给主 agent。

## 原设计

原先的自动 RAG 设计目标是：每轮用户输入后，系统先对规则书做召回与重排，只有高相关证据才塞入本轮 runtime state，降低模型不查工具也能回答规则问题的概率。

流程如下：

```text
用户输入
-> ContextAssembler 构建 runtime state
-> RuleEvidenceContextProvider 读取最近用户问题
-> 三本核心书索引召回候选
   - BM25
   - 向量检索
-> rerank 重排
-> 分数超过阈值则插入 [规则证据候选]
-> 主 LLM 调用
```

它的优点：

- 对明确规则问题，模型可能不需要再主动调用工具。
- 可以把 PHB/DMG/MM 的原文片段直接放入上下文。
- trace 中可以记录候选、分数、是否注入，便于分析命中质量。

它的问题：

- 当前实现是同步阻塞的。即使最后不注入，也要等检索和 rerank。
- 闲聊或纯剧情输入也可能付出无意义等待。
- 自动注入会增加上下文成本。
- 一旦证据和项目自身状态结算重叠，模型可能把规则原文当成额外行动指令，产生冗余结算。
- 如果为了提高命中再加入词表、标题兜底、正则分类，就会偏离语义检索目标，维护成本也会上升。

因此目前已撤下自动静态注入，只保留工具式检索。

## 召回率与命中质量

RAG 的召回率可以拆成两层：

- 候选召回率：BM25/向量阶段是否把正确片段放进候选池。
- 最终注入召回率：rerank 与阈值门控后，正确片段是否真的进入模型上下文。

例如“黑龙是怎样的怪物”曾出现过候选召回成功、最终注入失败：

```text
候选中有 MM 黑龙条目
rerank 分数低于阈值
最终不注入
```

这说明调度方案不能直接提升检索质量。要提升命中质量，应优先看：

- chunk 切分是否合理。
- 标题、页码、章节等 metadata 是否准确。
- embedding 模型是否适配中文规则书。
- rerank 模型是否适配中文长文和怪物条目。
- top_k 与阈值是否过保守。

## 方案 3：机会型并行 RAG

方案 3 的目标不是提升召回率，而是降低等待浪费。它把规则 RAG 视为机会型增强：赶上就塞入，赶不上就放弃本轮，不阻塞主模型太久。

核心原则：

```text
必需上下文：同步构建，永远不能丢
机会型上下文：限时等待，超时可丢
```

必需上下文包括：

- 当前运行状态帧。
- 当前战斗状态。
- 当前剧情节点事实。
- 冒险路径记忆。
- 后台运行指令。
- 当前工具返回与 pending action 信息。

机会型上下文只包括：

- 自动规则书 RAG 证据。

建议流程：

```text
用户输入
-> 启动规则 RAG 后台任务
-> 同步构建必需上下文
-> 必需上下文完成后，最多等待 RAG 一个短窗口
   -> RAG 已完成且高相关：附加规则证据
   -> RAG 未完成/失败/低相关：不附加
-> 发起主 LLM 请求
```

伪代码：

```python
async def _ainvoke_assistant(state, mode):
    query = latest_external_human_text(state["messages"])

    rag_task = None
    if query and mode == NARRATIVE_AGENT_MODE:
        rag_task = asyncio.create_task(
            asyncio.to_thread(evaluate_auto_rule_evidence, query)
        )

    required_context = assembler.assemble_required(
        state,
        mode,
        base_system_prompt=base_system_prompt,
    )

    optional_rule_context = ""
    if rag_task is not None:
        try:
            evaluation = await asyncio.wait_for(rag_task, timeout=0.8)
        except TimeoutError:
            evaluation = None

        if evaluation and evaluation.evidence:
            optional_rule_context = evaluation.evidence

    runtime_state_text = required_context.runtime_state_text
    if optional_rule_context:
        runtime_state_text += "\n\n[扩展上下文]\n" + optional_rule_context

    return await llm_service.ainvoke_with_tools(
        messages=[*required_context.model_input_messages, build_runtime_state_message(runtime_state_text)],
        tools=get_tool_profile(mode),
        system_prompt=required_context.system_prompt,
        mode=mode,
    )
```

## 关键实现约束

1. 不得把剧情节点上下文放入可超时丢弃分支。

剧情节点事实是主持当前场景的硬依赖，必须同步构建并稳定进入运行状态帧。

2. 不得让旧 RAG 证据进入历史残留。

机会型 RAG 只能作为本轮 runtime state 的短期附加块。后续如果实现，要确认旧运行状态帧不会被投影回主模型输入。

3. 不要用词表或正则做自动门控。

自动规则 RAG 的门控应以语义检索和 rerank 分数为主。少量结构化元数据可以用于展示、过滤明确工具参数，不能变成隐式分类规则。

4. 超时必须 fail closed。

RAG 超时、rerank 不可用、embedding 不可用时，不注入证据，不影响主流程。

5. trace 必须记录耗时。

如果探索方案 3，先补观测再调窗口：

```text
rule_auto_rag_started
rule_auto_rag_completed
rule_auto_rag_timed_out
duration_ms
candidate_count
top_scores
injected
reason
```

## 等待窗口取舍

窗口越短，越省等待，但本轮注入机会越低。

建议先观测真实耗时，再定默认值：

- 800ms：偏激进，适合 rerank 很快或主要目标是低延迟。
- 1500ms：折中，适合大多数在线 rerank。
- 2000ms：接近同步体验，延迟收益较小。

如果 p50 都超过 1500ms，方案 3 会明显降低本轮规则证据命中率。此时更应该优先优化 rerank 性能、缓存或工具触发策略。

## 探索顺序

1. 保持当前“只能工具检索”的行为不变。
2. 为工具检索补更完整的 trace：召回候选、rerank 耗时、最终返回片段。
3. 离线评估 PHB/DMG/MM 的召回质量，特别是怪物条目、法术通用规则、DMG 可选规则。
4. 设计 `RequiredContextProvider` 与 `OptionalContextProvider` 的清晰边界。
5. 在实验分支实现机会型 RAG，不接入默认运行路径。
6. 用 trace 对比同步、机会型、纯工具三种模式的延迟、命中率、成本和误注入率。

## 暂不做的事

- 不恢复每轮静态自动注入。
- 不用正则/词表做规则类型门控。
- 不改剧情节点序列帧。
- 不把 RAG 证据写进长期历史消息。
- 不让规则原文覆盖项目工具已经完成的状态结算。

