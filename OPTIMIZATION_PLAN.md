# 工程分阶段优化方案（Lumina AI Retouch）

本文档用于记录当前项目的分阶段优化方案，覆盖架构重构、安全加固、代码质量与测试、部署与多环境配置等内容。目标是在不打断现有功能的前提下，按优先级逐步提升可维护性与安全性。

## 1. 项目现状概览（基于当前代码库）

### 1.1 技术栈与结构
- 前端：Vite + React + TypeScript（入口：[index.tsx](file:///home/ivan/reimagine-photo-0.0.1/index.tsx)，主组件：[App.tsx](file:///home/ivan/reimagine-photo-0.0.1/App.tsx)）
- 后端：FastAPI（单文件：[server.py](file:///home/ivan/reimagine-photo-0.0.1/server.py)）
- 前后端交互：前端通过服务层调用后端接口（[services/gemini.ts](file:///home/ivan/reimagine-photo-0.0.1/services/gemini.ts)）
- 数据落地：SQLite + 本地文件（默认 `./data`）
- API 文档：FastAPI 自带 OpenAPI/Swagger（默认 `/docs`、`/openapi.json`）

### 1.2 当前主要风险点
- CORS 全开放：后端使用 `allow_origins=["*"]`（见 [server.py](file:///home/ivan/reimagine-photo-0.0.1/server.py) 的 CORS 中间件配置）。
- 前端注入敏感信息风险：Vite 配置存在把 `GEMINI_API_KEY` 注入前端构建产物的行为（[vite.config.ts](file:///home/ivan/reimagine-photo-0.0.1/vite.config.ts)）。
- 仓库中存在硬编码 API Key：测试脚本内包含明文 key（[test_gemini_image.py](file:///home/ivan/reimagine-photo-0.0.1/test_gemini_image.py)）。
- 后端代码集中在单文件，功能耦合度高：难以在不引入回归的情况下迭代认证/限流/中间件等能力。
- 前端/后端缺少统一的 Lint/Format/Test 基线：难以确保重构质量与一致性。

## 2. 总体原则与目标

### 2.1 总体原则
- 安全优先：先止血（密钥与访问边界），再结构化重构。
- 最小影响：每个阶段尽量保持 API 行为稳定，避免大爆炸式重写。
- 可回滚：每一阶段的改动应具备清晰的回滚点（配置切换/中间件开关/分支发布）。
- 可验证：每一阶段至少提供关键路径的自动化校验或人工验收清单。

### 2.2 目标状态（最终）
- 前后端职责清晰、可独立部署：前端静态资源与后端 API 分离，统一通过反向代理对外暴露。
- API 安全：HTTPS、合理的 CORS、对写接口具备鉴权策略；如采用 Cookie 身份态则具备 CSRF 防护。
- 质量与可维护：前端 ESLint/Prettier/TypeScript 严格化；后端测试基线（pytest）与关键接口覆盖。
- 多环境：dev/test/prod 配置清晰，支持不同域名、不同后端地址、不同密钥与限流策略。

## 3. 分阶段落地计划

### 阶段 0：安全止血（优先级最高）

#### 目标
先解决最容易造成“泄露/滥用/被攻击”的问题，保持功能不变或影响最小。

#### 建议动作
- 移除前端注入密钥：不把任何后端密钥/第三方调用 key 通过 Vite `define` 打进前端。
- 清理硬编码密钥：将明文 key 改为从环境变量读取，并避免提交真实 key。
- CORS 收敛：从 `*` 改为白名单；开发环境只允许本机前端地址，生产环境只允许生产域名。
- `/proxy_image` 风险控制：强化 URL 校验与访问限制，避免被当作开放代理使用。
- 上传与生成接口的基本防护：限制文件大小与类型、合理超时、失败信息最小化。

#### 验收标准
- 构建产物不包含任何 API Key 字样。
- 生产环境 CORS 仅允许指定域名；开发环境可正常联调。
- 仓库中不存在明文 API Key。
- `/proxy_image` 不可被用于访问内网地址或非预期协议。

### 阶段 1：后端模块化与分层（保持 API 行为不变）

#### 目标
将单文件后端拆分为可维护的分层结构，为后续鉴权/限流/日志/异常处理做铺垫。

#### 拆分建议（与当前功能边界对齐）
- routers/records：记录与日志相关接口（`/records*`、`/logs`、`/records/{id}/images`）
- routers/media：媒体处理（`/preview`、`/convert`、`/proxy_image`、静态文件挂载）
- routers/analyze：分析（`/analyze`、`/analyze_stream`）
- routers/smart：智能工作流（`/smart/start`、`/smart/answer`、`/smart/generate`）
- routers/edit：编辑生成（`/magic_edit`）
- core/config：集中配置与环境变量读取
- core/db：sqlite 连接与初始化

#### 验收标准
- 对外 API 路径与请求/响应格式保持一致。
- 启动方式保持一致（`python server.py` 或 `uvicorn`）。
- 新增的模块边界清晰且无循环依赖。

### 阶段 2：API 认证与 CSRF（按业务模型选择）

#### 目标
为“写接口”和“高成本接口”（生成/编辑）增加身份与权限边界，防止滥用与资源盗刷。

#### 推荐策略（从轻到重）
- 方案 A（轻量，适合单租户/内部部署）：对写接口要求 `X-API-Key` 或 `Authorization: Bearer <server_token>`。
- 方案 B（标准，适合多用户）：引入登录与 JWT（需要用户体系、刷新/撤销机制、审计与风控策略）。

#### CSRF 适用范围
- 若采用 Cookie Session 作为身份态，必须配套 CSRF（Token/双重提交/SameSite 策略等）。
- 若采用 Bearer Token 且不依赖浏览器自动携带 Cookie，CSRF 不是主要矛盾，但仍应防 XSS 与 Token 泄露。

#### 验收标准
- 未携带鉴权信息的写接口请求在生产环境拒绝。
- 鉴权失败返回统一且不泄露内部细节的错误响应。
- 鉴权策略可通过环境变量/配置开关进行启停（便于过渡）。

### 阶段 3：代码质量与测试基线（为增量重构护航）

#### 前端（建议）
- ESLint + Prettier：统一规范，避免格式与风格争议导致的无效 diff。
- TypeScript 严格化：分阶段开启 `strict` 及相关规则，逐步清除 `any` 与隐式类型问题。
- 测试：引入 Vitest + React Testing Library，优先覆盖关键流程（上传、分析状态机、生成链路的错误处理）。

#### 后端（建议）
- pytest：关键接口的请求/响应与异常路径覆盖。
- 关键路径：`/preview`、`/convert`、`/proxy_image`、`/analyze`、`/magic_edit`、`/smart/*`。

#### 验收标准
- 每次合并/发布前具备可重复的 `typecheck` 与 `lint` 校验。
- 至少关键路径测试通过（不追求一次性全覆盖率）。

### 阶段 4：部署、HTTPS 与多环境

#### 目标
实现前后端完全分离部署，并通过 Nginx/Ingress 统一处理 HTTPS、跨域与路由。

#### 推荐形态
- TLS 终止：交给 Nginx/Ingress；后端保持内网 HTTP。
- 路由规划：
  - `/`：前端静态资源
  - `/api/*`：反向代理到 FastAPI
- 多环境：
  - 前端：以 `VITE_API_BASE_URL` 等变量区分环境
  - 后端：以环境变量区分密钥、外部模型 endpoint、CORS 白名单、限流参数、数据目录等

#### 验收标准
- 生产访问为 HTTPS，HSTS/安全头可配置。
- 前端调用使用相对路径或由配置注入 API Base URL，避免写死端口与 hostname。
- dev/test/prod 配置可一键切换，且不需要改代码。

## 4. 实施顺序建议（与风险匹配）
- 先做阶段 0：最快降低泄露与滥用风险。
- 再做阶段 1：降低后续引入安全与质量能力的成本。
- 阶段 2/3 可并行：鉴权与测试互相支撑。
- 最后做阶段 4：部署与环境治理，在能力齐备后落地更稳定。

## 5. 变更影响面提示（便于评估）
- 前端风险点集中在：[vite.config.ts](file:///home/ivan/reimagine-photo-0.0.1/vite.config.ts)、[services/gemini.ts](file:///home/ivan/reimagine-photo-0.0.1/services/gemini.ts)
- 后端风险点集中在：[server.py](file:///home/ivan/reimagine-photo-0.0.1/server.py)
- 需要立即关注的泄露点：[test_gemini_image.py](file:///home/ivan/reimagine-photo-0.0.1/test_gemini_image.py)

