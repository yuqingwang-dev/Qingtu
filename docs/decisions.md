# TripPilot 架构决策记录

本文件采用轻量 ADR 格式。状态为 Accepted 的决策约束后续实现；变更时新增 ADR，不静默改写历史原因。

## ADR-001：保留 OR-Tools，采用确定性优化内核

- 状态：Accepted
- 决策：保留 CP-SAT，并将其逐步扩展为 Optimization Engine；贪心算法保留为 fallback。
- 原因：时间窗、预算、唯一访问、预约和体力属于可验证约束。OR-Tools 能输出可行/不可行状态，便于测试和解释。
- 代价：需要严谨建模、整数缩放、求解时间上限和 fallback；不能把当前简化实现宣传为完整路由优化。

## ADR-002：路线规划不全部依赖 LLM

- 状态：Accepted
- 决策：LLM 只抽取意图、提出高层策略和解释结果；坐标、路程、营业、预算和排程由 Provider、规则与 optimizer 负责。
- 原因：LLM 输出不可保证约束满足、可重复性、数值正确性或实时性。
- 代价：需要维护结构化契约和更多确定性测试，但可显著降低幻觉与不可执行计划。

## ADR-003：使用 Provider Abstraction

- 状态：Accepted
- 决策：Map、Search、Transport、Weather、Crowd、Booking、LLM 均通过供应商无关端口访问。
- 原因：中国场景需要高德；单一供应商可能受覆盖、价格、配额和故障影响；测试也需要 Mock。
- 代价：adapter 要处理能力差异，不能以“最小公分母”抹掉供应商特性；通过 capability metadata 暴露差异。

## ADR-004：建立独立 Critic

- 状态：Accepted
- 决策：优化结果必须由不依赖 Planner 自述的确定性 Critic 重算关键约束。
- 原因：求解输入可能缺失、adapter 可降级、后处理可能破坏可行性；独立复核才能形成可观察的 Planner→Optimize→Critic→Replan 闭环。
- 代价：部分逻辑看似重复，但 Critic 的职责是验证最终产物，必须能单独运行并返回 typed conflicts。

## ADR-005：Travel Pace 由 Physical Load 驱动

- 状态：Accepted
- 决策：CHILL/BALANCED/EXPLORER 不再简单映射活动数量，而映射可配置的每日负载阈值和权重。
- 原因：两个活动也可能包含长距离步行和排队；多个相邻、短时活动可能更轻松。
- 代价：首版分数需要估算和校准，因此必须展示组成项、方法版本和置信度。

## ADR-006：餐饮与服务点必须 route-aware

- 状态：Accepted
- 决策：餐厅、咖啡、购物、伴手礼、休息点和厕所根据具体行程路段召回，并以 Detour Cost、时间窗、排队、价格和匹配度排序。
- 原因：脱离路线的高评分推荐会增加不可接受的绕路；用户需要的是行程中的合适插入点。
- 代价：依赖路网矩阵/走廊检索，缓存策略和 API 成本需控制。

## ADR-007：字段级来源和三态可信度

- 状态：Accepted
- 决策：实用字段记录 evidence，并区分 VERIFIED、ESTIMATED、AI_SUGGESTION；未知不补值。
- 原因：同一 POI 的坐标、营业、排队和价格可能来自不同时间、不同来源，实体级单一 `source` 不足以审计。
- 代价：存储和响应更复杂，需要 TTL 和冲突来源选择规则。

## ADR-008：先模块化单体，不立即引入 LangGraph 或微服务

- 状态：Accepted
- 决策：先在当前 FastAPI 应用内建立领域模块、端口和显式 Agent state machine。
- 原因：当前规模和工作流不足以证明分布式复杂度；普通 Python 更容易调试、测试和回滚。
- 复审触发：需要持久化暂停/恢复、多个人工确认点、复杂并行分支，且自有状态机维护成本已被量化。

## ADR-009：版本化计划，不原地覆盖

- 状态：Accepted
- 决策：生成与动态重排创建 `trip_plan_versions`，记录 parent、trigger、input snapshot 和 conflict results。
- 原因：Live Copilot 必须能展示差异、拒绝候选、处理并发并回滚。
- 代价：需要版本清理和投影逻辑；当前 SavedItinerary JSON 继续作为 v1 快照兼容层。

