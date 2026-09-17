# TripPilot 架构设计

## 1. Qingtu 当前架构（代码事实）

### 1.1 请求主链路

```text
Next.js 表单
  → POST /api/v1/plan-itinerary
  → FastAPI 校验、会话与 Redis 限流
  → PostgreSQL Activity 查询 / 可选 pgvector RAG
  → build_itinerary
       ├─ CP-SAT 按天选择活动（USE_ORTOOLS=true）
       └─ 贪心算法排列日内顺序
  → OpenAI 或 stub 生成短叙述
  → Pydantic ItineraryResponse
  → React 卡片 + Google Maps 标记/折线
```

自然语言调整是另一条混合链路：LLM 解析 `RefinementIntent`，后端以数据库/Google Places 校验候选，再使用确定性 slot filling。`/agent-plan` 已实现最多 10 轮的 OpenAI tool-calling，但最终优化仍直接使用全部城市活动，搜索工具结果没有形成显式候选集；也没有独立 Critic/Replan 状态机。

### 1.2 现有能力盘点

| 能力 | 当前位置 | 实际功能 | 保留判断 | 后续处理与复用 |
|---|---|---|---|---|
| FastAPI | `backend/app/main.py`, `backend/app/api/*` | API v1、CORS、中间件、健康检查、规划/保存/分享/认证/调整/Agent/多城市端点 | 保留 | 路由按领域逐步拆分，保持现有端点兼容 |
| Pydantic 契约 | `backend/app/api/schemas.py` | 请求、行程、调整和 Agent trace 模型 | 保留 | 旧模型作为兼容 DTO；新增领域 DTO，避免单文件继续膨胀 |
| PostgreSQL/SQLAlchemy | `backend/app/db/session.py`, `models.py` | 城市、活动、用户、行程、评价、协作、航班、住宿、embedding | 保留 | 采用 Alembic 增量扩展；JSON 行程保留快照用途，不承担全部查询模型 |
| pgvector/RAG | `services/retrieval_service.py`, `embedding_service.py`, `scripts/*`, `alembic/...pgvector...py` | OpenAI embedding + cosine top-K；无 embedding/失败时回退城市全量 SQL | 保留并收敛 | 成为 Retrieval Engine 的一个召回器；补版本、来源和离线评估 |
| POI/activity retrieval | `api/routes.py`, `services/retrieval_service.py`, `services/places_service.py` | DB 全量/语义召回；调整时可查 Google Places 并按人气和邻近度重排 | 保留并重构边界 | 统一 `SearchProvider`/POI repository；Google 响应映射到供应商无关模型 |
| Redis | `core/cache.py`, `core/session.py`, `middleware/rate_limit.py`, `api/routes.py` | 可降级缓存、会话、请求及生成次数限制 | 保留 | 承担短 TTL 动态数据、幂等与运行状态；不作为事实主存储 |
| 评分 | `core/scoring.py` | 评分、类别、预算、时长、直线距离惩罚及解释 | 保留并拆分策略 | 复用为候选效用和解释基础；参数配置化并加入来源/偏好/绕路得分 |
| 贪心规划 | `core/optimizer.py` | 09:00–22:00 排程、简单 opening hours、预算偏好、去重、类别多样性 | 保留为 fallback | 维持稳定兜底；逐步通过统一 OptimizationRequest/Result 接口调用 |
| OR-Tools | `core/ortools_optimizer.py` | CP-SAT 选择“某活动在某天”，含预算、每日数量和 must-visit；日内仍贪心排序 | 保留并扩展 | 成为 Optimization Engine；先补正确性约束，再逐步加入路线维度 |
| 时间窗/opening hours | `db/models.py`, `core/optimizer.py` | 单一 `open_time/close_time`；仅检查开始时是否已开门 | 部分保留 | 新增按日期/星期多时段、最后入场和时区；要求整个活动区间可执行 |
| travel time/路线 | `core/scoring.py`, optimizer；前端 `GoogleItineraryMap.tsx` | Haversine 距离乘固定模式速度；地图折线为展示，不是路网矩阵 | 仅作 fallback | `MapProvider`/`TransportProvider` 提供矩阵；保留直线估算并标 `ESTIMATED` |
| budget | schemas、scoring、两个 optimizer | 活动基础费用和每日预算；OR-Tools 允许 20% 浮动 | 保留并增强 | 明确币种，拆分活动/交通/餐饮/住宿费用，硬软预算由请求指定 |
| travel pace | `EnergyLevel`, `get_activities_per_day` | relaxed/moderate/active 映射每日活动数 | 兼容保留，需替换内核 | API 兼容映射到 CHILL/BALANCED/EXPLORER；由 Physical Load 约束驱动 |
| itinerary generation | `api/routes.py`, optimizer、`llm/generator.py` | 召回→优化→叙述→结构化响应 | 保留 | 用 application service 编排四个 Engine；叙述不能修改事实字段 |
| refinement | `api/refinement.py`, `services/refinement_service.py` | LLM 意图解析、候选验证、Places fallback、确定性替换/增删 | 保留并迁移 | 演进为 Replanner 的早期实现，补全量 Critic 和计划版本 |
| Agent | `api/agent.py`, `services/agent_service.py` | 有界 tool-calling、trace、最终确定性 optimizer | 实验性保留 | 不作为默认主链路；先定义状态和 Critic，再评估 LangGraph |
| Frontend | `frontend/app/*`, Zustand、Tailwind | 单/多城市、详情、保存分享、认证、自然语言调整 | 保留 | 抽取共享 TS 类型和 API client；增加约束/来源/体力/变更差异视图 |
| Map | `GoogleMapsProvider.tsx`, `GoogleItineraryMap.tsx` | Google JS API 标记、InfoWindow、连接折线和方向链接 | UI 保留，边界需解耦 | 先抽象前端地图 adapter；中国场景增加高德实现 |
| Docker | 根 `docker-compose.yml`, 两个 Dockerfile | PostgreSQL、Redis、FastAPI、Next.js 本地编排；镜像有生产 stage | 保留 | PostgreSQL 镜像当前不保证预装 pgvector，需改用兼容镜像或扩展安装迁移 |

