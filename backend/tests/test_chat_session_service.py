import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.services.chat_session_service import ChatSessionService


async def _noop_touch_chat_session(**kwargs):
    return None


def _noop_trace(*args, **kwargs):
    return None


class FakeGraph:
    def __init__(self, result: dict):
        self.result = result
        self.last_input = None
        self.last_config = None
        self.values = {"messages": []}
        self.tasks = []
        self.state_updates = []

    async def ainvoke(self, graph_input, config):
        self.last_input = graph_input
        self.last_config = config
        self.values = self.result
        return self.result

    async def aget_state(self, config):
        self.last_config = config
        return SimpleNamespace(values=self.values, tasks=self.tasks)

    async def aupdate_state(self, config, values):
        self.last_config = config
        self.state_updates.append(values)
        self.values = {**self.values, **values}


class ChatSessionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._touch_session_patcher = patch(
            "app.services.chat_session_service.touch_chat_session",
            side_effect=_noop_touch_chat_session,
        )
        self._trace_request_patcher = patch(
            "app.services.chat_session_service.trace_chat_request",
            side_effect=_noop_trace,
        )
        self._trace_result_patcher = patch(
            "app.services.chat_session_service.trace_chat_result",
            side_effect=_noop_trace,
        )
        self._trace_error_patcher = patch(
            "app.services.chat_session_service.trace_chat_error",
            side_effect=_noop_trace,
        )
        self._touch_session_patcher.start()
        self._trace_request_patcher.start()
        self._trace_result_patcher.start()
        self._trace_error_patcher.start()

    async def asyncTearDown(self):
        self._trace_error_patcher.stop()
        self._trace_result_patcher.stop()
        self._trace_request_patcher.stop()
        self._touch_session_patcher.stop()

    async def test_process_turn_returns_last_non_tool_ai_message(self):
        graph = FakeGraph(
            {
                "messages": [
                    AIMessage(content="", tool_calls=[{"name": "mock_lookup", "args": {"query": "beijing"}, "id": "call_1"}]),
                    AIMessage(content="查询完成。", tool_calls=[]),
                ]
            }
        )
        service = ChatSessionService(graph=graph)

        result = await service.process_turn(message="查一下北京", session_id="s1")

        self.assertEqual("查询完成。", result["reply"])
        self.assertEqual("s1", result["session_id"])
        self.assertIsNone(result["plan"])
        self.assertEqual("s1", graph.last_config["configurable"]["thread_id"])
        self.assertEqual(80, graph.last_config["recursion_limit"])
        self.assertEqual("查一下北京", graph.last_input["messages"][0].content)

    async def test_process_turn_clears_hot_episodic_context_before_graph_run(self):
        graph = FakeGraph({"messages": [AIMessage(content="继续推进。", tool_calls=[])]})
        graph.values = {
            "messages": [],
            "episodic_context": ["旧热摘要不应继续注入。"],
        }
        service = ChatSessionService(graph=graph)

        result = await service.process_turn(message="继续", session_id="episodic-demo")

        self.assertEqual("继续推进。", result["reply"])
        self.assertEqual("episodic-demo", graph.state_updates[0]["session_id"])
        self.assertEqual([], graph.state_updates[0]["episodic_context"])

    async def test_process_turn_generates_session_id_when_missing(self):
        graph = FakeGraph({"messages": [AIMessage(content="ok", tool_calls=[])]})
        service = ChatSessionService(graph=graph)

        result = await service.process_turn(message="hello")

        UUID(result["session_id"])
        self.assertEqual(result["session_id"], graph.last_config["configurable"]["thread_id"])

    @patch("app.services.chat_session_service.trace_chat_result")
    @patch("app.services.chat_session_service.trace_chat_request")
    async def test_process_turn_records_trace_events(self, mock_trace_request, mock_trace_result):
        graph = FakeGraph({"messages": [AIMessage(content="继续推进。", tool_calls=[])]})
        service = ChatSessionService(graph=graph)

        result = await service.process_turn(message="继续", session_id="trace-demo")

        self.assertEqual("继续推进。", result["reply"])
        mock_trace_request.assert_called_once()
        mock_trace_result.assert_called_once()
        self.assertEqual("trace-demo", mock_trace_request.call_args.args[0])
        self.assertEqual("trace-demo", mock_trace_result.call_args.args[0])

    async def test_get_history_keeps_original_transcript_without_tool_placeholders(self):
        graph = FakeGraph({"messages": []})
        graph.values = {
            "messages": [
                HumanMessage(content="我攻击哥布林"),
                AIMessage(content="", tool_calls=[{"name": "attack_action", "args": {"attacker_id": "player_hero"}, "id": "call_1"}]),
                ToolMessage(content="Goblin 使用 [Scimitar] 攻击 英雄!\n英雄 HP: 18 → 13", tool_call_id="call_1", name="attack_action"),
                HumanMessage(content="[系统:怪物行动]\n你放弃了反应。"),
                AIMessage(content="哥布林被你逼退了半步。", tool_calls=[]),
            ]
        }
        service = ChatSessionService(graph=graph)

        history = await service.get_history(session_id="demo", limit=10)

        self.assertEqual(
            [
                {"role": "user", "content": "我攻击哥布林"},
                {"role": "assistant", "content": "哥布林被你逼退了半步。"},
            ],
            history["messages"],
        )
        self.assertFalse(any("[工具:" in item["content"] for item in history["messages"]))
        self.assertFalse(any("状态快照" in item["content"] for item in history["messages"]))

    async def test_get_history_keeps_ai_text_that_also_triggered_tools(self):
        graph = FakeGraph({"messages": []})
        graph.values = {
            "messages": [
                HumanMessage(content="继续战斗"),
                AIMessage(
                    content="战斗开始！让我先为哥布林1执行攻击。",
                    tool_calls=[{"name": "attack_action", "args": {"attacker_id": "goblin_1"}, "id": "call_1"}],
                ),
                ToolMessage(content="Goblin 1 使用 [Scimitar] 攻击 预设-法师!\n未命中！", tool_call_id="call_1"),
                AIMessage(
                    content="哥布林1失手了，现在轮到哥布林2行动。",
                    tool_calls=[{"name": "next_turn", "args": {}, "id": "call_2"}],
                ),
            ]
        }
        service = ChatSessionService(graph=graph)

        history = await service.get_history(session_id="demo", limit=10)

        self.assertEqual(
            [
                {"role": "user", "content": "继续战斗"},
                {"role": "assistant", "content": "战斗开始！让我先为哥布林1执行攻击。"},
                {"role": "assistant", "content": "哥布林1失手了，现在轮到哥布林2行动。"},
            ],
            history["messages"],
        )


if __name__ == "__main__":
    unittest.main()
