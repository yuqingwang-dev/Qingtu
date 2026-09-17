# 国内真实 POI 搜索接入

本轮接入高德 Web 服务 v5 POI 搜索，已支持的国内城市在生成普通行程和 Agent 行程前自动补充真实地点。
不是城市自动扩容，也不是实时路线/天气/预约服务；原有国外城市与规划保持可用。

## 配置与启动

根目录 `.env`：

```env
AMAP_WEB_SERVICE_KEY=仅在本机填写Web服务类型Key
LIVE_POI_ENABLED=True
POI_CACHE_TTL_SECONDS=3600
POI_MAX_RESULTS=36
POI_TIMEOUT_SECONDS=8
```

前端地图继续使用 `frontend/.env.local` 的 `NEXT_PUBLIC_AMAP_KEY`（Web端 JS API 类型）。
两个 Key 不互换。更改根目录配置后重启后端。

```powershell
cd D:\RouteMind\backend
.\.venv\Scripts\python.exe -m alembic upgrade head
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --env-file ../.env
```

已有启动/导入阶段 Windows 原生崩溃风险仍需独立排查，不能理解为高德权限错误。

## 查看与使用

- 前端：http://localhost:3000/plan/single-city 。选择国内城市并重新生成；普通模式和 Agent 模式都会触发补充。
- API 文档：http://localhost:8000/docs 。新增 GET `/api/v1/domestic/pois`，输入城市 ID、keywords（如博物馆）和 limit（1–25）。
- 城市 ID 从 GET `/api/v1/domestic/cities` 获取。预览接口不写数据库；实际规划才持久化候选。
- 生成后显示搜索来源、获取数量、合并后候选数量、缓存状态及失败提示；选中真实地点显示高德来源/获取时间。
- 关闭 LIVE_POI_ENABLED 可恢复纯本地 seed 规划，不会删除已保存行程。

## 实现边界与数据语义

1. 使用现有 SearchProvider / PoiPracticalInfo / Evidence 契约，新增 AmapSearchProvider。
2. 查询强制 city_limit=true，并校验返回 cityname，避免跨城市结果；没有坐标/非法坐标、重复高德 ID 和入口/停车场类子点会过滤。
3. 默认按最多三个偏好类别各取 12 个地点，共最多 36 个；单查询至多两页。规划候选总量上限 60，避免无限增长。
4. 供应商身份通过 `(city_id, provider_name, provider_poi_id)` 唯一约束和 upsert 保持稳定。数据库新增三个可空字段，已有景点不覆盖；同名近距离 seed 优先。
5. 查询快照缓存优先 Redis，Redis 不可用时使用限量进程内 TTL 缓存；权限错误不缓存。供应商 Key 不返回前端、不存入 POI 元数据，HTTP 日志脱敏。
6. 本次请求只使用 seed 与当前查询得到的地点；失败时仅复用未过期的供应商快照。持久化记录保留稳定 ID 以兼容保存/修改行程，TTL 过期不代表记录自动删除，也不会当作最新资料自动回用。
7. 真正已知的是供应商报告的名称、坐标、地址和可能返回的评分/人均消费。`cost` 人均消费不当作门票价格。
8. 费用缺失时，排程暂用明确的类别预算假设（文化50/自然30/餐饮80/购物100等）；停留时长为60–120分钟类别估算。未知评分3.5仅为内部中性排序值，前端显示“暂无评分”。
9. 今日营业时间不复用为未来日期的营业时间。未返回的信息保持未知；导入活动不施加未经验证的时间窗，行程明确提醒核实营业/预约，不声称满足真实开馆约束。
10. 高德坐标明确标记 GCJ02，直接用于高德底图；缺少前端高德 Key 时不把这些坐标静默绘制到 WGS84/OSM 底图。原 seed 坐标仍沿用旧行为，系统性坐标规范化属于路线阶段。
11. 公共 POI 搜索接口目前服务本地开发。公开部署前仍需按业务权限/用户配额保护供应商用量；现有应用的全局频率限制不能替代完整供应商费用控制。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests/providers/test_amap_search.py tests/test_live_poi_service.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

包含城市隔离、缺失字段、Key/额度错误、超时、分页上限、缓存隔离、重复导入、seed 保留、供应商故障降级和新地点进入优化器。

实际 Key 验证：高德返回 HTTP 200 / status=1 / infocode=10000。
首次成都导入：原有 10 个地点，检索并接入 36 个高德地点，候选池 46 个。

完整接口验证：GET /domestic/pois 返回真实 5 个博物馆地点，重复请求 cache_hit=true。
POST /domestic/plan 的成都 8 天返回 HTTP 200，每天 5 个活动，40 个 ID 全程不重复，
其中 32 个为真实高德 POI，来源字段保留。供应商搜索排序可能变化，后续导入可能增加
新的 ID；相同 ID 不重复插入。143 项后端测试通过，1 项需显式启用的迁移测试跳过。

本次 DeepSeek 返回 401 authentication_failed，普通规划正确降级并保留搜索/排程结果；
Agent 的候选补充已通过离线测试，但当前真实 Agent/AI 解读受该密钥认证问题阻塞。
需用户在本机检查/更新 DEEPSEEK_API_KEY；不要将其与 AMAP_WEB_SERVICE_KEY 互换。

启动环境临时兼容方式（已恢复 HTTP 服务，WebSocket 协作未启用）：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --loop asyncio --http h11 --ws none --port 8000 --env-file ../.env
```

模型 SDK 改为按需加载，POI/城市/健康检查不必启动时加载它。
使用上述方式启动成功不代表已定位 Windows 原生崩溃的根因，系统环境问题仍需单独排查。

接口依据：[高德 POI 搜索文档](https://developer.amap.com/api/webservice/guide/api/newpoisearch)。
