#!/bin/bash

# LUMINA AI 停止脚本
# 停止所有正在运行的服务

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}[停止] 正在关闭 LUMINA AI 服务...${NC}"

# 从 PID 文件停止
if [ -f .backend.pid ]; then
    BACKEND_PID=$(cat .backend.pid)
    kill $BACKEND_PID 2>/dev/null && echo -e "${GREEN}[成功] 后台服务已停止 (PID: $BACKEND_PID)${NC}"
    rm -f .backend.pid
fi

if [ -f .frontend.pid ]; then
    FRONTEND_PID=$(cat .frontend.pid)
    kill $FRONTEND_PID 2>/dev/null && echo -e "${GREEN}[成功] 前端服务已停止 (PID: $FRONTEND_PID)${NC}"
    rm -f .frontend.pid
fi

# 根据端口查找并停止进程（确保清理干净）
echo -e "${YELLOW}[检查] 清理残留进程...${NC}"

# 停止占用 8000 端口的进程
BACKEND_PORT_PIDS=$(lsof -ti:8000 2>/dev/null)
if [ ! -z "$BACKEND_PORT_PIDS" ]; then
    for pid in $BACKEND_PORT_PIDS; do
        kill -9 $pid 2>/dev/null && echo -e "${GREEN}[成功] 已强制停止占用端口 8000 的进程 (PID: $pid)${NC}"
    done
fi

# 停止占用 3000 端口的进程
FRONTEND_PORT_PIDS=$(lsof -ti:3000 2>/dev/null)
if [ ! -z "$FRONTEND_PORT_PIDS" ]; then
    for pid in $FRONTEND_PORT_PIDS; do
        kill -9 $pid 2>/dev/null && echo -e "${GREEN}[成功] 已强制停止占用端口 3000 的进程 (PID: $pid)${NC}"
    done
fi

echo -e "${GREEN}所有服务已关闭${NC}"