### 1.3 已识别限制

- OR-Tools 没有“一个活动跨所有天最多选择一次”的约束，也没有真实时间维度、路段矩阵、营业窗口或日总时长约束；约束求解后仍可能在贪心排序阶段丢掉已选活动。
- `is_activity_available` 只验证开始时刻，没有验证活动结束时刻、星期、闭馆日、最后入场或时区。
- 路程是 Haversine + 固定平均速度，不是道路、公交或实时交通时间；前端 Polyline 也不是实际路线。
- `ActivityEmbedding.embedding_vec` 在 ORM 声明为 JSON，而迁移实际建为 `vector(1536)`，类型意图不一致，查询依赖 raw SQL。
- 初始 `cities`/`activities` 建表没有对应 Alembic 基线迁移，`init_data.py` 依赖 `Base.metadata.create_all`，新环境的迁移可复现性不足。
- `SavedItinerary` 将完整输入输出保存为 JSON，适合版本快照，但不适合运行中状态、逐项来源和分析查询。
- Google Places 集成直接位于业务服务，价格由 price level 映射为固定估值，但输出没有统一 `VERIFIED/ESTIMATED` 标记。
- 前端多个页面重复声明同类 itinerary interface，并有页面直接 `fetch`，与 `app/lib/api.ts` 的类型形状存在漂移风险。
- SSE 路由 (`api/streaming.py`) 复用 `app.api.routes.validate_trip_preferences` 与 `retrieval_service`，没有调用 `_check_and_increment_generation_limit`，绕过每日生成次数限制；并且只支持单城市 (`len(city_ids) != 1` 即报错)。
- 同一产品存在 `/plan-itinerary` 单城市限制与独立 `/multi-city/*` 实现，模型和行为没有统一。
- 同步 SQLAlchemy session 与外部 async 调用混用，规模扩大后可能阻塞事件循环。
- LLM client、Places、地图和交通尚无统一可 Mock 的 Provider contract；Agent 端点缺少 API key 保护性 fallback。

## 2. TripPilot 目标架构

采用“模块化单体 + 明确端口”的渐进结构。现阶段不拆微服务；领域边界稳定、负载证明确有需要后再拆。

```text
Web / Mobile clients
        │
FastAPI Application Layer
        │
        ├── Preference Engine ── TravelerProfile / TripIntent / Memory
        ├── Retrieval Engine  ── POI repository + RAG + route corridor search
        ├── Optimization Engine ── candidate scoring + OR-Tools + fallback
        └── Agent Engine ── Planner → Tool Gateway → Optimizer → Critic → Replanner
                                      │
Provider Ports                         ├── MapProvider
  ├── SearchProvider                  ├── TransportProvider
  ├── WeatherProvider                 ├── CrowdProvider
  ├── BookingProvider                 └── LLMProvider
        │
Adapters: existing DB/RAG, Google, future Amap, mock adapters
        │
PostgreSQL + pgvector (facts/history) / Redis (ephemeral/live/cache)
```

依赖方向必须由业务指向协议，而不是指向供应商 SDK。核心 optimizer 只接收经过验证的 `OptimizationRequest`（候选、时间窗、travel matrix、成本、负载和硬软约束），不在求解过程中调用网络。

## 3. 核心领域契约

### 3.1 Provider 通用规则

每个 Provider 方法返回结构化结果，而非裸供应商 JSON：`data`、`source`、`observed_at`、`expires_at`、`confidence_kind`、`confidence_score` 和 `errors`。超时或限流返回可识别的降级结果；Mock adapter 使用相同协议。

