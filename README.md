# 航海图经线网复原

海图修复师扫描一张受潮航海图后，把按从左到右录入的 5–10 条经线残迹复原为**同一套经线网**。
系统在服务端做**全局联合裁决**——共同确定严格递增的整数经线序号、正的共同网距 `d` 与起始
位置 `s`，使每条残迹偏差均不超过限值，并依次：

1. 使**最大偏差**最小；
2. 使**偏差平方和**最小；
3. 使**相邻缺线数序列**字典序最小。

绝不逐段就近取整。全部计算使用精确有理数（`fractions.Fraction`），字典序裁决不受浮点误差影响。

## 目录结构

```
├── docker-compose.yml      # api + web + 一次性 verify 服务（健康检查、可配置宿主机端口）
├── api/                    # FastAPI 业务服务
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py         # 路由：GET /health、POST /api/restore
│   │   ├── schemas.py      # 请求校验（5–10 条严格递增整数横坐标等）
│   │   └── solver.py       # 精确全局求解器（分支限界 + 区间传播 + 受约束最小二乘）
│   └── tests/              # 求解器单测（含暴力枚举对照、LP 顶点法交叉验证）与 API 测试
├── web/                    # React + TypeScript + Vite 前端
│   ├── Dockerfile          # 多阶段：vite 构建 → nginx 托管并反向代理 /api
│   ├── nginx.conf
│   └── src/
└── verify/                 # 一次性验证服务
    ├── Dockerfile          # node + python 双运行时
    ├── run.sh              # 依次执行：代码测试 → 前端构建 → 复原 API 冒烟
    └── smoke.py            # 经 nginx 代理的端到端冒烟
```

## 快速开始

```bash
# 启动应用（宿主机端口可用 WEB_PORT 配置，默认 8080）
WEB_PORT=8080 docker compose up --build web

# 打开页面
open http://localhost:8080
```

## 一键验证（verify 一次性服务）

`verify` 服务在 `api`、`web` 健康检查通过后自动执行：后端代码测试（pytest）、
前端生产构建（`npm ci && npm run build`）、复原 API 冒烟（经 nginx 代理的端到端请求），
随后退出，**以退出码报告结果**（0 = 全部通过）。

```bash
# 运行验证并以 verify 的退出码作为命令退出码
docker compose up --build --exit-code-from verify verify

# 或者：先启动应用，再单独运行一次验证
docker compose up -d --build web
docker compose run --rm verify
```

## 业务 API

### `POST /api/restore`

请求：

```json
{
  "xs": [0, 10, 30, 40, 50],
  "maxMissing": [0, 1, 0, 0],
  "tolerance": 0.4
}
```

* `xs`：5–10 个严格递增的整数横坐标（按从左到右录入）；
* `maxMissing`：相邻残迹间可能缺失的经线数上限，`len(xs) - 1` 个，每个 0–50；
* `tolerance`：允许定位误差（正数，作用于每条残迹）。

可行时返回 `200`：

```json
{
  "feasible": true,
  "spacing": 10.0,
  "start": 0.0,
  "maxDeviation": 0.0,
  "sumSquaredDeviations": 0.0,
  "traces": [
    {"position": 1, "x": 0,  "serial": 1, "fitted": 0.0,  "deviation": 0.0},
    {"position": 3, "x": 30, "serial": 4, "fitted": 30.0, "deviation": 0.0}
  ],
  "missing": [0, 1, 0, 0]
}
```

每条残迹给出**经线序号**（`serial`，首条为 1）、**拟合位置**（`fitted = s + (serial-1)·d`）
与**偏差**（`deviation = fitted − x`）；`missing[i]` 为第 i 与 i+1 条残迹间补出的缺线数。

不存在共同网距时，返回首个无法满足误差约束的残迹及其相邻已定序号区间：

```json
{
  "feasible": false,
  "failure": {
    "trace": 3,
    "x": 11,
    "requiredTolerance": 2.25,
    "previousSerialRange": [2, 2],
    "candidateSerialRange": [3, 3],
    "message": "第 3 条残迹（x=11）无法满足误差约束：相邻已确定的经线序号区间为 [2, 2]，…"
  }
}
```

非法输入返回 `422` 并附带具体原因。另有 `GET /health` 供健康检查。

## 求解方法（为什么不是逐段就近取整）

固定一组序号 `k_1<…<k_n` 后，最佳 `(s, d)` 的切比雪夫误差由直线族交错定理给出——
等于所有三点组等幅交错误差的最大值，可精确求值。求解器在此之上做全局分支限界：

* **阶段一**：在所有合法序号组合上最小化最大偏差 `t*`（启发式初始上界 +
  三点组下界剪枝 + 针对未来序号位置的精确区间传播）；
* **阶段二**：在达到 `t*` 的组合上，以受约束（`|残差| ≤ t*`）精确最小二乘最小化偏差平方和 `q*`；
* **阶段三**：枚举按序号字典序进行，仅在严格改进 `(t*, q*)` 时更新，
  因而并列时自动得到字典序最小的相邻缺线数序列。

不可行时，按前缀单调性定位**首个**无法满足误差约束的残迹，并报告其相邻已确定的
序号区间（前一残迹在所有可行前缀复原中的序号范围）与该残迹的候选序号区间。

## 本地开发

```bash
# 后端（Python 3.11+）
cd api && python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest httpx
.venv/bin/python -m pytest            # 代码测试
.venv/bin/uvicorn app.main:app --reload --port 8000

# 前端（Node 20+，dev server 代理 /api 到 localhost:8000）
cd web && npm ci && npm run dev       # http://localhost:5173
npm run build                         # 生产构建（tsc + vite）
```
