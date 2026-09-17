# Qingtu 求职项目升级执行计划

2026-09-16。面向 Agent 应用开发 / Agent 全栈 / LLM 应用实习。
本清单是现有 docs/roadmap.md 的近期执行切片，不把已有模块重复实现。

| 步骤 | 交付 | 验收条件 |
| --- | --- | --- |
| 1：Agent 基础闭环 | 统一聊天模型配置；候选集驱动排程；工具校验、执行预算、测试；前端可选 Agent 模式 | DeepSeek-only 可调用 Agent/解读/修改；筛选结果实际影响最终地点；无匹配明确返回；新增不少于 30 项可重复测试 |
| 2：真实交通 | 成都优先的地图 Provider、起终点、路线矩阵与几何、来源时间与降级 | 地图和排程使用同一交通数据；同候选集与旧算法比较路程/时长；国外保留现有能力 |
| 3：需求澄清和可恢复工作流 | LangGraph 状态、关键问题追问、持久化、真实进度和取消 | 刷新或重启后恢复；不重复执行已完成工具；用户确认前不擅自变更硬约束 |
| 4：局部重规划 | 版本、锁定、规则 Critic、有限修复、差异和撤销 | “第二天太累”只修改指定范围；已完成/预约项目保持稳定；冲突有原因 |
| 5：可信中文攻略 | 有来源和日期的文档、混合检索、引用、无答案处理 | 引用可回溯；资料中的指令不改变工具权限；动态信息经工具获取 |
| 6：评测与交付 | 约 100 个评测案例、基线对比、追踪/成本统计、部署、演示 | 实测重复率/约束满足率/任务成功率/P95/费用，不编写未经测量的提升数字 |

## 第一步的使用方法

状态：第一步功能已实现并完成真实模型接口联调；第二步的住宿起终点与真实路线首版已推广至北京、上海、杭州、成都，范围/样例/限制见
[真实路线说明](chengdu_route_planning.md)。第三至六步未开始；当前 DeepSeek 密钥认证需用户恢复。

前端 http://localhost:3000/plan/single-city 选择国内或国外城市，在偏好页勾选
“使用 Agent 智能筛选（测试版）”，可输入“多安排文化景点，少购物”。
结果页可展开筛选过程，查看每步保留下来的候选数量。默认常规规划保持不变。

也可在 http://localhost:8000/docs 使用 POST /api/v1/agent-plan，结构如下；
city ID 请先通过 GET /api/v1/cities 获取，不要假定不同数据库中 ID 相同。

```json
{
  "preferences": {
    "destination_city_id": 14,
    "start_date": "2026-10-01",
    "end_date": "2026-10-03",
    "trip_type": "weekend",
    "budget_level": "medium",
    "budget_per_day": 300,
    "preferred_categories": ["culture", "food"],
    "energy_level": "moderate",
    "travel_mode": "mixed"
  },
  "user_message": "优先文化与美食，先查找候选地点再安排行程。"
}
```

## 模型配置

根目录 .env 中可选 LLM_PROVIDER=auto/deepseek/openai。auto 在存在 DeepSeek
密钥时优先使用 DeepSeek，否则使用 OpenAI；显式选择的供应商缺少密钥时返回
清晰错误，不偷偷切换到另一家。Agent、文字解读、修改意图使用同一选择。
密钥不得写入前端或提交 Git。

向量配置独立：EMBEDDING_MODEL、EMBEDDING_API_KEY、EMBEDDING_BASE_URL。
仅默认 OpenAI 向量地址可回退到 OPENAI_API_KEY，绝不把 DeepSeek 聊天密钥当向量密钥。
现有向量库固定 1536 维；替换不同维度模型需要后续迁移/重建索引，不在本步骤自动执行。
RAG_ENABLED=False 时使用中英文关键词查找，trace 明确标记 keyword；不能宣传成已完成语义检索。

Agent 默认最多 8 次模型决策、24 次工具调用、90 秒异步执行期限。
AGENT_MAX_TOKENS=12000 按每轮返回的 usage 判断是否继续；这是观测后的停止门槛，
不是严格的计费上限。tokens_used 仅计算 Agent 决策，不包含解读和向量调用。
同步数据库/优化器工作不会被 asyncio 强制抢占；优化器仍有自己的求解时间限制。
生产严格取消/排队将在后续工作流任务中完成。

