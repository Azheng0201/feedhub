# 📡 FeedHub - 高性能 RSS 聚合阅读器
[![CI](https://github.com/Azheng0201/feedhub/actions/workflows/ci.yml/badge.svg)](https://github.com/Azheng0201/feedhub/actions)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)
![Docker](https://img.shields.io/badge/Docker-Supported-blue)

FeedHub 是一个基于 Python + FastAPI 构建的现代化 RSS 聚合阅读器。支持定时抓取、多源并发、文章过滤和可视化的数据看板。

## 🏗️ 系统架构

本项目采用现代 Web 应用架构，已实现全链路容器化部署：

- **Web 层**：FastAPI (Uvicorn) 提供异步 RESTful API 与静态页面。
- **数据层**：PostgreSQL (替代 SQLite, 支持高并发写入)。
- **缓存层**：Redis (优化高频统计接口响应)。
- **异步任务**：APScheduler (后台定时抓取) + Asyncio (并发 HTTP 抓取与 AI 摘要生成)。
- **AI 能力**：接入兼容 OpenAI 格式的大模型接口，自动生成 3 句话。

## ✨ 核心特性

- **⚡极速并发抓取**：使用 `httpx.AsyncClient` + `asyncio.gather` 实现多源并发抓取，避免慢源阻塞。
- **⏱️后台定时任务**：集成 `APScheduler`，支持每 30 分钟自动抓取全量阅读源。
- **📊数据可视化看板**：使用 `Chart.js` 渲染文章分布与阅读状态。
- **🛡️生产级架构**：包含数据去重、SQLite 级联删除、N+1 查询优化（`joinedload`）。
- **🐋容器化部署**：提供 `Dockerfile` 与 `docker-compose.yml`，一键启动。

## 🛠️ 技术栈

- **后端**: FastAPI, SQLAlchemy 2.0, Pydantic v2, APScheduler, feedparser 
- **前端**: Vanilla JS, Bootstrap 5, Chart.js
- **数据库**: SQLite（支持无缝切换至 PostgreSQL）
- **测试与质量**: pytest, respx (HTTP mock), ruff
- **部署**: Docker, Docker Compose

## 🚀 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/Azheng0201/feedhub.git
cd feedhub

# 2. 配置环境变量
cp .env.example .env

# 3. 一键启动
docker compose up -d --build
```

### 方式二：本地开发

```bash
# 1. 安装依赖
python -m venv .venv
source .venv/bin/activate # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt

# 2. 启动服务
uvicorn app.main:app --reload
```

Swagger API 文档地址：http://127.0.0.1:8000/docs

## 🧪 自动化测试
本项目采用严格的 TDD 实践，核心业务逻辑覆盖率达 80%+。测试环境完全使用内存 SQLite，不依赖真实网络请求。
```bash
pytest --cov=app
```

## 📂 目录结构

```text
feedhub/
|—— app/
|   |—— main.py         # FastAPI 入口与生命周期管理
|   |—— db.py           # SQLAlchemy 数据库引擎
|   |—— models.py       # ORM 模型（Feed，Article）
|   |—— schemas.py      # Pydantic 校验模型
|   |—— routers/        # 路由层（feeds，articles）
|   |—— services/       # 业务逻辑（fetcher，scheduler）
|   |—— static/         # 前端代码（HTML，JS）
|—— tests/              # pytest 测试用例
|—— Dockerfile
```

## 📝 开发说明
- 数据清理：DELETE /articles/clean?day=30 可清理 30 天前的已读且为收藏文章。
- 手动同步：点击前端右上角“刷新抓取”按钮，或调用 POST /feeds/scheduler/run-now 。