## ADR-010：Booking 强制 Human-in-the-loop

- 状态：Accepted
- 决策：Agent 只能创建 booking intent。真实下单/取消前重新检查价格和库存，并要求短期、一次性用户确认。
- 原因：支付、实名、取消条款和价格变化具有高风险，不能由模型自行授权。
- 代价：流程多一步；需明确状态机、审计日志和幂等处理。

## ADR-011：动态信息与静态知识分离

- 状态：Accepted
- 决策：动态数据以 provider snapshot + TTL 管理；静态 POI 内容进入 catalog/evidence。优化使用冻结快照。
- 原因：天气、交通、排队、价格的新鲜度远短于描述、标签；混存会造成陈旧信息和不可复现决策。
- 代价：需要刷新策略和失效处理，但能够解释“当时为何这样规划”。

## ADR-012：契约层与 API/ORM 分层（app/contracts + app/providers）

- 状态：Accepted
- 决策：TripPilot 新增独立的 `app/contracts`（Pydantic 领域契约）和 `app/providers`（端口与适配器）包，不混入 `app/api/schemas`（API DTO）或 `app/db/models`（SQLAlchemy ORM）。
- 原因：Provider 通用返回契约（`ProviderResult`、`Evidence`、`ConfidenceKind`）是 Retrieval/Optimization/Agent/Critic 共用的稳定边界，独立于 HTTP 层和持久层才便于跨引擎复用、Mock 和 contract test；混入 schemas 会把 API 版本耦合进领域契约。
- 代价：多两个包，需约束未来不把 ORM/HTTP 概念反向引入 contracts 层。

## ADR-013：Phase 1.1 范围与 init_data.create_all 暂缓处理

- 状态：Accepted
- 决策：Phase 1.1 只交付供应商无关契约（`ConfidenceKind`/`Evidence`/`PoiPracticalInfo`/`ProviderResult`）、`SearchProvider` 端口、`MockSearchProvider`、非破坏性 `GoogleSearchAdapter` 和基线测试；不修改 optimizer、v1 路由、places_service 及其调用方。
- 原因：满足“每个重要修改可单独测试和回滚”“不修改稳定工作的核心逻辑”；契约+Mock+测试是后续所有实时数据与 Critic 的最小公共基础。
- 暂缓问题：`app/db/init_data.py` 调用 `Base.metadata.create_all()`，在空库上先于 Alembic 建表会破坏 `alembic upgrade head` 的可复现性（且 `activity_embeddings` ORM 声明为 JSON 而迁移为 `vector(1536)`，是有意兼容）。本期仅以静态基线测试覆盖 ORM↔迁移漂移，并在 `test_schema_baseline.py` 提供 Postgres+pgvector 真实 `upgrade head` 集成测试（`RUN_SCHEMA_BASELINE=1` 触发）；`init_data.create_all` 的修正推迟到独立迁移单元，避免触碰当前稳定流程。
- 代价：基线测试不能在 sqlite 上跑真实迁移（迁移含 `server_default=now()` 与 `CREATE EXTENSION vector` 等 Postgres 专属 DDL），故 always-on 检查采用静态解析。

## ADR-014：SearchProvider 适配器为非破坏性、feature flag 默认关闭

- 状态：Accepted
- 决策：`GoogleSearchAdapter` 仅“包装”现有 `places_service.fetch_real_venues`，把原始 venue dict 映射为 `ProviderResult[list[PoiPracticalInfo]]`；不修改 `places_service.py` 与其唯一调用方 `refinement_service.py`。默认 `USE_PROVIDER_ADAPTER=False`，运行时不接入任何路径。
- 原因：保证 Qingtu 现有主流程零行为变化、可回滚（删除两个包即可）；同时证明 SearchProvider 契约可被真实供应商实现满足。Google 不返回的实用字段（营业/末班/排队/预约/厕所等）一律保持 `None`，绝不伪造（ADR-007）。
- 代价：真实切换到 adapter 由 v2 路径在 M2 通过 feature flag 完成，本期不产生运行时收益。
