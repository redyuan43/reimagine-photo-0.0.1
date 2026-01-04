#!/bin/bash

# LUMINA AI systemd 服务安装脚本

echo "正在安装 LUMINA AI systemd 服务..."

# 确保项目目录权限正确（归属于 nx 用户）
sudo chown -R nx:nx /home/nx/reimagine-photo-0.0.1

# 复制服务文件到系统目录
sudo cp /home/nx/reimagine-photo-0.0.1/lumina-ai.service /etc/systemd/system/

# 重新加载 systemd
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable lumina-ai.service

echo ""
echo "服务安装完成！"
echo ""
echo "常用命令："
echo "  启动服务:    sudo systemctl start lumina-ai"
echo "  停止服务:    sudo systemctl stop lumina-ai"
echo "  查看状态:    sudo systemctl status lumina-ai"
echo "  查看日志:    sudo journalctl -u lumina-ai -f"
echo "  禁用自启:    sudo systemctl disable lumina-ai"
echo ""
echo "如果需要立即启动（不重启系统），请运行："
echo "  sudo systemctl start lumina-ai"
