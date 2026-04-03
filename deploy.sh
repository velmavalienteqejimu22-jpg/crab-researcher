#!/bin/bash
# ==============================================
# CrabRes - 一键部署脚本
# 用法: chmod +x deploy.sh && ./deploy.sh
# ==============================================

set -e

echo "🦀 CrabRes - 部署开始"
echo "=========================="

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ 请先安装 Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# 检查 .env
if [ ! -f .env ]; then
    echo "📋 未找到 .env 文件，从模板创建..."
    cp .env.example .env
    echo "⚠️  请编辑 .env 文件填写真实的 API Key 后重新运行"
    exit 1
fi

echo "1/3 🐳 启动数据库和缓存..."
docker compose up -d postgres redis
sleep 5

echo "2/3 🐍 启动 FastAPI 后端..."
docker compose up -d api
sleep 3

echo "3/3 🎨 启动前端..."
docker compose up -d frontend 2>/dev/null || echo "   (前端镜像未构建，跳过)"

echo ""
echo "=========================="
echo "🦀 部署完成!"
echo ""
echo "📍 服务地址:"
echo "   FastAPI 后端:  http://localhost:8002"
echo "   API 文档:      http://localhost:8002/docs"
echo "   内置调度器:    已启用（每分钟扫描到期任务）"
echo "   前端 Dashboard: http://localhost:3000"
echo ""
echo "📋 快速验证:"
echo "   curl http://localhost:8002/"
echo "   curl http://localhost:8002/api/system/health"
echo ""
echo "🛑 停止所有服务:"
echo "   docker compose down"