建议的端口：

- `MapProvider.geocode()`、`route_matrix()`、`route_geometry()`；
- `TransportProvider.options()`、`last_service()`；
- `SearchProvider.search_pois()`、`get_poi_details()`；
- `WeatherProvider.forecast()`；
- `CrowdProvider.crowd_level()`、`queue_estimate()`；
- `BookingProvider.search()`、`check_price()`、`check_availability()`、`create_order()`、`cancel_order()`；
- `LLMProvider.extract_preferences()`、`classify_replan_intent()`、`explain_plan()`。

`create_order` 和 `cancel_order` 必须接收短期确认令牌；该令牌只能在展示最新价格/条件并由用户显式确认后签发。

### 3.2 Physical Load

首版使用可解释的归一化加权分数，而不是黑盒预测：

```text
load = walking_km*w1 + steps*w2 + standing_min*w3 + queue_min*w4
     + stairs*w5 + slope*w6 + heat*w7 + baggage*w8 + transfers*w9
     + early_start*w10 + late_return*w11
```

权重按 CHILL/BALANCED/EXPLORER 和 traveler profile 配置。每项保留原始量、估算方法与置信度；总分只用于比较和阈值判断。实测反馈进入版本化校准，不直接覆写历史计划。

### 3.3 Detour Cost

候选服务点 `p` 相对当前路段 `a→b` 的增量成本：

```text
detour_minutes = travel(a,p) + travel(p,b) - travel(a,b)
utility = user_match + rating_quality - detour - queue - price_penalty
```

交通时间来自 Provider 时为 `VERIFIED` 或 `ESTIMATED`（取决于来源语义），直线 fallback 必须标 `ESTIMATED`。餐厅还需满足餐时和营业窗口，不能仅按综合分排序。

## 4. 数据库扩展计划

所有变化使用独立 Alembic revision，先增后迁移、双读校验、最后才考虑停用旧字段。

| 表 | 关键字段/关系 | 用途与阶段 |
|---|---|---|
| `traveler_profiles` | user_id、party_type、party_size、age_bands、pace、walking/queue tolerance、fatigue、wake/return、taxi、lodging preferences、version | MVP |
| `traveler_interests` | profile_id、interest_type、weight、source | MVP，替代不可查询的大 JSON 偏好 |
| `poi_practical_info` | activity_id/provider_poi_id、hours、last_entry、duration、ticket、reservation、loads、accessibility、restroom、luggage、transport、indoor_ratio | MVP，允许逐项为空 |
| `data_evidence` | entity_type/id、field_name、value_json、source/provider、source_url、observed_at、expires_at、confidence_kind/score | MVP，字段级溯源 |
| `trip_plans` | user/session、profile_version、status、timezone、currency、current_version_id | MVP，稳定计划身份 |
| `trip_plan_versions` | plan_id、parent_version_id、trigger、input_snapshot、result_snapshot、created_at | MVP，生成/重排可回滚 |
| `trip_items` | version_id、activity_id/external_poi_id、day、start/end、locked/status、cost/duration、priority | MVP，可查询的行程项 |
| `trip_legs` | version_id、from/to item、mode、duration、cost、walk_distance、transfers、geometry_ref、evidence_id | MVP |
| `constraint_results` | version_id、code、severity、item_refs、details、resolution | MVP，Critic 输出 |
| `physical_load_results` | version_id/day、各分量、score、threshold、method_version | MVP |
| `provider_snapshots` | provider、request_hash、payload、observed/expires、status | V1，审计与短期复现；敏感字段需清洗 |
| `travel_events` | trip_id、event_type、time/location、payload、source | V1，Live Copilot 输入 |
| `traveler_feedback` | user/plan/item、rating、actual_cost/steps/queue、fatigue、notes | V1 |
| `luggage_options` | location/provider、hours、price、capacity/status、evidence | V1 |
| `booking_intents` | plan/item、provider、quote_snapshot、status、confirmation_token_expiry | V2，不保存支付凭据 |
| `agent_runs` / `tool_calls` | plan/version、state、model、tool、input/output摘要、latency、tokens、error | V1 评估与审计 |

`activities` 暂时保留。MVP 可先增加 `external_id`、`provider`、`canonical_place_id`、`timezone`、`updated_at`，实用字段进入独立表，避免在主表一次加入大量稀疏且更新频率不同的列。

## 5. API 扩展计划

保留现有 `/api/v1`。新契约优先在 `/api/v2` 下建设，避免破坏当前前端。

