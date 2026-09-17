# TripPilot 开发路线图

## Phase 0：Architecture Migration（本阶段）

目标：建立 Qingtu 现状基线与可渐进执行的 TripPilot 设计。

- 审计后端、前端、数据库、RAG、Redis、OR-Tools、地图和 Docker；
- 明确保留项、限制、目标架构、数据/API/Agent/优化扩展方案；
- 记录技术决策和回滚原则；
- 仅新增文档，不改变运行时行为。

退出条件：五份设计文档完成；现有后端测试与前端 lint/build 结果有记录；停止并等待确认。

## Phase 1 / MVP：可信、可执行的单城市计划

### 1.1 数据真实性最小切片

- 定义 `Evidence`、`ConfidenceKind`、POI practical info 和 Provider result；
- 提供 Mock SearchProvider，封装现有 Google Places 为 adapter；
- 补全数据库基线和 Alembic 可复现测试；
- 旧 `/api/v1` 不变。

### 1.2 Traveler Profile 与 Physical Load shadow mode

- CHILL/BALANCED/EXPLORER profile；
- 计算 walking、steps、standing、queue、stairs、slope、temperature、baggage、transfers；
- 只展示负载与来源，不改变现有排程，收集校准数据。

### 1.3 Optimization contract 与 Critic

- 统一 greedy/OR-Tools 输入输出；
- 修复跨天重复、不可行诊断、硬软预算；
- 实现九类 Critic conflict 的确定性检查；
- 先 shadow-check，达到回归门禁后启用。

### 1.4 时间窗与交通矩阵

- 支持星期、多时段、闭馆日、最后入场和时区；
- MapProvider matrix + Haversine fallback；
- CP-SAT 时间维度、行程结束时间和 Physical Load 约束。

MVP 验收：单城市计划的硬约束满足率可测；每个动态/实用字段有可信度；Provider 故障可降级；原 Qingtu 主流程仍可回归。

## Phase 2 / V1：Route-aware 与 Live Copilot

### 2.1 Route-aware recommendations

- route corridor 搜索；
- Detour Cost；
- food/cafe/souvenir/shop/rest/restroom 插入；
- 饭点、营业、排队、预算和偏好联合排序与解释。

### 2.2 Versioned Replanning

- trip plan versions、items、legs、events；
- “累了/下雨/饿了/跳过/早回/新增地点/预约将迟到”意图；
- 锁定已完成和预约项目，只重排剩余行程；
- Planner→Optimizer→Critic→Replanner，最多三次 repair。

### 2.3 交通、天气和行李

- 比较 walking/subway/bus/taxi 的时长、价格、步行和换乘；
- 天气触发模式权重变化；
- 酒店/车站/景区寄存方案及返回酒店成本。

### 2.4 前端体验

- 计划版本 diff、冲突、证据和 Physical Load 可视化；
- Provider-neutral map view model，增加高德 adapter；
- 收敛重复 TS 类型和直接 fetch。

V1 验收：典型现场事件能在时间预算内产出经过 Critic 的新版本；用户可拒绝/回滚；route-aware 推荐展示增量绕路成本。

## Phase 3 / V2：长期记忆、评估和安全预订

- 记录实际花费、步数、排队、疲劳与偏好反馈，版本化更新 profile；
- 建立离线场景集和在线指标：成功率、约束率、效率、幻觉、延迟、token/cost；
- Crowd/queue 场景与更鲁棒的优化；
- MockBookingProvider → 受控真实 provider；价格复查、显式确认、幂等和审计；
- 多城市交通与跨日全局约束，必要时评估分解求解。

V2 验收：记忆改善可通过评估集量化；预订无法绕过用户确认；Agent 和 Provider 调用完整可审计。

## 暂不承诺

- 全自动支付或无确认取消；
- 依赖 LLM 猜测营业时间、价格、拥挤或交通；
- 在没有覆盖率/质量指标时声称实时或最优；
- 为技术展示提前拆微服务或引入工作流框架。

## 下一步建议

等待 Phase 0 审阅后，只启动 Phase 1.1：实现供应商无关的 POI practical info + evidence Pydantic 契约、Mock SearchProvider 和 contract tests。该切片不触碰 optimizer 和现有 API，是后续所有实时数据与 Critic 的最小公共基础。
