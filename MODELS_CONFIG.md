# 模型配置说明

本文档说明项目中使用的所有 AI 模型及其配置方式。

## 模型列表

### 1. 图像分析模型 (Image Analysis)

**模型名称**: `qwen3-vl-plus`  
**服务商**: 阿里云 DashScope  
**API 地址**: 
- 环境变量: `DASHSCOPE_COMPAT_URL`
- 默认值: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- 完整端点: `{DASHSCOPE_COMPAT_URL}/chat/completions`

**配置位置**:
- `server.py:994` - `analyze_image_with_qwen3_vl_plus()` 函数
- `backend/routers/analyze.py:78` - `analyze_stream()` 函数

**使用位置**:
- `server.py:989-1079` - `analyze_image_with_qwen3_vl_plus()` 函数
- `server.py:1908-2076` - `analyze_stream()` 端点（SSE 流式分析）
- `backend/routers/analyze.py:19-62` - `/analyze` 端点
- `backend/routers/analyze.py:65-254` - `/analyze_stream` 端点（SSE）
- `server.py:1163-1174` - `_analyze_image_facts_best_effort()` 函数

**API Key**: `DASHSCOPE_API_KEY`

---

### 2. 图像编辑模型 (Image Editing)

项目支持两种图像编辑模型，按优先级选择：

#### 2.1 Google Gemini（优先）

**模型名称**: 
- 环境变量: `IMAGE_EDIT_MODEL`
- 默认值: `gemini-3-pro-image-preview`

**API 地址**:
- 环境变量: `IMAGE_EDIT_ENDPOINT` 或 `GEMINI_BASE_URL`
- 默认值: `https://generativelanguage.googleapis.com/v1beta`
- 完整端点: `{GEMINI_BASE_URL}/models/{IMAGE_EDIT_MODEL}:generateContent?key={VISION_API_KEY}`

**配置位置**:
- `server.py:1617` - `magic_edit()` 函数
- `backend/routers/edit.py:32` - `magic_edit()` 端点
- `backend/routers/smart.py:129,224,255` - `smart_start()`, `smart_answer()`, `smart_generate()` 端点

**使用位置**:
- `server.py:1601-1906` - `magic_edit()` 函数（优先使用 Gemini）
- `server.py:1541-1598` - `_gemini_image_edit_native()` 函数
- `backend/routers/edit.py:16-304` - `/magic_edit` 端点
- `backend/routers/smart.py:229-315` - `/smart/generate` 端点

**API Key**: `VISION_API_KEY` 或 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`

#### 2.2 阿里云 DashScope（备用）

**模型名称**:
- 环境变量: `IMAGE_EDIT_MODEL`
- 默认值（当使用 DashScope 时）: `qwen-image-edit-plus`

**API 地址**:
- 环境变量: `IMAGE_EDIT_ENDPOINT`
- 默认值: `https://dashscope.aliyuncs.com/api/v1`

**配置位置**:
- `server.py:65` - DashScope SDK 初始化
- `server.py:1814` - `magic_edit()` 函数（备用路径）
- `backend/routers/edit.py:199` - `magic_edit()` 端点（备用路径）

**使用位置**:
- `server.py:1802-1839` - `magic_edit()` 函数（当没有 VISION_API_KEY 时）
- `backend/routers/edit.py:187-229` - `/magic_edit` 端点（备用路径）

**API Key**: `DASHSCOPE_API_KEY`

---

### 3. 智能对话模型 (Smart LLM)

**模型名称**:
- 环境变量: `SMART_LLM_MODEL`
- 默认值: 
  - `server.py`: `gemini-2.0-flash`
  - `backend/routers/smart.py`: `gemini-2.5-flash`

**API 地址**:
- 环境变量: `GEMINI_BASE_URL`
- 默认值: `https://generativelanguage.googleapis.com/v1beta`
- 完整端点: `{GEMINI_BASE_URL}/models/{SMART_LLM_MODEL}:generateContent?key={VISION_API_KEY}`

**配置位置**:
- `server.py:1452` - `_llm_clarify_next()` 函数
- `backend/routers/smart.py:105,206` - `smart_start()`, `smart_answer()` 端点

**使用位置**:
- `server.py:1451-1517` - `_llm_clarify_next()` 函数（用于意图澄清和对话）
- `backend/routers/smart.py:49-53` - `/smart/start` 端点
- `backend/routers/smart.py:159-163` - `/smart/answer` 端点

