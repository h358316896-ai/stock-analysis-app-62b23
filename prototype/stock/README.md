# StockAI `/stock` 原型

这是一个轻量的 HTML/CSS/JS 原型，用于演示 `kunhuang.top/stock` 首屏与快速筛选交互。

文件:

- `index.html` — 原型页面
- `styles.css` — 样式
- `app.js` — 假数据与交互脚本

快速预览（在项目根目录运行）:

```bash
python -m http.server 8000
# 然后在浏览器打开 http://localhost:8000/prototype/stock/
```

下一步建议:

- 用真实行情数据替换 `app.js` 的假数据（从后端或第三方 API 拉取）。
- 用图表库（如 `Chart.js` 或 `TradingView` 小部件）绘制 K 线图与深度图。
- 根据 A/B 测试将首屏进一步精简以提升 LCP。

运行本地行情代理（可选，提供真实行情）:

```bash
# 1) 创建并激活虚拟环境（推荐）
python -m venv .venv
.\.venv\Scripts\activate
# 2) 安装依赖
pip install -r requirements.txt
# 3) 启动代理
python proxy_server.py
# 代理启动后，页面会向 http://localhost:5000/quote 请求数据
```

注意：`proxy_server.py` 使用 `yfinance` 取得数据，适合本地开发与演示，生产环境建议在后端做更完备的数据缓存与速率控制。

可选：使用 Node.js 代理（当本机无 Python 或偏好 Node 时）

```bash
cd node_proxy
npm install
npm start
# Node 代理默认监听 http://localhost:5000
```

说明：Node 代理使用 `yahoo-finance2` 获取行情与历史 OHLC 数据，提供与 Python 代理相同的 `/quote` 与 `/history` 接口。

SEO 与 埋点（快速指南）

1. Google Analytics / GA4
	- 在 `index.html` 已添加 GA4 占位脚本，默认 ID 为 `G-XXXXXXX`。请替换为你的实际 Measurement ID。若不使用 GA，请移除相关脚本。

2. 结构化数据
	- 已嵌入简单的 `WebSite` JSON-LD（`index.html`）。针对文章、产品页或组织信息可扩展为 `Article`、`Product`、`Organization` 等 schema。

3. Sitemap / robots
	- 已在原型中添加 `sitemap.xml` 与 `robots.txt`（位于 `prototype/stock/`），生产部署时请放置在站点根目录并确保 `sitemap.xml` 可被搜索引擎访问。

4. 页面级 SEO
	- 为重要页面补充独立 `title`、`meta description` 与 `canonical`。首页与 `/stock` 建议分别使用业务核心关键词并添加 Open Graph 图片资源。

5. 事件埋点（建议）
	- 埋点建议包括：`enter_terminal`（进入行情终端）、`start_trial`（点击试用）、`subscribe`（订阅付费）、`search_symbol`（输入并查询股票）。在 `app.js` 中可以在关键交互处调用 `gtag('event', ...)` 触发这些事件。

示例：在用户点击查询时发送事件（把下面代码放到 `app.js` 的查询处理处）:

```js
if(window.gtag){ gtag('event','search_symbol',{ 'symbol': symbol, 'market': market }); }
```

6. 后续建议
	- 将 `sitemap.xml` 提交到 Google Search Console；配置 `robots.txt` 与 Hreflang（若多语言）；为关键页面添加结构化 `BreadcrumbList` 以增加搜索结果展示概率。

7. 安全与部署
   - 已添加 `security.txt`（`prototype/stock/security.txt`）和基本页面安全元数据（`Content-Security-Policy`、`Referrer-Policy`）。生产部署时请根据实际域名与外部资源调整 CSP。
   - 已添加 GitHub Actions CI 流程：`.github/workflows/stock-cicd.yml`，会在推送或 PR 时安装 node 依赖、构建代理 Docker 镜像并验证关键文件。
   - 已配置 GitHub Pages 自动部署：当 `main` 分支有更新时，CI 会把 `prototype/stock` 发布到 `gh-pages` 分支。
   - 若你希望，我可以继续添加 Netlify / Vercel 部署脚本或自动环境变量配置。
使用 Docker（推荐，无需在本机安装 Python 或 Node）

```bash
# 在项目原型目录下运行（含 node 代理与 nginx 静态站点）
cd prototype/stock
docker compose up --build -d

# 访问原型（nginx 静态服务）：
http://localhost:8000/prototype/stock/
# 代理接口（示例）：
http://localhost:5000/quote?symbol=600519&market=cn

# 停止并移除容器：
docker compose down
```

注意：如果你的 Docker 在非本机（远端）运行，请根据实际主机的端口映射调整访问地址。如果需要我尝试在当前环境运行 `docker compose up` 并检索日志，请确认环境可用或我将继续下一项优化工作。
