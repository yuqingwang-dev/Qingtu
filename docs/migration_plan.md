# Qingtu → TripPilot 迁移计划

## 1. 迁移策略

采用 Strangler 式渐进迁移：保留 Qingtu `/api/v1` 及当前前端体验，在旁边建立稳定领域契约，通过 adapter 复用旧实现。每一步独立迁移、独立测试、可通过配置切回旧路径。

Phase 0 只交付文档，不修改运行时代码、数据库和依赖。

## 2. Migration Map

| Qingtu 资产 | TripPilot 归属 | 动作 |
|---|---|---|
| `TripPreferences` / energy level | Preference Engine | 保持 v1 DTO；映射到 versioned TravelerProfile + TripIntent |
| Activity/City SQLAlchemy models | POI catalog | 保留表和 ID；增量补 canonical identity、时区和证据关系 |
| `retrieval_service.py` + pgvector | Retrieval Engine | 作为 semantic retriever adapter，保留 SQL fallback |
| `places_service.py` | SearchProvider adapter | 抽出 Google 实现，供应商 JSON 不越过 adapter |
| `scoring.py` | Candidate scoring / Detour scoring | 保留基础函数；拆为配置化、可解释策略 |
| `optimizer.py` | Optimization fallback | 保留稳定贪心路径，接入统一 request/result |
| `ortools_optimizer.py` | Optimization Engine | 保留 CP-SAT 技术，按正确性→时间窗→路线→体力扩展 |
| energy/activity count | Physical Load Engine | 保留兼容映射，逐步由可解释负载模型取代 |
| refinement service | Replanner | 复用结构化意图和确定性执行思想，改为版本化重排 |
| agent service | Agent Engine prototype | 保留实验端点；工具改走 gateway，增加 Critic 和状态模型 |
| LLM client/generator | LLMProvider + Explanation | stub 行为保留；禁止叙述写回事实字段 |
| Redis cache/session/rate limits | Runtime/cache | 原样保留，扩展 TTL 快照、幂等和 checkpoint 命名空间 |
| SavedItinerary JSON | Plan snapshot | 保持兼容读取；新计划写入 versioned tables 并可投影为旧响应 |
| Next.js/Tailwind/Zustand | TripPilot Web | 保留技术栈；先抽共享类型/API，再加入新页面状态 |
| Google map components | Map UI adapter | 现有实现保留；定义中立 view model 后增加 Amap adapter |
| Docker Compose | Local platform | 保留服务边界；修正 pgvector 镜像/迁移基线后再扩展 |

## 3. 可独立回滚的迁移单元

### M1：事实与契约基线

- 补齐当前数据库基线迁移和架构测试；不改业务查询。
- 新增供应商无关的 evidence、POI practical info Pydantic 契约。
- 回滚：删除新增 revision/模块；旧表和 `/api/v1` 不变。

> 进度（Phase 1.1，已完成）：
> - `app/contracts`：`ConfidenceKind`/`Evidence`/`ProviderError`/`ProviderResult[T]`/`PoiPracticalInfo`/`PoiSearchQuery` 已落地。
> - `app/providers`：`SearchProvider` Protocol、`MockSearchProvider`、非破坏性 `GoogleSearchAdapter`（包装 `places_service`，`USE_PROVIDER_ADAPTER=False` 默认关闭）。
> - 基线测试：静态 ORM↔迁移漂移检查（always-on）+ Postgres+pgvector 真实 `upgrade head` 集成测试（`RUN_SCHEMA_BASELINE=1`）。确认 9 张 ORM 表均有迁移。
> - 未完成 / 推迟：`init_data.create_all` 与 Alembic 的冲突修正推迟到独立单元（见 ADR-013）；Google adapter 真实接入 v2 路径属于 M2。

### M2：Provider ports

- 定义 Map/Search/Transport/Weather/Crowd/Booking/LLM protocol。
- 将现有 Places 和 LLM 包在 adapter 后；保留旧调用配置开关。
- 每个 port 提供 mock 和 contract test。
- 回滚：关闭新 adapter feature flag，恢复原服务调用。

