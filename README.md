# StockAI — 专业A股智能分析平台

实时行情 · 主力追踪 · AI选股 · 龙虎榜 · 涨停复盘

## 线上地址

- 首页: https://kunhuang.top/
- 行情终端: https://kunhuang.top/stock
- API 后端: Railway 部署 (stock-analysis-app-production-da60.up.railway.app)

## 项目结构

```
├── index.html          # 品牌首页 — 产品展示、核心优势、FAQ
├── stock/
│   └── index.html      # 行情终端 — K线图表、AI分析、资金流向、北向资金等
├── manifest.json       # PWA 配置
├── archive/            # 旧版文件归档
├── prototype/          # 早期原型
│   └── stock/
│       └── backtest/   # Python 回测引擎（待集成）
└── .github/
    └── workflows/      # GitHub Actions CI/CD
```

## 技术栈

- **前端**: 纯 HTML/CSS/JS (无框架，极致性能)
- **图表**: Chart.js + chartjs-chart-financial (K线图)
- **后端**: Flask (Python) 部署在 Railway
- **AI 分析**: 多引擎架构 (DeepSeek V4 + Claude Opus 4.8 + GPT-4o)
- **数据源**: 全球交易所实时数据

## 本地开发

```bash
# 直接打开 index.html 或使用本地服务器
python -m http.server 8000
# 访问 http://localhost:8000
```

## 部署

- 静态页面部署到 GitHub Pages / Vercel / Netlify
- API 通过 Railway 运行 Flask 后端
- CI/CD 通过 GitHub Actions 自动部署
