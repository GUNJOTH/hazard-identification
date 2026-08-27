# 隐患识别后端

本项目只提供隐患图片识别后端。

处理流程：

```text
同一隐患的多张图片 -> 多模态识别 -> 隐患规则库检索 -> 隐患内容分析 -> 处理建议
```

## 启动

在已配置密钥的 PowerShell 窗口启动：

```powershell
$env:VISION_API_KEY = '<vision-api-key>'
$env:DIFY_API_KEY = '<dify-knowledge-base-api-key>'
$env:DIFY_HAZARD_RULES_DATASET_ID = '<hazard-rules-dataset-id>'
uv run uvicorn python_app.main:app --host 0.0.0.0 --port 8787
```

在线文档：`http://127.0.0.1:8787/docs`

## 独立前端预览

项目内置一个不依赖 GRP、Vue 或 npm 的纯 HTML/CSS/JS 预览页。后端启动后访问：

`http://127.0.0.1:8787/demo/`

页面分为隐患记录列表页和隐患分析详情页：列表页展示 5 条记录，点击记录后进入分析页，查看隐患信息、图片证据、知识库依据、AI 分析结论和处理建议。当前页面不进行填单，也不放图片上传入口；图片上传接口仅用于后端创建新的识别记录。

## 主要输出

列表接口保持原有字段不变。详情接口按 v3 返回五个前端直接渲染的区块：`basic`（基础信息）、`media`（识别图像与隐患部位）、`evidence`（法规和企业规则依据）、`findings`（隐患识别结果）和 `suggestion`（风险影响、整改建议和建议时限）。

详情中的 `media.images[].regions[].bbox` 是归一化 0~1 的区域坐标，用于前端标注和局部放大；它不是像素级分割掩码。详情接口内部执行或读取缓存分析，前端不需要再调用单独的分析接口。

接口字段见 [API.md](./API.md)。