### M3：Profile 与 Physical Load vertical slice

- 新增 profile、load result 表及 `/api/v2/profile`。
- 对现有 itinerary 进行只读负载计算，不改变排程。
- 回滚：停止 v2 路由；v1 无感。

### M4：Optimization contract + Critic

- 把当前 greedy/CP-SAT 包装为统一 OptimizationProvider。
- 先实现纯确定性 Critic，对 v1 输出 shadow-check 并记录差异。
- 达到阈值后才允许 Critic 阻止 v2 计划发布。
- 回滚：关闭 shadow/enforcement flag，旧优化器继续工作。

### M5：时间窗和路网矩阵

- 以 provider 快照构造矩阵；扩展 OR-Tools 时间维度。
- 与当前估时并行计算，验证性能、可行率和行程差异。
- 回滚：回到 Haversine fallback，响应标明 `ESTIMATED`。

### M6：Versioned planning / Replanning

- 创建 trip plan/version/item/leg/event 表。
- refinement 通过 adapter 产生新版本，不原地覆盖。
- 回滚：保留新表但停止写入，v1 SavedItinerary 继续可用。

### M7：route-aware 与 Live Copilot

- 实现 route corridor 检索、Detour Cost、餐时/休息插入。
- Live event 只重排剩余未锁定项目，并经 Critic 验证。

### M8：Booking

- 先实现 MockBookingProvider 和确认令牌状态机。
- 真实 provider 必须单独安全评审，Agent 无权跳过确认。

## 4. 数据迁移顺序

1. 建立可复现的 schema baseline，验证空库 `alembic upgrade head`。
2. 仅新增表/nullable 字段和索引；不重命名/删除旧字段。
3. 从 `SavedItinerary.trip_data` 回填 profile/intent，从 `itinerary_data` 回填 plan snapshot；记录失败项。
4. 双写新旧存储，比较读模型的一致性。
5. v2 读取新模型，v1 继续读取旧 JSON；保留投影 adapter。
6. 完成一个发布周期的数据校验和备份后，才另开 ADR 讨论停用字段。

## 5. API 兼容策略

- `/api/v1` 不改变字段语义；bug fix 也配回归测试。
- `/api/v2` 使用供应商无关 ID、计划版本、evidence 和 typed conflicts。
- 前端先统一 TS 类型和 `apiClient`，再逐页切换；避免一次重写大页面。
- 对生成、重排和预订意图使用 idempotency key；对版本更新使用 `If-Match` 或显式 base version。

## 6. 测试门禁

每个迁移单元至少包含：

- schema/model unit tests；
- provider mock contract tests 和失败降级测试；
- optimizer 固定数据集的可行性/确定性测试；
- Critic 每个冲突码的正反例；
- Alembic 空库升级和 upgrade/downgrade 测试；
- v1 API 快照回归；
- 前端 TypeScript build 和关键流程测试；
- 性能预算：候选规模、求解上限、provider timeout、Agent 迭代上限。

## 7. 当前已知迁移风险

1. POI 营业、排队、末班车和可达性数据在不同供应商间覆盖率差异大。
2. 当前 Alembic 缺少城市/活动基线，空库部署可能不可复现。
3. CP-SAT 当前只是按天选择，不能高估为完整路线优化器。
4. Google 结构已渗入 refinement 和前端，支持高德前必须建立 canonical model。
5. 同步数据库访问可能阻塞 async API；不宜与领域迁移同时大改，应独立评估。
6. 保存行程 JSON 与前端重复类型可能造成 v1/v2 契约漂移。
7. 实时数据的 TTL、失败语义和费用上限若不先定义，会产生“陈旧但看似精确”的结果。
8. 负载权重缺少真实反馈校准，首版必须标明估算并保留组成项。

## 8. Phase 0 结论

无需创建空 Provider 代码。首个可实施的最小切片应是“POI 实用信息可信度契约”：只新增 Pydantic 模型、字段级 evidence 模型、Mock SearchProvider contract tests 和一个只读示例服务，不接真实外部 API、不改变现有规划结果。它为后续地图、天气、交通和 Critic 提供共同的数据真实性边界。
