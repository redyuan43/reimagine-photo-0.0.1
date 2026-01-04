# 故障排除指南

## 常见错误及解决方案

### 1. 图片加载失败：ERR_CONNECTION_REFUSED

**错误信息：**
```
20260104105058_gen_3df0.jpg:1 Failed to load resource: net::ERR_CONNECTION_REFUSED
```

**原因：**
- 当从另一台电脑访问时，图片 URL 使用的是相对路径 `/static/...`
- 相对路径会基于浏览器当前访问的域名，如果后端服务没有正确配置，就会导致连接被拒绝

**解决方案：**

1. **设置 SERVER_BASE_URL 环境变量**
   
   在启动后端服务时，设置 `SERVER_BASE_URL` 环境变量为可访问的完整地址：
   
   ```bash
   # 如果从局域网访问，使用服务器的局域网 IP
   export SERVER_BASE_URL="http://192.168.1.107:8000"
   
   # 或者如果使用域名
   export SERVER_BASE_URL="http://your-domain.com:8000"
   ```

2. **确保后端服务监听所有网络接口**
   
   确保后端服务绑定到 `0.0.0.0` 而不是 `127.0.0.1`，这样其他设备才能访问：
   
   ```python
   # 在 server.py 或启动脚本中
   uvicorn.run(app, host="0.0.0.0", port=8000)
   ```

3. **检查防火墙设置**
   
   确保防火墙允许 8000 端口的入站连接。

### 2. Gemini API Key 泄露错误：403 Forbidden

**错误信息：**
```
POST http://192.168.1.107:8000/smart/generate 403 (Forbidden)
Error: {"detail":"Gemini image error: {
  \"error\": {
    \"code\": 403,
    \"message\": \"Your API key was reported as leaked. Please use another API key.\",
    \"status\": \"PERMISSION_DENIED\"
  }
}"}
```

**原因：**
- Gemini API Key 被 Google 标记为泄露（可能因为提交到公共代码仓库、分享给他人等）
- Google 出于安全考虑禁用了该 API Key

**解决方案：**

1. **生成新的 API Key**
   
   - 访问 [Google AI Studio](https://makersuite.google.com/app/apikey)
   - 删除或禁用旧的 API Key
   - 创建新的 API Key
   - **重要：** 不要将 API Key 提交到公共代码仓库

2. **更新环境变量**
   
   ```bash
   # 设置新的 API Key
   export VISION_API_KEY="your_new_api_key_here"
   # 或者
   export GEMINI_API_KEY="your_new_api_key_here"
   # 或者
   export GOOGLE_API_KEY="your_new_api_key_here"
   ```

3. **使用 .env 文件（推荐）**
   
   创建 `.env` 文件（不要提交到 Git）：
   ```
   VISION_API_KEY=your_new_api_key_here
   SERVER_BASE_URL=http://192.168.1.107:8000
   ```
   
   然后在启动脚本中加载：
   ```bash
   # 使用 python-dotenv
   pip install python-dotenv
   ```
   
   ```python
   from dotenv import load_dotenv
   load_dotenv()
   ```

### 3. 跨设备访问问题

**问题描述：**
- 在本机访问正常，但从另一台电脑访问时无法显示图片
- 出现"生成失败"的报错

**解决方案：**

1. **配置 SERVER_BASE_URL**
   
   这是最重要的配置。确保 `SERVER_BASE_URL` 指向其他设备可以访问的地址：
   
   ```bash
   # 获取服务器的局域网 IP
   # Linux/Mac:
   ip addr show | grep "inet " | grep -v 127.0.0.1
   
   # Windows:
   ipconfig
   
   # 然后设置环境变量
   export SERVER_BASE_URL="http://<your-server-ip>:8000"
   ```

2. **检查 CORS 配置**
   
   确保后端允许来自其他设备的跨域请求。检查 `server.py` 中的 CORS 配置：
   
   ```python
   # 应该允许所有来源或特定来源
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["*"],  # 或特定域名列表
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```

3. **验证网络连接**
   
   从客户端设备测试是否能访问后端：
   ```bash
   # 在客户端设备上执行
   curl http://<server-ip>:8000/openapi.json
   ```

### 4. 修复后的代码变更

**已修复的问题：**

1. **smart_generate 端点现在返回完整的图片 URL**
   
   修改了 `backend/routers/smart.py`，现在会：
   - 检查 `SERVER_BASE_URL` 环境变量
   - 将相对路径转换为完整的绝对 URL
   - 确保跨设备访问时图片可以正常加载

**代码变更示例：**
```python
# 修复前：返回相对路径
urls = ["/static/image.jpg"]

# 修复后：返回完整 URL
base = os.getenv("SERVER_BASE_URL", "http://localhost:8000").rstrip("/")
served_urls = [f"{base}/static/{Path(p).name}" for p in local_paths]
# 结果：["http://192.168.1.107:8000/static/image.jpg"]
```

## 快速检查清单

在遇到问题时，按以下顺序检查：

- [ ] `SERVER_BASE_URL` 环境变量是否设置正确？
- [ ] 后端服务是否绑定到 `0.0.0.0` 而不是 `127.0.0.1`？
- [ ] 防火墙是否允许 8000 端口？
- [ ] Gemini API Key 是否有效且未被标记为泄露？
- [ ] 从客户端设备能否访问 `http://<server-ip>:8000/openapi.json`？
- [ ] CORS 配置是否正确？

## 测试步骤

1. **测试后端可访问性：**
   ```bash
   curl http://<server-ip>:8000/openapi.json
   ```

2. **测试图片访问：**
   ```bash
   curl http://<server-ip>:8000/static/test.jpg
   ```

3. **检查环境变量：**
   ```bash
   echo $SERVER_BASE_URL
   echo $VISION_API_KEY  # 不要显示完整 key，只检查是否设置
   ```

## 联系支持

如果以上方法都无法解决问题，请提供：
- 完整的错误日志
- 服务器和客户端的 IP 地址
- 网络配置信息
- 环境变量配置（隐藏敏感信息）