## 候选集合与错误语义

- 初始候选是当前城市去除 avoid 后的已有 POI。
- search 显式替换当前候选集，filter 仅在当前候选内继续缩小；每次变更记录 ID。
- 搜索空字符串表示明确列出可用地点；没有匹配结果不会暗中改为全量。
- 长行程覆盖检查：先排除单点预算/开放时间已不可行的 POI。非空搜索/筛选结果若低于 min(旅行天数, 初始可行候选数)，拒绝本次缩减并保留原候选，trace 返回 would_create_empty_days，供模型放宽软筛选；不恢复用户 avoid 排除的地点。
- 可行地点足够时，OR-Tools 强制每天至少一个不同地点；真实数据不足时仍保留日期，界面明确显示“待补充”与调整入口，不显示空地图或误导性的零费用。
- 排除必去地点的工具请求被拒绝且不改变候选；支持结构化约束中的中英文地点名。
- 模型提前停止或达到步数预算时，仍只使用当前候选做确定性排程，并标注 fallback。
- 空候选/不可满足的必去条件返回 422；模型错误返回安全的 503 错误码；超时返回 504。
- 旅行范围、日期和预算沿用后端校验；现阶段 Agent 仅支持单城市。
- 工具记录是可观测执行摘要，不是模型内部思维链，也不代表完整事实核验。
- 本步不支持任意自然语言硬约束的可靠提取；硬约束仍需结构化字段，澄清属于第三步。

## 验证命令

在 backend 目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agent_workflow.py tests/test_chat_provider.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app/api/schemas.py app/config.py
.\.venv\Scripts\python.exe -m compileall -q app
```

前端：npm.cmd run typecheck。

启动后端时加载根目录配置：

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --env-file ../.env
```

启动前后端后，可在 backend 目录运行实时冒烟检查（会调用已配置的模型并计费）：

```powershell
.\.venv\Scripts\python.exe scripts/smoke_agent.py
```

离线测试使用脚本化模型回复和真实排程逻辑，不证明真实模型在任意自然语言下都正确。
实时冒烟覆盖成都和巴黎的工具调用及已有修改接口，也不能代替后续规模化质量评测。

## 面试展示建议

演示一次文化/美食筛选，展示每步候选 ID 与最终地点包含关系；再演示无匹配结果。
解释为什么不让语言模型直接生成虚构景点，为什么确定性排程仍需要候选状态。
当前不要声称已经实现真实道路最短路径、天气重规划、持久化 Agent 或完整 RAG。

## 本轮验收记录（2026-09-16）

- 新增 32 个脚本化模型/供应商选择回归案例；不消耗真实 API 额度。
- 完整后端测试一次运行结果：118 passed、1 skipped（需要显式开启的 PostgreSQL+pgvector 迁移测试）。
- Ruff、配置和 API schema 的 mypy、Python compileall、前端 typecheck 通过。
- 最终前端单城市页面 HTTP 200。未进行完整浏览器自动化操作验收。
- 最终真实 DeepSeek 成都三天：HTTP 200，6 个候选、6 个不重复地点，termination_reason=optimized，真实 AI 解读；决策 usage 为 10951 tokens。
- 最终真实 DeepSeek 巴黎三天：HTTP 200，16 个候选、15 个不重复地点，termination_reason=optimized，真实 AI 解读；决策 usage 为 3964 tokens。
- 已有行程修改接口使用同一模型成功返回 HTTP 200，应用一次删除操作。
- 上述是两次样例调用，不是整体准确率或普遍费用估计。早期提示词版本曾触发 token_limit 降级；调整提示词后本轮两个样例正常结束。

环境风险：在随后重复启动/收集测试时，本机基于 E:\\miniconda3 的 Python 运行时
多次出现 Windows 原生 access violation / 0xc000001d，发生于 SDK/Pydantic/FastAPI
导入期间，而非断言失败。部分进程可正常启动且真实接口已验证；尚未定位底层根因，
不能将偶尔通过描述为环境问题已修复。后续应在独立干净 Python 环境或 CI 复验。
本轮未升级/重装用户 Python，也未修改 BIOS 或系统安全设置。

工具调用消息与工具结果 ID 配对参考 [OpenAI 官方 Function Calling 文档](https://developers.openai.com/api/docs/guides/function-calling)。