**API Key**: `VISION_API_KEY` 或 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`

---

## 环境变量配置

在 `.env.local` 或 `.local.env` 文件中配置：

```bash
# ========== API Keys ==========
# Google Gemini API Key (用于图像编辑和智能对话)
VISION_API_KEY=your_gemini_api_key_here
# 或使用
GEMINI_API_KEY=your_gemini_api_key_here
# 或使用
GOOGLE_API_KEY=your_gemini_api_key_here

# 阿里云 DashScope API Key (用于图像分析)
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# ========== 模型配置 ==========
# 图像编辑模型（Google Gemini）
IMAGE_EDIT_MODEL=gemini-3-pro-image-preview

# 智能对话模型（Google Gemini）
SMART_LLM_MODEL=gemini-2.0-flash
# 或
SMART_LLM_MODEL=gemini-2.5-flash

# ========== API 地址配置 ==========
# Google Gemini API 地址
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta

# 图像编辑端点（可选，用于自定义 Gemini 端点）
IMAGE_EDIT_ENDPOINT=https://generativelanguage.googleapis.com/v1beta

# 阿里云 DashScope 兼容模式地址（用于图像分析）
DASHSCOPE_COMPAT_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 阿里云 DashScope 标准地址（用于图像编辑，备用）
IMAGE_EDIT_ENDPOINT=https://dashscope.aliyuncs.com/api/v1
```

---

## 模型选择逻辑

### 图像编辑模型选择

1. **优先使用 Google Gemini**:
   - 如果设置了 `VISION_API_KEY`（或 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`）
   - 使用模型: `IMAGE_EDIT_MODEL`（默认: `gemini-3-pro-image-preview`）
   - API 地址: `GEMINI_BASE_URL` 或 `IMAGE_EDIT_ENDPOINT`

2. **备用使用阿里云 DashScope**:
   - 如果没有设置 `VISION_API_KEY`
   - 使用模型: `IMAGE_EDIT_MODEL`（默认: `qwen-image-edit-plus`）
   - API 地址: `IMAGE_EDIT_ENDPOINT`（默认: `https://dashscope.aliyuncs.com/api/v1`）

### 图像分析模型

- 固定使用: `qwen3-vl-plus`
- 需要: `DASHSCOPE_API_KEY`
- API 地址: `DASHSCOPE_COMPAT_URL`

### 智能对话模型

- 固定使用: `SMART_LLM_MODEL`（默认: `gemini-2.0-flash` 或 `gemini-2.5-flash`）
- 需要: `VISION_API_KEY`（或 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`）
- API 地址: `GEMINI_BASE_URL`

---

## 代码位置总结

| 功能 | 模型 | 配置文件位置 | 使用位置 |
|------|------|------------|---------|
| 图像分析 | `qwen3-vl-plus` | `server.py:994`<br>`backend/routers/analyze.py:78` | `server.py:989-1079`<br>`backend/routers/analyze.py:19-254` |
| 图像编辑（Gemini） | `gemini-3-pro-image-preview` | `server.py:1617`<br>`backend/routers/edit.py:32` | `server.py:1601-1906`<br>`backend/routers/edit.py:16-304` |
| 图像编辑（DashScope） | `qwen-image-edit-plus` | `server.py:1814`<br>`backend/routers/edit.py:199` | `server.py:1802-1839`<br>`backend/routers/edit.py:187-229` |
| 智能对话 | `gemini-2.0-flash`<br>`gemini-2.5-flash` | `server.py:1452`<br>`backend/routers/smart.py:105,206` | `server.py:1451-1517`<br>`backend/routers/smart.py:49-163` |

---

## 注意事项

1. **模型名称硬编码**: 
   - `qwen3-vl-plus` 在代码中硬编码，无法通过环境变量修改
   - 其他模型可通过环境变量 `IMAGE_EDIT_MODEL` 和 `SMART_LLM_MODEL` 配置

2. **API 地址优先级**:
   - Google Gemini: `IMAGE_EDIT_ENDPOINT` > `GEMINI_BASE_URL` > 默认值
   - DashScope: `IMAGE_EDIT_ENDPOINT` > 默认值

3. **API Key 优先级**:
   - Google Gemini: `VISION_API_KEY` > `GEMINI_API_KEY` > `GOOGLE_API_KEY`

4. **环境变量加载**:
   - 后端启动时自动从 `.local.env` 或 `.env.local` 加载环境变量
   - 参考: `server.py:23-40` - `_load_local_env()` 函数

