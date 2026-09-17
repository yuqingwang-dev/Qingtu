# 晴途：成都可信攻略 RAG（第一版）

## 如何体验

前后端启动后访问 http://localhost:3000/knowledge 。首页也有「先查攻略」入口。
单城市行程结果页会显示同一个「出发前，先把小事弄明白」组件，不修改优化器或行程安排。

选择景点，点击常见问题，或输入问题并点击「查找有来源的回答」。默认仅在本地检索，不产生模型 API 费用。
「让 AI 帮我筛选资料」是可选项，使用后端现有聊天模型配置，可能产生聊天 API 费用。

首批覆盖成都大熊猫繁育研究基地、武侯祠、杜甫草堂：5 个官方来源、18 条人工核对摘要。
未知景点、未知主题不回答；不会将成都规则套用到其他城市。其余国内外城市的原有规划不受影响。

## 技术实现及边界

- FastEmbed 0.7.4 + ONNX Runtime CPU，`BAAI/bge-small-zh-v1.5`，512 维中文向量。模型为 MIT 许可；模型缓存不进入 Git。
- PostgreSQL/pgvector 独立 `knowledge_documents` / `knowledge_chunks` 表。不改变原有 1536 维景点向量，不需要打开旧 `RAG_ENABLED`。
- 人工审核本地 JSON → 按主题拆为短段 → 中文向量 → pgvector 精确余弦检索；jieba + BM25 关键词分支，RRF 合并排序。
- 先按城市、景点别名、主题和有效期过滤，再检索。第一版主题识别是规则，不是通用语义理解；无法识别的问法会拒答。小语料无需 ANN/HNSW，未声称实现该索引。
- 记录来源 URL、核对日、复核期限、内容哈希和版本。幂等导入，源摘要改变才升版；重新导入不会自动更新核对日期。
- 模型只允许从检索结果中选择引用 ID；服务端校验 ID 后展示对应的原始核对摘要。模型编造的正文、链接不被展示。这是受约束的检索增强回答，不是自由生成旅游建议。
- AI 401、超时、无 Key、非法引用 → 保留证据摘要并提示失败原因；本地模型缺失 → 明示 BM25 降级。请求路径不会自动下载模型。
- 静态资料不能确认实时余票、天气或排队；出游日期超出复核期限时，只引导查看官方原文。
- 每个后端进程最多 2 个知识问答并发、AI 筛选超时 20 秒；现有中间件为知识问答单独限流 10 次/分钟/IP。多进程生产部署需网关/Redis 分布式限流，反向代理环境需配置可信代理，不接受任意转发头绕过。
- 无任意 URL 抓取接口，不接收文件上传；导入仅支持人工审核并列入白名单的官方域名。

资料核对时间代表本项目人工核对日期，**不是官网发布时间，也不是官网保证的政策有效期**。
期限默认在语料中设为 30 天，是项目内部的复核策略。节假日临时公告仍须使用者出发前核实。

## 安装与导入（PowerShell）

在仓库根目录执行，沿用已有 PostgreSQL 配置；数据库需安装 pgvector 扩展。

```powershell
cd D:\RouteMind\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.import_knowledge --download-model
```

首次需联网下载模型到 `backend/.cache/models`；后续直接执行：

```powershell
.\.venv\Scripts\python.exe -m scripts.import_knowledge
```

导入脚本读取根目录 `.env`。无需独立 Embedding Key。不会把 DeepSeek Key 用来请求向量。
下载时 Windows 不支持缓存符号链接的警告不影响使用，但可能多占用一些磁盘空间。

可选配置写在根目录 `.env`：

```dotenv
KNOWLEDGE_VECTOR_ENABLED=True
KNOWLEDGE_MODEL_CACHE=.cache/models
```

修改配置后重启后端。只修改资料并重新导入，无需重新编译前端。
增加城市需要收录真实来源、人工核对资料，补入导入清单/别名/主题和测试；不能只给数据库追加城市名就宣称攻略已覆盖。

## API

- `GET /api/v1/knowledge/status`：索引数量、覆盖景点及来源清单；不代表模型已经加载或聊天 Key 有效。
- `POST /api/v1/knowledge/ask`：查询，不修改数据库或行程。

```json
{
  "city_id": 1,
  "poi_name": "武侯祠",
  "question": "行李在哪里寄存？",
  "travel_date": "2026-09-25",
  "use_ai": false
}
```

