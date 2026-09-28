# HubUserLogin 字段说明

这是一份 **魔灵召唤** 登录包（`HubUserLogin`）按字段拆开后的文件。文件名就是接口里的一级 key。

用 `python pyscript/sw_units.py split 某个.json` 拆包后，会得到同名目录，每个 `*.json` 对应一个 key。各号目录结构基本相同，个别 key 可能有缺（见文末）。

日常翻号最有用的是：`wizard_info`、`unit_list`、`runes`、`artifacts`、`inventory_info`、`deck_list`、`pvp_info`、`rtpvp_info`、`guild`。

登录包里**没有**完整召唤流水。`unit_list` 只有**现存**魔灵（喂掉、卖掉的不会出现），每只有 `create_time`（KST）和 `source`（来源）。

## 账号与会话

| 文件 | 含义 |
|---|---|
| `command` | 接口名，这里是 `HubUserLogin`（登录拉全量） |
| `ret_code` | 返回码，`0` 成功 |
| `wizard_id` | 角色 ID |
| `wizard_info` | 角色主数据：昵称、等级、魔力、水晶、能量、竞技场券等 |
| `wizard_skill_info` / `wizard_skill_list` | 召唤师技能（次元洞等） |
| `wizard_extra_data` | 角色附加数据 |
| `account_info` | 账号：Hive ID、设备、版本、国家 |
| `account_config_info` | 账号配置 |
| `session_key` / `session_key_node` | 会话密钥 |
| `webcash_info` | 网页商店点券 |
| `country` | 国家 |
| `reqid` | 请求 ID |
| `this_server_id` | 服务器 ID |
| `play_start_timestamp` | 本次登录开始时间 |
| `user_reference_date_info` | 账号基准日期（每日重置等相关） |
| `tvalue` / `ts_val` / `tvaluelocal` / `tzone` / `tzoffset` / `tvaluelocal_next_monday` | 服务器时间、时区 |

## 魔灵

| 文件 | 含义 |
|---|---|
| `unit_list` | 背包里的魔灵（最大一块数据之一） |
| `unit_collection` | 图鉴 |
| `unit_storage_normal_list` / `unit_storage_normal_slots` | 普通仓库及格子 |
| `unit_depository_slots` | 保管所格子 |
| `unit_marker_list` | 魔灵标记/标签 |
| `unit_state` | 魔灵状态 |
| `favorite_unit_list` | 收藏魔灵 |
| `lobby_proud_unit_id_list` | 大厅展示魔灵 |
| `wish_list` | 心愿单 |
| `draft_unit_list` | 征召/草稿池魔灵 |
| `worldboss_used_unit` | 世界首领已用魔灵 |

## 符文 / 神器 / 装备

| 文件 | 含义 |
|---|---|
| `runes` | 符文 |
| `rune_lock_list` | 锁定的符文 |
| `rune_craft_item_list` | 符文精工石、宝石 |
| `artifacts` | 神器 |
| `artifact_crafts` | 神器制作材料 |
| `relics` | 遗物 |
| `trans_item_list` | 附着在魔灵上的转换/升华类道具 |
| `equip_info_list` / `old_equip_info_list` | 新/旧装备数据 |
| `world_arena_rune_equip_list` / `world_arena_artifact_equip_list` | 世界竞技场符文/神器预设 |
| `world_arena_rune_equip_sync` / `world_arena_artifact_equip_sync` | 上述预设是否已同步 |

## 背包与商店

| 文件 | 含义 |
|---|---|
| `inventory_info` | 背包道具（卷轴、精髓等） |
| `inventory_open_info` | 已开格子 |
| `inventory_mail_info` | 邮箱附件 |
| `inventory_item_expire_list` | 限时道具 |
| `period_item_list` | 限时物品 |
| `shop_info` | 商店及购买冷却 |
| `shop_daily_bonus_list` | 每日商店奖励 |
| `shop_bonus_event` | 商店活动 |
| `item_cart_prev_reset_timestamp` / `item_cart_next_reset_timestamp` | 购物车刷新时间 |
| `costume_ticket_purchased_list` | 已买时装券 |

## 召唤

| 文件 | 含义 |
|---|---|
| `summon_special_info` | 特殊召唤（当前卡池，不是抽卡历史） |
| `summon_choices` | 自选召唤 / 祝福二选一 |
| `summon_custom_pool_info` | 自定义卡池 |
| `summon_beginner_pickup_info` | 新手 Pickup |
| `summon_pass_info` / `summon_pass_reward_list` | 召唤通行证 |
| `beginner_summon_free` | 新手免费召唤 |

## 建筑 / 岛屿

| 文件 | 含义 |
|---|---|
| `island_info` | 天空之岛 |
| `building_list` | 建筑 |
| `deco_list` | 装饰 |
| `obstacle_list` | 岛上障碍（石头等） |
| `object_state` | 岛上物件状态 |
| `object_storage_slots` / `object_storage_list` | 物件仓库格子 / 仓库内物件 |
| `markers` | 地图标记 |
| `mob_list` | 岛上生物/人造魔灵相关 |
| `mob_costume_equip_list` / `mob_costume_part_list` | 魔灵时装及部件 |
| `homunculus_skill_list` / `homunculus_skill_select_ratio_info` | 人造魔灵技能 |

