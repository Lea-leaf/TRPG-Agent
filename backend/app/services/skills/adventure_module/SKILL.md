# 冒险模组主持技能

当玩家行动涉及《凡戴尔的失落矿坑》的剧情事实、地点、NPC、线索、遭遇、宝藏或主线推进时，使用本技能。冒险节点是主持材料，不是玩家可见菜单；你仍然负责像 DM 一样判断行动是否合理、是否需要检定、是否触发战斗或是否只是叙事反馈。

## 入口工具

兼容入口仍是 `manage_adventure`。旧的 `inspect_adventure_state`、`load_adventure_node`、`search_adventure_nodes`、`switch_adventure_node`、`advance_adventure`、`reveal_adventure_clue`、`mark_adventure_event` 只保留给历史调用兼容。

## 动作速查

- 读取节点：`action="load_node"`，可选 `node_id`；不传则读取当前节点。
- 搜索节点：`action="search_nodes"`，传 `query`，可选 `limit`。
- 切换书签：`action="switch_node"`，传 `node_id`，可选 `reason`；它只改书签，不会把当前节点算作完成。
- 沿出口推进：`action="advance"`，传 `option_id`；它会完成当前节点再进入下一个节点。
- 收束节点：`action="resolve"`，传 `outcome`，可选 `clue_ids`、`event_ids`。
- 查看说明：`action="help"`。

## 使用流程

- 当前场景缺少事实依据时，先 `action="load_node"`。不要凭记忆补模组内容。
- 玩家意图指向别的地点、NPC、支线或秘密关键词时，先 `action="search_nodes"`，再按需要 `action="load_node"`。
- 工具返回的 `player_visible_intro` 可改写给玩家；`secrets`、`dm_guidance` 和未发现线索只作为主持依据，不要直接泄露。
- `available_exits` 表示硬出口是否满足；它不是唯一选择列表。合理绕行、调查、返回城镇、休整或角色扮演都可以自然处理。
- 搜索能查到后期和秘密节点，但搜索可见不等于玩家可达。未获得方向或线索时，不要直接切换；用叙事说明缺少路径，并引导玩家从当前线索调查。
- 玩家真实获得线索或完成稳定事件后，用 `action="resolve"` 收束当前节点并写入 `clue_ids`、`event_ids`；不要因为 NPC 提到目标、玩家打算去做或剧情可能发生就提前记录。
- 战斗、调查或谈判让当前节点告一段落后，先用 `action="resolve"` 收束当前节点；根据返回的 `recommended_action` 决定立刻 `advance`、询问玩家，或继续当前节点。
- 玩家进入已查到且合理可达的新场景时，用 `action="switch_node"` 更新书签；如果当前节点提供满足条件的硬出口，优先用 `action="advance"`。
- 玩家回到之前跳过或暂离的场景时，也用 `action="switch_node"` 更新书签；回访节点不该被标成“完成”，这样后续还能再回来。
- 节点奖励先进入待发放队列；领取时用 `claim_adventure_reward`，只允许领取 `pending_reward_grants` 里列出的 reward_id，重复领取同一个 id 不会重复结算。领取成功后，要用工具返回的 `message` 或 `result.description` 自然告诉玩家获得了什么奖励。

## 和其他系统配合

- 当前冒险开局若玩家已加载角色但 HUD 中还没有友方单位，应先创建一名战士友方同伴（`fighter_companion`），再继续推进模组。
- 节点里出现具体空间、房间、洞穴、道路、营地或可能战斗的位置时，按需使用 `manage_space` 建立地图并放置单位。
- 节点里出现遭遇时，先读取 `encounters` 和触发条件。玩家实际触发冲突后，再用战斗工具生成敌人并开战；战斗结束后不要直接自编后续路线，先 `action="resolve"` 回到冒险节点出口。
- 节点里的 XP 奖励会通过剧情奖励工具写入角色卡；财物、金币、道具先由剧情奖励工具标记为已领取并告知玩家，正式背包/金币写回等有对应状态字段后再接入。
- 节点里的奖励会先写进待发放队列，不要直接把它们当作已获得收益处理。
- 模组材料不足、怪物 slug 未结构化或规则细节缺失时，使用规则查询或现有战斗/怪物工具补足，不要在冒险工具里硬编规则。

## 完整性边界

当前数据已包含完整 PDF 候选节点和少量人工硬出口。它能支持一场“资料可查、书签可推进”的完整冒险主持，但后续地下城房间级路线主要依赖 `search_nodes` 与 `switch_node`，不是全自动图遍历。遇到细粒度房间探索时，按玩家自然行动检索并切换到对应节点。