| API | 目的 | 阶段 |
|---|---|---|
| `GET/PUT /api/v2/profile` | 获取/版本化更新 traveler profile | MVP |
| `POST /api/v2/trips` | 创建规划上下文和收藏地点 | MVP |
| `POST /api/v2/trips/{id}/plans` | 生成一个新 plan version | MVP |
| `GET /api/v2/trips/{id}/plans/{version}` | 返回日程、路段、来源、负载和冲突 | MVP |
| `POST /api/v2/trips/{id}/plans/{version}/critic` | 可重复执行确定性约束检查 | MVP（内部也调用） |
| `POST /api/v2/trips/{id}/replans` | 以事件/约束创建候选版本，不自动覆盖 | V1 |
| `POST /api/v2/route-recommendations` | 基于 route legs 查询餐饮/休息等候选 | V1 |
| `GET /api/v2/pois/{id}/practical-info` | 实用信息及字段级证据 | MVP |
| `GET /api/v2/trips/{id}/transport-options` | 步行/公交/地铁/打车比较 | V1 |
| `POST /api/v2/trips/{id}/events` | Live Copilot 状态输入 | V1 |
| `POST /api/v2/booking-intents` | 创建非支付预订意图 | V2 |
| `POST /api/v2/booking-intents/{id}/confirm` | 显式确认后调用 provider | V2 |

所有写请求支持 idempotency key；计划响应包含 `version` 和 `based_on_version`，更新采用乐观并发控制。

## 6. Agent Workflow

```text
Intent/Input
  → Planner：生成结构化 PlanningSpec，声明目标、硬约束、软偏好、所需事实
  → Tool Gateway：只调用白名单 Provider，校验 schema、TTL、来源和错误
  → Retrieval：形成有出处的候选池
  → Optimizer：在冻结的数据快照上求解
  → Critic：独立重算冲突和质量指标
       ├─ 通过 → LLM 仅解释事实和取舍 → 候选计划版本
       └─ 未通过 → 结构化 RepairInstruction → Replanner
                         └─ 达到迭代/时间上限后返回最佳可行解及未解决冲突
```

Critic 至少输出 `TIME_CONFLICT`、`BUDGET_CONFLICT`、`OPENING_HOURS_CONFLICT`、`RESERVATION_CONFLICT`、`WEATHER_CONFLICT`、`PHYSICAL_LOAD_CONFLICT`、`TRANSPORT_CONFLICT`、`ROUTE_INEFFICIENCY`、`MEAL_TIME_CONFLICT`。每条含 severity、证据、涉及项目和机器可执行修复建议。

Agent 状态必须持有 plan version、完成/锁定项目、当前时间位置、数据快照版本、迭代次数和未解决冲突。默认最多 3 次 repair；不可行时不伪装为成功。

当前无需 LangGraph。先以普通 Python application service 和显式状态模型实现并测试；只有当分支、暂停恢复、持久化执行和人工确认显著复杂后再用 ADR 评估引入。

## 7. OR-Tools Constraint Model 扩展

### 7.1 先修正当前模型

1. 加入每个活动跨全程 `sum_day x[day,activity] <= 1`。
2. 将活动数量下限改为软约束或在候选不足时安全降级，避免整体 infeasible。
3. 将选中活动与可落地排序统一到一个结果契约；贪心阶段不得静默丢项。
4. 区分硬预算与软预算，不默认允许 20% 超支。
5. 为 infeasible、timeout 和 fallback 输出明确状态和诊断。

### 7.2 MVP 模型

- optional interval variables 表达活动开始、结束和游览时长；
- 按日期/星期的营业窗口、最后入场、预约固定窗；
- must/avoid、唯一访问、日边界、总时长、用餐窗口；
- currency-normalized 活动与交通预算；
- 每日 Physical Load 上限或超限惩罚；
- 从 provider 快照预先构建非对称 travel-time matrix；
- 目标函数组合用户匹配、优先级、评分、旅行时间、等待、费用、负载和未满足软约束。

### 7.3 V1/V2 模型

- V1：多交通模式、换乘/末班车、天气适配、route-aware stop insertion、行李物流、锁定已完成项目的滚动重规划。
- V2：拥挤/排队场景、预订库存、鲁棒时间缓冲、多成员偏好公平性和多目标 Pareto 方案。

避免一次构建巨型模型：先按天分配再做日内 routing，在 Critic 中做全局检查；只有数据质量和性能测试证明必要时才联合求解。

## 8. 运行与可观测性

- PostgreSQL 是事实、计划版本和审计的主存储；pgvector 是召回索引。
- Redis 只保存短期 provider cache、rate limit、idempotency、Agent checkpoint 和 live state。
- 指标按 provider、optimizer、critic code 和 plan version 记录延迟、fallback、错误率及 token。
- 日志不得写 API key、OAuth token、确认令牌或完整供应商敏感响应。
- Provider contract、Critic 和 optimization request 均需纯 Mock 测试；供应商 adapter 使用 contract/integration tests。