上面的 `city_id` 只是格式示例，请从 `/api/v1/cities` 取实际成都 ID，不能假定为 1。
返回 `answered / not_found / needs_refresh / requires_live_data`，并附 `retrieval_mode`、`answer_mode`、`citations`、`warnings`。
引用包含题目、官方链接、原文的人工摘要、核对日期、复核期限及源版本。

## 验证与复现

```powershell
cd D:\RouteMind\backend
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m compileall -q app scripts
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge.py -q
.\.venv\Scripts\python.exe -m scripts.evaluate_knowledge
.\.venv\Scripts\python.exe -m scripts.smoke_knowledge
# 可选：会额外调用一次现有聊天模型
.\.venv\Scripts\python.exe -m scripts.smoke_knowledge --ai

cd D:\RouteMind\frontend
npm.cmd run typecheck
npm.cmd run build
```

2026-09-17 本机结果：

- 数据库升级成功；首次导入 changed=5，再次导入 changed=0 / skipped=5。
- 36 项新增离线测试通过；覆盖幂等更新、城市隔离、过期拒答、实时问题拒答、向量失效降级、非法引用及 AI 401 回退。
- 完整测试 216 通过、1 跳过（真实数据库 baseline 测试默认需显式开启）。
- 本机曾出现 Windows 原生 `0xc000001d` 导入崩溃；按已有环境规避方式预加载模块后完整测试通过，不能将此称为彻底修复了 Python 环境。
- 类型检查和生产构建通过。浏览器自动化不可用，未做截图/交互视觉验收。
- ESLint 通过（0 错误，21 条既有警告）；修正了配置的插件作用域与 CommonJS 脚本规则，新增组件没有 lint 警告。
- `/knowledge` 与 `/plan/single-city` 页面 HTTP 均为 200。当前 Redis 未连接，知识检索依赖本地模型和 PostgreSQL，不因此失效。
- 真实 HTTP：索引接口 5 来源/18 段；武侯祠寄存问题命中混合检索；余票返回 requires_live_data；人民公园返回 not_found。
- 真实聊天请求仍为 `authentication_failed`（401）；界面返回 evidence_only 并保留引用。请自行在后端 `.env` 更换有效 Key，不要发送到聊天或提交 Git。不能据此判断是余额不足。

### 小样本开发评测（不是独立测试集）

`data/knowledge/eval_cases.json` 有 19 个按具体证据段标注的可答问题和 8 个拒答问题。
脚本实际调用本地模型和 PostgreSQL 余弦排序，不调用聊天模型；若混合检索降级，脚本直接报错，不伪报向量成绩。

| 方法 | Recall@3 | MRR@3 | 拒答状态正确率 |
| --- | --- | --- | --- |
| BM25 + 规则过滤 | 1.0000 | 1.0000 | 8/8 |
| BM25 + 本地向量 + RRF + 规则过滤 | 1.0000 | 1.0000 | 8/8 |

数据量小、景点和主题过滤强，**此结果不证明向量优于关键词检索，更不是线上准确率**。
下一阶段需增加独立留出集、口语/错别字/多意图/否定问题和困难负例，扩充多城市语料，再比较向量、混合及重排的实际收益。

## 后续阶段（尚未实现）

1. 定期复核、过期提醒与后台资料审核；保留历史全文版本、回滚和来源变更审计。
2. 扩展其他城市，增强景点实体识别与主题语义理解；必要时加入中文 reranker。
3. 更丰富的有引用生成回答、逐条支持关系评估和人工审核，而不是只校验引用 ID 存在。
4. 将核验后的结构化预约/开放规则作为规划约束，和现有 Agent/真实路线结合；当前只提供须知，不声称优化器已遵守这些规则。
5. 检索 trace、真实用户反馈、独立评测与成本/延时观测；当前没有实现 LangGraph、LangSmith 或通用多轮记忆。

## 本次文件范围

新增：迁移 `d3f7a9021456`；`api/knowledge.py`；`services/knowledge_embeddings.py`、`knowledge_ingest.py`、`knowledge_service.py`；`data/knowledge/`；导入、评测、smoke 三个脚本；`tests/test_knowledge.py`；前端 `TravelKnowledge.tsx`、`knowledge/page.tsx`；本文档。

修改：`.gitignore`、`.env.example`、README、后端依赖、配置、模型、主路由、限流中间件；前端首页、单城市行程页、ESLint 配置作用域。
仓库原本已有大量未提交改动，本次未重置或清理这些改动。
