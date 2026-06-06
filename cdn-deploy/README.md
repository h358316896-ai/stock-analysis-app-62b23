# StockAI 国内 CDN 部署指南

## 方案一：腾讯云 COS + CDN（推荐）

### 1. 注册开通
1. 注册腾讯云账号：https://cloud.tencent.com
2. 开通 COS 对象存储 + CDN 加速
3. 创建存储桶(Bucket)，设置为「公有读」

### 2. 上传文件
将 `cdn-deploy/` 文件夹内所有文件上传到 COS 存储桶根目录

### 3. 配置
- CDN 加速域名：xxx.cos.ap-guangzhou.myqcloud.com
- 绑定自定义域名（可选）
- 开启 HTTPS

### 4. 成本估算
- 存储：约 ¥0.1/月
- CDN 流量：约 ¥0.2/GB
- 日均1000访问 ≈ ¥30/月

---

## 方案二：阿里云 OSS + CDN

### 1. 注册开通
1. 注册阿里云：https://www.aliyun.com
2. 开通 OSS + CDN
3. 创建 Bucket，设置为「公共读」

### 2. 上传文件
同上，上传 `cdn-deploy/` 内所有文件

### 3. 成本估算
- 与腾讯云相近，¥20-50/月

---

## 方案三：Railway 直接国内加速（零成本，立即生效）

不需要任何云账号，利用现有 Railway：

1. 绑定自定义域名到 Railway（在 Railway Dashboard → Settings → Domains）
2. Railway 自动提供全球 CDN

成本：¥0

---

## 文件说明

| 文件 | 说明 |
|------|------|
| index.html | 首页 |
| stock.html | 股票分析主页面 |
| media.html | 自媒体助手 |
| services.html | 服务页面 |
| manifest.json | PWA 配置 |
| sw.js | Service Worker |
