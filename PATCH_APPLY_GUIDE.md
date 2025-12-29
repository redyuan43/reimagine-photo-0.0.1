# API CORS 修复补丁应用指南

## 📋 补丁概述

此补丁修复了前端从不同网络地址访问时的 CORS 跨域问题，通过动态获取主机名来构建 API 请求地址。

**问题描述：**
- 原代码硬编码了 `http://localhost:8000` 或 `http://0.0.0.0:8000`
- 当从局域网 IP（如 `http://192.168.31.10:3000`）访问时会触发 CORS 错误
- 浏览器阻止跨域请求，导致前端无法访问后端 API

**解决方案：**
- 使用 `window.location.hostname` 动态获取当前页面主机名
- 确保前后端使用相同的主机名，避免跨域问题
- 添加详细的日志输出，便于问题排查

## 📦 补丁内容

### 修改的文件：
1. **services/gemini.ts** (6处修改)
   - 新增 `getApiBaseUrl()` 函数
   - 更新所有 API 调用地址

2. **components/DownloadPage.tsx** (1处修改)
   - 更新图片转换 API 调用

3. **server.py** (6处修改)
   - 新增所有 API 端点的详细日志
   - 优化服务启动信息输出

## 🚀 应用补丁

### 方法1: 使用 Git apply (推荐)

```bash
# 进入项目目录
cd /path/to/your/project

# 应用补丁
git apply api-cors-fix.patch

# 验证修改
git diff

# 如果确认无误，提交修改
git add .
git commit -m "Fix: 修复API跨域问题，使用动态主机名"
```

### 方法2: 使用 patch 命令

```bash
# 进入项目目录
cd /path/to/your/project

# 应用补丁（使用 -p1 参数）
patch -p1 < api-cors-fix.patch

# 验证修改
git diff
```

### 方法3: 手动应用

如果自动应用失败，可以参考补丁内容手动修改：

#### 1. 修改 `services/gemini.ts`

在文件顶部添加 API 配置函数：

```typescript
// 在 import 语句后添加
const getApiBaseUrl = () => {
  if (typeof window !== 'undefined') {
    return `http://${window.location.hostname}:8000`;
  }
  return 'http://localhost:8000';
};
```

替换所有 API 调用：
- `http://localhost:8000/xxx` → `${getApiBaseUrl()}/xxx`
- `http://0.0.0.0:8000/xxx` → `${getApiBaseUrl()}/xxx`

#### 2. 修改 `components/DownloadPage.tsx`

找到 convert API 调用处：
```typescript
// 修改前
const res = await fetch('http://localhost:8000/convert', { method: 'POST', body: fd });

// 修改后
const apiUrl = `http://${window.location.hostname}:8000/convert`;
const res = await fetch(apiUrl, { method: 'POST', body: fd });
```

#### 3. 修改 `server.py`

为每个 API 端点添加日志，参考补丁文件中的具体修改。

## ✅ 验证修改

### 1. 检查文件修改

```bash
# 查看修改的文件
git status

# 查看具体修改内容
git diff services/gemini.ts
git diff components/DownloadPage.tsx
git diff server.py
```

### 2. 测试运行

```bash
# 启动服务
./start-venv.sh

# 访问前端（使用局域网IP）
# 浏览器打开: http://192.168.31.10:3000
```

### 3. 查看日志输出

**浏览器控制台** (F12 → Console):
```
[API] 开始图片分析请求
[API] 文件名: test.jpg
[API] 目标地址: http://192.168.31.10:8000/analyze_stream  ✅
```

**后端终端**:
```
============================================================
[/analyze_stream] SSE 收到分析请求
[/analyze_stream] 图片字节数: 123456
[/analyze_stream] 请求来源: 前端
============================================================
```

## 🔍 故障排查

### 问题1: 补丁应用失败

**错误信息：**
```
error: patch failed: services/gemini.ts:55
```

**解决方案：**
1. 检查文件是否已经被修改过
2. 使用 `git apply --reject` 查看冲突部分
3. 手动应用补丁内容

### 问题2: 仍然出现 CORS 错误

**检查清单：**
- [ ] 前端是否已重新编译？清除浏览器缓存（Ctrl+Shift+R）
- [ ] 后端服务是否重启？
- [ ] 浏览器控制台中的 API 地址是否正确？
- [ ] 前后端端口是否都正确监听？

### 问题3: 日志不显示

**检查：**
- 后端：确认 `server.py` 的日志代码已添加
- 前端：打开浏览器开发者工具，确认 Console 标签已启用

## 📝 技术细节

### getApiBaseUrl() 函数工作原理

```typescript
const getApiBaseUrl = () => {
  if (typeof window !== 'undefined') {
    // 运行在浏览器环境
    return `http://${window.location.hostname}:8000`;
  }
  // 运行在 Node.js 环境（SSR）
  return 'http://localhost:8000';
};
```

**示例：**
| 前端访问地址 | window.location.hostname | API 地址 |
|-------------|-------------------------|---------|
| http://localhost:3000 | localhost | http://localhost:8000 |
| http://192.168.31.10:3000 | 192.168.31.10 | http://192.168.31.10:8000 |
| http://127.0.0.1:3000 | 127.0.0.1 | http://127.0.0.1:8000 |

### 为什么这样可以解决 CORS 问题？

1. **同源策略**：浏览器要求请求的协议、域名、端口与页面一致
2. **原问题**：页面在 `http://192.168.31.10:3000`，但请求 `http://0.0.0.0:8000`（不同域名）
3. **解决后**：页面和 API 都使用 `192.168.31.10`，符合同源策略

## 📞 支持

如有问题，请：
1. 检查补丁文件内容是否完整
2. 查看项目日志输出
3. 确认网络配置正确

---

**补丁版本：** 1.0.0  
**创建日期：** 2025-12-02  
**适用版本：** reimagine-photo-0.0.1  
