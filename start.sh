#!/bin/bash

# LUMINA AI 一键启动脚本 (Linux/macOS)
# 同时启动前端和后台服务

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  LUMINA AI - 启动中...${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# 检查 Node.js
echo -e "${YELLOW}[检查] Node.js...${NC}"
if ! command -v node &> /dev/null; then
    echo -e "${RED}[错误] 未检测到 Node.js，请先安装 Node.js${NC}"
    exit 1
fi
NODE_VERSION=$(node --version)
echo -e "${GREEN}[成功] Node.js 已安装 ($NODE_VERSION)${NC}"

# 检查 Python
echo -e "${YELLOW}[检查] Python...${NC}"
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo -e "${RED}[错误] 未检测到 Python，请先安装 Python${NC}"
    exit 1
fi
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
else
    PYTHON_CMD=python
fi
PYTHON_VERSION=$($PYTHON_CMD --version)
echo -e "${GREEN}[成功] Python 已安装 ($PYTHON_VERSION)${NC}"

# 检查 npm 依赖
echo -e "${YELLOW}[检查] npm 依赖...${NC}"
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}[安装] npm 依赖...${NC}"
    npm install
    if [ $? -ne 0 ]; then
        echo -e "${RED}[错误] npm 依赖安装失败${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}[成功] npm 依赖已就绪${NC}"

# 检查 Python 依赖
echo -e "${YELLOW}[检查] Python 依赖...${NC}"
if [ -f "requirements.txt" ]; then
    echo -e "${YELLOW}[提示] 如需安装 Python 依赖，请运行: pip install -r requirements.txt${NC}"
fi

echo ""
echo -e "${YELLOW}[启动] 后台服务 (端口 8000)...${NC}"
$PYTHON_CMD server.py &
BACKEND_PID=$!
echo -e "${GREEN}[成功] 后台服务已启动 (PID: $BACKEND_PID)${NC}"

sleep 2

echo -e "${YELLOW}[启动] 前端服务 (端口 5173)...${NC}"
npm run dev &
FRONTEND_PID=$!
echo -e "${GREEN}[成功] 前端服务已启动 (PID: $FRONTEND_PID)${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  所有服务已启动！${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "  后台服务: ${CYAN}http://localhost:8000${NC}"
echo -e "  前端服务: ${CYAN}http://localhost:5173${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}提示: 按 Ctrl+C 停止所有服务${NC}"
echo ""

# 保存 PID 到文件，方便后续停止
echo $BACKEND_PID > .backend.pid
echo $FRONTEND_PID > .frontend.pid

# 捕获 Ctrl+C 信号，优雅退出
cleanup() {
    echo ""
    echo -e "${YELLOW}[停止] 正在关闭服务...${NC}"
    
    if [ -f .backend.pid ]; then
        BACKEND_PID=$(cat .backend.pid)
        kill $BACKEND_PID 2>/dev/null
        echo -e "${GREEN}[成功] 后台服务已停止${NC}"
        rm .backend.pid
    fi
    
    if [ -f .frontend.pid ]; then
        FRONTEND_PID=$(cat .frontend.pid)
        kill $FRONTEND_PID 2>/dev/null
        echo -e "${GREEN}[成功] 前端服务已停止${NC}"
        rm .frontend.pid
    fi
    
    echo -e "${GREEN}所有服务已关闭${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 等待进程
wait
