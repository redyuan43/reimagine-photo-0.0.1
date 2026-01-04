# LUMINA AI 服务管理命令

## 启动服务
sudo systemctl start lumina-ai

## 停止服务
sudo systemctl stop lumina-ai

## 重启服务
sudo systemctl restart lumina-ai

## 查看服务状态
sudo systemctl status lumina-ai

## 查看实时日志
sudo journalctl -u lumina-ai -f

## 查看最近日志
sudo journalctl -u lumina-ai -n 50

## 启用开机自启（已自动设置）
sudo systemctl enable lumina-ai

## 禁用开机自启
sudo systemctl disable lumina-ai

## 重新加载服务配置
sudo systemctl daemon-reload

## 检查服务是否开机自启
systemctl is-enabled lumina-ai
