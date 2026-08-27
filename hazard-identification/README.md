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

`hazard_info` 对应隐患识别出的基本信息和处理上下文，不代表已经写入业务台账。图片不能确认的责任人、责任部门、整改时限、重点隐患和集团统计字段返回空值，并在 `manual_review_items` 中说明原因。

AI 分析会重新读取原始图片作为证据，并输出重点观察位置、风险判断、可能影响、可能原因、关键发现和处理建议。创建和详情接口同时返回 `regions` 区域坐标，包含归一化 `bbox` 和近似 `polygon`；它们用于前端标记和局部截取，不等同于像素级分割掩码。

接口字段见 [API.md](./API.md)。