## 编队

| 文件 | 含义 |
|---|---|
| `deck_list` | 保存的队伍 |
| `deck_recent_list` | 最近使用队伍 |
| `defense_deck_info` | 竞技场防守阵容 |
| `temporary_defense_deck` | 临时防守 |
| `raid_deck` | 团本队伍 |
| `battle_option_list` | 战斗选项 |

## 竞技场 / 世界竞技场

| 文件 | 含义 |
|---|---|
| `pvp_info` | 普通竞技场战绩、段位 |
| `arena_shutdown_info` | 竞技场维护 |
| `server_arena_defense_unit_list` / `server_arena_defense_deck_info` / `server_arena_schedule_info` | 服务器竞技场防守与赛程 |
| `rtpvp_info` | 世界竞技场（RTA）积分、体力、胜负 |
| `rtpvp_season_info` / `rtpvp_team_season_info` / `rtpvp_draft_season_info` | 赛季 / 组队赛季 / 征召赛季 |
| `rtpvp_contest_info` | 对抗赛 |
| `rtpvp_season_npc_list` / `rtpvp_selected_npc_list` | NPC 对手 |
| `rtpvp_contest_shop_display` / `rtpvp_web_link_display` | 商店展示、网页入口 |
| `rtpvp_reward_info` / `rtpvp_contest_reward` | 奖励 |

## 公会

| 文件 | 含义 |
|---|---|
| `guild` | 公会信息 |
| `guild_join_timer` | 入会冷却 |
| `guild_attend_info` | 公会签到 |
| `guildsiege_defense_unit_list` / `guildsiege_defense_deck_unit_list` / `guildsiege_defense_deck_equip_list` | 公会战防守 |

## 副本与活动

| 文件 | 含义 |
|---|---|
| `scenario_list` | 剧情副本进度 |
| `quest_active` / `quest_rewarded` | 进行中 / 已领任务 |
| `event_id_list` | 当前活动 ID |
| `dimension_hole_info` | 次元洞能量 |
| `raid_info_list` / `raid_best_clear_info_list` | 团本及最佳通关 |
| `worldboss_status` | 世界首领状态 |
| `my_worldboss_ranking` / `my_worldboss_prev_ranking` / `my_worldboss_best_ranking` / `my_worldboss_daily_battle_count` / `world_boss_best_rank_id` | 世界首领排名 |
| `scout_info` | 探索/迷宫进行中的一场（时长、回合、难度） |
| `summonerway_event_info` | 召唤师之路 |
| `quiz_reward_info` | 问答活动 |
| `contents_limit_list` | 内容限制 |
| `is_dungeon_open_check_user` | 是否参与副本开放校验 |

## 每日奖励 / 加成

| 文件 | 含义 |
|---|---|
| `daily_reward_info` / `daily_reward_list` / `daily_reward_checked` | 每日签到 |
| `daily_reward_inactive_status` | 回流每日奖励开关 |
| `daily_reward_new_user_status` | 新手每日奖励开关 |
| `daily_reward_special_status` | 特别每日奖励开关 |
| `daily_reward_special_event_status` | 特别活动每日奖励 |
| `daily_reward_special_pass_status` / `daily_reward_special_pass_info` | 特别通行证 |
| `daily_reward_unit_upgrade_info` | 每日强化相关 |
| `check_login_reward_interval` | 登录奖励检查间隔 |
| `new_user_buff` / `inactive_user_buff` | 新手 / 回流加成 |
| `reward_buff_info_list` | 奖励加成列表 |

## 社交

| 文件 | 含义 |
|---|---|
| `friend_list` | 好友 |
| `invite_buddy` / `invite_counter_list` | 邀请好友 |
| `helper_assist_info` | 助战 |
| `mentoring_info` / `mentor_slot_list` / `mentee_slot_list` | 师徒 |
| `emoticon_favorites` | 收藏表情 |

## 通知与屏蔽

| 文件 | 含义 |
|---|---|
| `notice_info` / `notice_popup_info_list` | 公告 / 弹窗 |
| `push_noti_status` / `push_noti_status_list` | 推送开关 |
| `costume_disable_list` | 禁用时装 |
| `mob_costume_disable_list` | 禁用魔灵时装 |
| `object_skin_disable_list` | 禁用物件皮肤 |
| `trans_item_disable_list` | 禁用转换道具 |
| `lobby_map_disable_list` | 禁用大厅地图 |
| `emoticon_disable_list` | 禁用表情 |

## 各号可能缺的 key

| 文件 | 说明 |
|---|---|
| `object_storage_list` | 物件仓库内容，有的号只有 `object_storage_slots` |
| `rtpvp_draft_season_info` | 世界竞技场征召赛季，未开时可能没有 |
| `user_reference_date_info` | 视客户端版本 |
