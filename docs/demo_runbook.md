# 晴途本地演示流程

## 启动和状态检查

在仓库根目录 PowerShell 执行：

```powershell
.\start_qingtu.ps1
```

脚本会打开两个窗口，并先检查数据库、Redis、LLM、高德 Key 和真实 POI 配置。
LLM 默认只检查是否配置，不会发起请求；需要验证 DeepSeek/OpenAI 账号时再执行：

```powershell
.\start_qingtu.ps1 -ProbeLLM
```

`-ProbeLLM` 会产生一次真实模型请求，可能消耗配额。也可以只检查环境：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\check_environment.py
```

## 三条固定演示

打开 `http://localhost:3000`，按下面顺序演示：

1. 普通规划：选择成都，填写 2 天、文化和美食，保持普通规划模式；结果页观察逐日活动、地图和 `AI 解读来源`。显示“规则降级”代表行程仍由确定性规划算法生成，不能称作 AI 解读。
2. Agent 规划：勾选“使用 Agent 智能筛选（测试版）”，输入“优先文化和美食，少购物”；结果页展开 Agent 过程，说明候选集、工具调用、停止原因和最终排程使用的是同一批候选。
3. 攻略查询：打开 `http://localhost:3000/knowledge`，选择成都的武侯祠，查询“行李在哪里寄存？”。展示官方链接、核对日期、检索模式和无答案/实时信息提示。

命令行也有固定流程。默认只执行无成本状态和本地攻略查询：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\demo_flows.py
```

普通规划和 Agent 会调用模型，确认账户可用后再执行：

```powershell
.\.venv\Scripts\python.exe scripts\demo_flows.py --execute-planning
```

## 状态含义

| 状态 | 含义 | 用户动作 |
|---|---|---|
| `healthy` | 已完成真实探测 | 正常使用 |
| `configured` | 已填写 Key，但没有探测 | 需要时使用 `-ProbeLLM` |
| `missing_api_key` | 没有 Key | 在根目录 `.env` 配置后重启 |
| `authentication_failed` | Key 无效或已失效 | 重新生成/替换 Key，不要把 Key 发给别人 |
| `insufficient_balance` | 上游返回余额或配额不足 | 到服务商控制台核对余额和配额 |
| `timeout` / `connection_failed` | 网络或服务超时 | 检查代理、网络和服务商状态 |
| `disconnected` | Redis 未连接 | 本地可继续使用；需要限流/缓存时启动 Redis |

普通规划的行程结果和 AI 解读是两个状态：即使 `narrative.source=fallback`，行程仍可能已经生成，但页面必须显示“未生成 AI 解读”，不能把规则文案标作 AI 内容。
