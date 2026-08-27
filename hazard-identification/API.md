# 隐患识别 API 接口文档（v2）

> **版本说明**：v2 收敛为两个接口 —— 列表、详情。
> 1. **列表接口契约不变**（与 v1 完全一致，前端已依赖，不要改动）。
> 2. **详情接口为 v2 重设计**：一次请求返回详情报告页所需的全部数据（基础信息、图像标注、法规/规则依据、多模态识别结果、风险分析与建议），前端不再调用分析接口。
> 3. 原 `POST /hazard-identifications/{id}/analysis` 不再作为前端依赖：分析结论由详情接口统一返回。详情接口内部执行/读取分析，并建议**按记录缓存结果**（重复请求返回相同内容，分析为只读，不修改已识别字段，不重复计费）。

---

## 1. 总览

- **Base URL**：智能体配置地址 `SY_AG_URL`，未配置时缺省 `http://172.20.2.99:8787`，统一前缀 `/api/v1`。
- **返回格式**：JSON；成功一律 2xx；错误见 [第 7 节错误码](#7-错误码)。
- **时间格式**：ISO 8601 UTC 字符串，如 `2026-08-26T04:30:00Z`。
- **空值约定**：字段为 `null` 表示当前图片/上下文/知识库不能可靠确认，前端展示"待确认"或 `-`，**不要当作空字符串处理**。
- **图片地址**：`url` / `thumbnail_url` / `images[].url` 均为相对地址（`/api/v1/...`），前端拼上 Base URL 使用。

## 2. 接口总览

| 接口 | 方法 | 路径 | 用途 |
| --- | --- | --- | --- |
| 隐患记录列表 | GET | `/api/v1/hazard-identifications` | 分页隐患摘要（**不变**） |
| 隐患记录详情 | GET | `/api/v1/hazard-identifications/{id}` | 完整分析报告（**v2 新增内容**） |

> 图片接口 `GET /api/v1/hazard-identifications/{id}/images/{index}` 沿用（建议支持可选的 `?w=` `?h=` 尺寸参数用于缩略图，见 [6.图片接口](#6-图片接口)）。`POST /api/v1/hazard-identifications`（创建识别）暂不在本次前端流程内，按现状处理即可。

---

## 3. 隐患记录列表（不变）

```http
GET /api/v1/hazard-identifications?page=1&page_size=20&keyword=锈蚀
```

**请求参数（query）**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `page` | int | 否 | 页码，从 1 开始，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20 |
| `keyword` | string | 否 | 关键词，模糊匹配隐患描述/设备/位置等 |

**响应**

```json
{
  "total": 5,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": "00000000-0000-4000-8000-000000000005",
      "status": "identified",
      "created_at": "2026-08-25T04:30:00Z",
      "discovery_time": "2026-08-25T04:30:00Z",
      "description": "同一处设施从多个角度可见构件锈蚀、墙面锈水和局部破损，需开展联合排查。",
      "category": "生产设备",
      "type": "设备设施事故隐患",
      "level": "一般隐患",
      "discovery_source": "隐患排查",
      "rectification_deadline": "2026-09-02",
      "location": "设备间及相邻墙体",
      "equipment_name": "管道、阀门及墙体构件",
      "image_count": 2,
      "thumbnail_url": "/api/v1/hazard-identifications/00000000-0000-4000-8000-000000000005/images/0",
      "manual_review_required": false
    }
  ]
}
```

**`items[]` 字段说明（与 v1 一致，字段不要变更）**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 隐患记录唯一标识，详情接口的路径参数 |
| `status` | string | 识别记录状态，当前固定 `identified` |
| `created_at` | string | 后端创建记录时间 |
| `discovery_time` | string | 隐患发现时间 |
| `description` | string/null | AI 生成的隐患描述；无法可靠判断时为 `null` |
| `category` | string/null | 隐患类别，见枚举 |
| `type` | string/null | 隐患类型，见枚举 |
| `level` | string/null | 隐患等级，`一般隐患` / `重大隐患`，未命中规则为 `null` |
| `discovery_source` | string | 隐患发现来源，见枚举 |
| `rectification_deadline` | string/null | 整改时限，`YYYY-MM-DD`；图片无法确认时为 `null` |
| `location` | string/null | 区域位置 |
| `equipment_name` | string/null | 设备或对象名称 |
| `image_count` | integer | 关联图片数量（多角度仍算一条记录） |
| `thumbnail_url` | string/null | 第一张图片相对地址，可直接用于 `<img src>` |
| `manual_review_required` | boolean | 是否需要人工复核 |

---

## 4. 隐患记录详情（v2 重设计）

```http
GET /api/v1/hazard-identifications/{id}
```

一次性返回详情报告页所需的全部内容。**报告页各展示区块与响应字段对应关系见 [5. 字段与原型图映射](#5-字段与原型图映射)**。

### 4.1 响应示例

```json
{
  "id": "7c3b8cae-5a3d-4ca2-bf18-0d1a7a3e31b4",
  "report_no": "HD-20260826-0001",
  "status": "identified",
  "created_at": "2026-08-26T08:00:00Z",
  "discovery_time": "2026-08-26T08:00:00Z",
  "model": "多模态隐患识别模型 v1.0",
  "analyzed_at": "2026-08-26T08:02:11Z",
  "analyzer": {
    "type": "system",
    "name": "系统自动分析"
  },
  "description": "金属构件根部存在明显锈蚀和局部破损，具体腐蚀深度待现场确认。",
  "category": "基础设施",
  "type": "设备设施事故隐患",
  "level": "一般隐患",
  "level_source": "knowledge_rule",
  "discovery_source": "图片上传识别",
  "location": "图片可见区域",
  "equipment_name": "金属立柱",
  "image_count": 2,
  "thumbnail_url": "/api/v1/hazard-identifications/7c3b8cae-5a3d-4ca2-bf18-0d1a7a3e31b4/images/0",
  "manual_review_required": false,
  "rectification_deadline": null,
  "identification_basis": "表面锈蚀严重，涂层剥落，存在腐蚀减薄风险，可能导致设备泄漏。",
  "images": [
    {
      "index": 0,
      "url": "/api/v1/hazard-identifications/7c3b8cae-5a3d-4ca2-bf18-0d1a7a3e31b4/images/0",
      "thumbnail_url": "/api/v1/hazard-identifications/7c3b8cae-5a3d-4ca2-bf18-0d1a7a3e31b4/images/0?w=128",
      "regions": [
        {
          "id": "r0-1",
          "label": "腐蚀,锈蚀区域",
          "kind": "corrosion",
          "bbox": { "x": 0.33, "y": 0.46, "width": 0.42, "height": 0.36 },
          "confidence": 0.93
        }
      ]
    },
    {
      "index": 1,
      "url": "/api/v1/hazard-identifications/7c3b8cae-5a3d-4ca2-bf18-0d1a7a3e31b4/images/1",
      "thumbnail_url": "/api/v1/hazard-identifications/7c3b8cae-5a3d-4ca2-bf18-0d1a7a3e31b4/images/1?w=128",
      "regions": []
    }
  ],
  "analysis": {
    "summary": "综合图像特征、法规与企业规则，判定为一般隐患，建议按 24 小时内定级并整改。",
    "confidence": 0.93,
    "findings": [
      {
        "description": "法兰连接处存在锈蚀、腐蚀现象",
        "reason": "检测依据：图像特征识别",
        "location": "循环水出口法兰",
        "risk_level": "high",
        "confidence": 0.93,
        "basis": ["image_feature", "law", "rule"]
      },
      {
        "description": "阀门锈蚀严重，存在泄漏风险",
        "reason": "检测依据：表面锈蚀识别",
        "location": "截止阀手轮处",
        "risk_level": "medium",
        "confidence": 0.78,
        "basis": ["image_feature", "rule"]
      },
      {
        "description": "管道保温层破损",
        "reason": "检测依据：管道保温破损识别",
        "location": "水平管道部位",
        "risk_level": "medium",
        "confidence": 0.71,
        "basis": ["image_feature", "rule"]
      }
    ],
    "risk_impacts": [
      "可能导致介质泄漏，造成设备失效",
      "存在高温热水泄漏风险，可能造成人员烫伤",
      "腐蚀加剧将导致设备参数降低，增加停机风险",
      "环境污染风险增加"
    ],
    "recommended_actions": [
      "立即清除整改部位，评估腐蚀深度",
      "对腐蚀部位进行补焊或更换受损部件",
      "表面防腐处理，恢复防护涂层",
      "加强巡检频次，重点关注腐蚀高发部位"
    ],
    "response_deadline": {
      "urgency": "urgent",
      "text": "建议 24 小时内完成风险评级并制定整改方案"
    },
    "evidence": {
      "laws": [
        {
          "title": "《中华人民共和国特种设备安全法》",
          "article": "第十三条",
          "excerpt": "特种设备使用单位应当使用符合安全技术规范要求的特种设备，并不得使用未经检验或者检验不合格的特种设备。",
          "source_url": null
        }
      ],
      "rules": [
        {
          "code": "设备通则规程-RU-01",
          "name": "设备泄漏或减薄处置规则",
          "excerpt": "设备泄漏或减薄经确认后，泄漏或减薄超过设计使用年限的 10% 或减薄 >1mm，判定为隐患。",
          "risk_level": "高风险",
          "source_url": null
        }
      ]
    }
  }
}
```

### 4.2 顶层字段说明

**与列表项一致的基础字段（内容同上文列表字段表，详情返回同一记录的完整值）：** `id`、`status`、`created_at`、`discovery_time`、`description`、`category`、`type`、`level`、`discovery_source`、`location`、`equipment_name`、`image_count`、`thumbnail_url`、`manual_review_required`、`rectification_deadline`。

**详情新增字段：**

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `report_no` | string | 是 | 报告单号，如 `HD-20260826-0001`；未生成时为 `null`，前端回退展示 `id` |
| `model` | string | 是 | 识别模型名称，如 `多模态隐患识别模型 v1.0` |
| `analyzed_at` | string | 是 | 分析完成时间；为 `null` 时前端回退 `discovery_time` → `created_at` |
| `analyzer` | object | 否 | 分析执行者，见下 |
| `analyzer.type` | string | 否 | `system`（系统自动分析）/ `manual`（人工） |
| `analyzer.name` | string | 否 | 展示名称，如 `系统自动分析`（人工时为人名） |
| `level_source` | string | 是 | 等级判定来源：`knowledge_rule`（知识库规则）/ `model`（模型识别）/ 其他说明文本 |
| `identification_basis` | string/null | 是 | 图像识别依据摘要（原型图第 2 部分底部"识别依据"文本），如 `表面锈蚀严重，涂层剥落…` |
| `images` | array | 否 | 图片列表（详见下） |
| `analysis` | object | 否 | 多模态分析报告（详见下） |

### 4.3 `images[]` 图片与标注

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `index` | int | 否 | 图片序号，从 0 开始（多角度图片，多张属于同一条隐患） |
| `url` | string | 否 | 原图相对地址，详情页大图/预览用 |
| `thumbnail_url` | string | 是 | 缩略图相对地址；建议后端提供 `?w=&h=` 裁剪，未实现时回退 `url` |
| `regions` | array | 否 | 标注区域列表（原型图虚线框+标签），可以为空数组 |

**`regions[]`：**

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 否 | 区域唯一标识 |
| `label` | string | 否 | 标注文本，如 `腐蚀,锈蚀区域`、`设备部位`（原型图 2 右侧红色标签，及"隐患部位"蓝色标签） |
| `kind` | string | 是 | 区域类型，见枚举；前端据此决定颜色与虚线样式（如 `corrosion` 红色、`hazard_area` 蓝色） |
| `bbox` | object | 否 | 归一化坐标（左上角原点，取值范围 0~1） |
| `bbox.x` / `bbox.y` | number | 否 | 区域左上角相对图片宽高的比例 |
| `bbox.width` / `bbox.height` | number | 否 | 区域宽高相对图片宽高的比例 |
| `confidence` | number | 是 | 区域识别置信度，0~1，仅在置信度可量化时返回 |

> 前端用 bbox 在原图上叠加虚线框和标签，并裁出"隐患部位放大图"（原型图 2 右侧），后端无需额外提供裁剪后的放大图 URL。

### 4.4 `analysis` 多模态分析报告

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `summary` | string | 是 | 分析结论摘要（一句话） |
| `confidence` | number | 是 | 整体置信度，0~1 |
| `findings` | array | 否 | 多模态识别结果，**顺序即展示顺序**（原型图第 4 部分表格行，前端不另外排序） |
| `risk_impacts` | array | 否 | 风险影响分析条目（原型图 5.1 列表，顺序即展示顺序）；可为空数组 |
| `recommended_actions` | array | 否 | 整改建议条目（原型图 5.2 编号列表，任意长度） |
| `response_deadline` | object/null | 是 | 建议整改时限（原型图 5.3） |
| `evidence` | object | 否 | 法律法规 / 企业规则依据（原型图 3.2 / 3.3） |

**`findings[]`：**

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `description` | string | 否 | 隐患描述（识别结果），表第一列 |
| `reason` | string | 是 | 识别依据说明文本，表第一列第二行，如 `检测依据：图像特征识别` |
| `location` | string/null | 是 | 隐患部位，表第二列；无法定位时 `null` |
| `risk_level` | string | 是 | 风险等级：`high` / `medium` / `low`（前端映射为 高/中/低 徽标）；未判定时为 `null` |
| `confidence` | number/null | 是 | 单项置信度，0~1 |
| `basis` | array | 否 | 判定依据枚举，见枚举；无依据时可为空数组 |

**`response_deadline`：**

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `urgency` | string | 是 | `urgent`（紧急）/ `normal`（一般）；未判定时为 `null`，前端显示灰色"一般" |
| `text` | string | 否 | 建议文案，后端组装好，前端原样展示，如 `建议 24 小时内完成风险评级并制定整改方案` |

**`evidence.laws[]` / `evidence.rules[]`：**

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 否 | 标题，如 `《中华人民共和国特种设备安全法》`；规则为 `code` |
| `article` | string | 是 | 条款号（laws 有、rules 无） |
| `code` | string | 是 | 规则编码（rules 有、laws 无），如 `设备通则规程-RU-01` |
| `name` | string | 是 | 规则名称（rules 可选） |
| `excerpt` | string | 否 | 正文摘要（按 3 行截断展示） |
| `risk_level` | string | 是 | 关联风险等级说明（rules 可选），如 `高风险` |
| `source_url` | string/null | 是 | 原文链接，无则 `null` |

---

## 5. 字段与原型图映射

| 原型图区块 | 响应字段 |
| --- | --- |
| 标题：隐患单分析详情 / 下载分析报告 | 页面静态文案 + 前端 `id` 生成报告文件名；`report_no` 展示于基础信息 |
| 1. 基础信息 | `report_no`(编号)、`created_at`(创建时间)、`discovery_source`(隐患来源)、`model`(识别模型)、`analyzer.name`(分析人)、`analyzed_at`(分析时间) |
| 2. 识别图像与隐患部位 | `images[]`（大图/多角度切换）、`regions[]`（虚线标注+标签）、`identification_basis`（识别依据） |
| 3. 分析依据 | 3.1 图像识别依据：`images[index].url` + 静态文案；3.2 `analysis.evidence.laws[]`；3.3 `analysis.evidence.rules[]` |
| 4. 隐患识别结果（多模态分析） | `analysis.findings[]`（描述、部位、风险等级、置信度、依据）；条目 >3 时前端"展开全部（共 N 项）" |
| 5. 风险分析与建议 | 5.1 `analysis.risk_impacts[]`；5.2 `analysis.recommended_actions[]`；5.3 `analysis.response_deadline`（紧急徽标 + 文案） |
| 备注（人工审核提示） | 页面静态文案 |

---

## 6. 图片接口

```http
GET /api/v1/hazard-identifications/{id}/images/{index}
```

- 原图：不传参返回原始图片。
- 缩略图（可选实现）：`GET .../images/0?w=128`、`?w=128&h=96`，按等比缩放返回；未实现时前端直接用原图地址（列表页大图数量多时建议实现，为列表性能关键）。
- 404：图片不存在；`415`：格式不支持（同前）。

---

## 7. 错误码

沿用 v1：

| 状态码 | 含义 |
| --- | --- |
| 400 | 请求参数错误 |
| 401 | 服务认证未配置，请联系后端 |
| 404 | 隐患记录不存在或已失效 |
| 413 | 请求体过大 |
| 415 | 请求格式不支持 |
| 429 | 请求过于频繁，请稍后重试 |
| 502 | 识别服务暂时不可用（视觉模型调上游失败后由后端自动重试，最终失败返回上游错误信息） |

错误响应格式：

```json
{
  "detail": "用户可读的中文错误提示",
  "error": { "code": "not_found", "message": "该隐患记录已失效" }
}
```

---

## 8. 枚举值

| 字段 | 可选值 |
| --- | --- |
| `level` | `一般隐患`、`重大隐患` |
| `category` | `电气设备`、`消防设施`、`二违`、`基础设施`、`生产设备`、`管理问题` |
| `type` | `人身安全隐患`、`设备设施事故隐患`、`安全管理隐患`、`电力安全事故隐患`、`大坝安全隐患`、`其他事故隐患` |
| `discovery_source` | `安全检查`、`巡检`、`缺陷`、`隐患排查`、`图片上传识别`（新增） |
| `level_source` | `knowledge_rule`、`model` |
| `findings[].risk_level` | `high`、`medium`、`low` |
| `findings[].basis` | `image_feature`（图像特征）、`law`（法规）、`rule`（规则）、`knowledge`（知识库） |
| `response_deadline.urgency` | `urgent`、`normal` |
| `images[].regions[].kind` | `hazard_area`（隐患部位/蓝色）、`corrosion`（腐蚀/红色）、`crack`（裂纹/红色）、`wear`（磨损/橙色）、`other`；后端可扩展，前端未匹配类型时按默认样式 |

> 枚举可扩展：新增值不影响已有前端逻辑（未知值按其默认样式/文本兜底展示）。

---

## 9. 实现建议（后端）

1. 详情接口建议内部判断：若该记录已有分析结果则直接返回缓存；否则执行一次分析（视觉模型 + 知识库查询）后返回并缓存，历史记录不重复执行。
2. `images[].regions` 建议由视觉模型输出归一化 bbox 与标签文本；无法输出时返回空数组，前端不展示标注框，页面其它区块不受影响。
3. `identification_basis`、`analysis.summary` 等文案字段允许直接使用模型生成语句，由后端组装并保证非空文案可读即可。


