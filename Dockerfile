# ============================================================
# Serendipity Navigation - 多阶段构建镜像
# 阶段1: Node 构建 Vue 前端 -> webapp/dist
# 阶段2: Python 运行 FastAPI 后端, 同源托管前端
# ============================================================

# ---------- 阶段 1: 构建前端 ----------
FROM node:22-alpine AS webapp-build
WORKDIR /app/webapp

# 先拷贝依赖清单, 利用 Docker 层缓存
COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci

# 再拷贝源码并构建
COPY webapp/ ./
RUN npm run build

# ---------- 阶段 2: 后端运行环境 ----------
FROM python:3.11-slim
WORKDIR /app

# 先装依赖, 利用 Docker 层缓存
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# 拷贝后端代码与前端构建产物
COPY backend/ ./backend/
COPY --from=webapp-build /app/webapp/dist ./webapp/dist

WORKDIR /app/backend
EXPOSE 8000

# 环境变量由部署平台注入 (AMAP_KEY 等), 无需 .env 文件
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
