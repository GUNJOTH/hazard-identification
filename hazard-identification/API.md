# 隐患识别 API 接口文档（v3）

> **版本说明（v3）**：详情接口按原型图五个展示区块重新设计数据结构 ——
> 后端一次返回「基础信息 / 识别图像与隐患部位 / 分析依据 / 隐患识别结果 / 风险分析与建议」五个区块，
> **字段名即页面语义，取字段即渲染**，前端不再做字段映射与兜底转换。
> 1. **列表接口契约不变**（与 v1 完全一致，前端已依赖，不要改动）。
> 2. 详情接口为 v3 重设计：原 `analysis` / `hazard_info` / `identification_basis` /
>    `response_deadline` 等松散字段全部收敛为下方结构，**不再返回嵌套的综合分析对象**。
> 3. 原 `POST /hazard-identifications/{id}/analysis` 不再作为前端依赖：分析结论由详情接口统一返回。
>    详情接口内部执行/读取分析，建议按记录缓存结果（重复请求返回相同内容，分析为只读、不重复计费）。

---

## 1. 总览

- **Base URL**：智能体配置地址 `SY_AG_URL`，未配置时缺省 `http://172.20.2.99:8787`，统一前缀 `/api/v1`。
- **返回格式**：JSON；成功一律 2xx；错误见 [第 7 节错误码](#7-错误码)。
- **时间格式**：ISO 8601 UTC 字符串，如 `2026-08-26T04:30:00Z`。
- **空值约定**：字段为 `null` 表示当前图片/上下文/知识库不能可靠确认，前端展示"待确认"或 `-`，
  **不要当作空字符串处理**；必填数组（`images` / `findings` / `evidence.laws` / `evidence.rules` /
  `suggestion.risk_impacts` / `suggestion.recommended_actions`）无内容时**返回空数组**，不返回 `null`。
- **图片地址**：`url` / `thumbnail_url` 均为相对地址（`/api/v1/...`），前端拼上 Base URL 使用。

## 2. 接口总览

| 接口 | 方法 | 路径 | 用途 |
| --- | --- | --- | --- |
| 隐患记录列表 | GET | `/api/v1/hazard-identifications` | 分页隐患摘要（**不变**） |
| 隐患记录详情 | GET | `/api/v1/hazard-identifications/{id}` | 完整分析报告（**v3 重设计**） |

> 图片接口 `GET /api/v1/hazard-identifications/{id}/images/{index}` 沿用（见 [6.图片接口](#6-图片接口)）。
> `POST /api/v1/hazard-identifications`（创建识别）暂不在前端流程内，按现状处理即可。

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
| `category` | string/null | 隐患类别，见 [第 8 节枚举](#8-枚举值) |
| `type` | string/null | 隐患类型，见 [第 8 节枚举](#8-枚举值) |
| `level` | string/null | 隐患等级，`一般隐患` / `重大隐患`，未命中规则为 `null` |
| `discovery_source` | string | 隐患发现来源，见 [第 8 节枚举](#8-枚举值) |
| `rectification_deadline` | string/null | 整改时限，`YYYY-MM-DD`；图片无法确认时为 `null` |
| `location` | string/null | 区域位置 |
| `equipment_name` | string/null | 设备或对象名称 |
| `image_count` | integer | 关联图片数量（多角度仍算一条记录） |
| `thumbnail_url` | string/null | 第一张图片相对地址，可直接用于 `<img src>` |
| `manual_review_required` | boolean | 是否需要人工复核 |

---

## 4. 隐患记录详情（按前端 view 结构返回）

```http
GET /api/v1/hazard-identifications/{id}
```

**响应结构即前端渲染结构（view）**：字段名与前端组件取值完全一致（`view.basic.reportNo`、
`view.media.images`、`view.evidence.laws`、`view.findings`、`view.suggestion` —— 对应页面五个区块），
前端零转换、零兜底链。后端只需按下述结构返回，把各字段的取值、回退、文案组装全部做实。

### 4.1 响应示例

```json
{
  "basic": {
    "reportNo": "HD-20260826-0001",
    "createdAt": "2026-08-26T08:00:00Z",
    "source": "图片上传识别",
    "model": "生产设备",
    "analyst": "设备设施事故隐患",
    "analyzedAt": "2026-08-26T08:02:11Z"
  },

  "media": {
    "imageBasis": "表面锈蚀严重，涂层剥落，存在腐蚀减薄风险，可能导致设备泄漏。",
    "images": [
      {
        "index": 0,
        "url": "/api/v1/hazard-identifications/7c3b8cae-5a3d-4ca2-bf18-0d1a7a3e31b4/images/0",
        "regions": [
          {
            "id": "r0-1",
            "label": "腐蚀,锈蚀区域",
            "kind": "corrosion",
            "bbox": { "x": 0.33, "y": 0.46, "width": 0.42, "height": 0.36 },
            "confidence": 0.93
          },
          {
            "id": "r0-2",
            "label": "隐患部位",
            "kind": "hazard_area",
            "bbox": { "x": 0.30, "y": 0.40, "width": 0.50, "height": 0.50 },
            "confidence": null
          }
        ]
      }
    ]
  },

  "evidence": {
    "laws": [
      {
        "title": "《中华人民共和国特种设备安全法》",
        "article": "第十三条",
        "articleContent": "特种设备使用单位应当使用符合安全技术规范要求的特种设备，并不得使用未经检验或者检验不合格的特种设备。",
        "excerpt": "用于判断特种设备是否符合安全技术规范要求；图片只能作为外观异常线索，需结合检验和现场资料确认。",
        "violationReason": "当前识别结果涉及特种设备外观异常，与该条款的使用和安全技术要求相关；是否构成违反条款仍需结合检验和现场资料复核。",
        "aiSummary": "该条款关注特种设备是否符合安全技术规范。当前图片只能作为外观异常线索，仍需结合设备档案、检验记录和现场检查确认。"
      }
    ],
    "rules": [
      {
        "title": "设备泄漏或减薄处置规则",
        "riskLevelText": "高风险",
        "excerpt": "设备泄漏或减薄经确认后，泄漏或减薄超过设计使用年限的 10% 或减薄 >1mm，判定为隐患。"
      }
    ]
  },

  "findings": [
    {
      "description": "法兰连接处存在锈蚀、腐蚀现象",
      "reason": "检测依据：图像特征识别",
      "location": "循环水出口法兰",
      "riskBadge": { "text": "高" },
      "confidenceText": "0.93",
      "basisText": "图像特征、法规、规则"
    }
  ],

  "suggestion": {
    "impacts": [
      "可能导致介质泄漏，造成设备失效",
      "存在高温热水泄漏风险，可能造成人员烫伤",
      "环境污染风险增加"
    ],
    "actions": [
      "立即清除整改部位，评估腐蚀深度",
      "对腐蚀部位进行补焊或更换受损部件",
      "表面防腐处理，恢复防护涂层"
    ],
    "deadline": {
      "isUrgent": true,
      "text": "建议 24 小时内完成风险评级并制定整改方案"
    }
  }
}
```

### 4.2 顶层结构

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `basic` | object | ① 基础信息 |
| `media` | object | ② 识别图像与隐患部位 |
| `evidence` | object | ③ 分析依据 |
| `findings` | array | ④ 隐患识别结果（多模态分析） |
| `suggestion` | object | ⑤ 风险分析与建议 |

### 4.3 ① `basic` 基础信息（原型图 1）

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `reportNo` | string | 是 | 报告单号（编号），如 `HD-20260826-0001`；未生成时为 `null`，前端回退接口请求用的 `id` |
| `createdAt` | string | 否 | 创建时间 |
| `source` | string | 是 | 隐患来源，如 `图片上传识别`，见枚举 |
| `model` | string | 是 | 兼容已发版前端的字段名；详情页展示为“隐患类别”，如 `生产设备` |
| `analyst` | string | 是 | 兼容已发版前端的字段名；详情页展示为“隐患类型”，如 `设备设施事故隐患` |
| `analyzedAt` | string | 是 | 分析时间；为空时前端回退 `discovery_time` → `created_at`（列表同款字段，由后端在基础字段中一并返回） |

### 4.4 ② `media` 识别图像与隐患部位（原型图 2）

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `imageBasis` | string | 是 | 识别依据摘要（2 区底部"识别依据"文本），如 `表面锈蚀严重，涂层剥落…` |
| `images` | array | 否 | 图片列表，可为空数组（多角度多张同属一条隐患） |

**`images[]`：**

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `index` | int | 否 | 图片序号，从 0 开始 |
| `url` | string | 否 | 原图**相对地址**（`/api/v1/...`），前端拼接 Base URL 使用 |
| `regions` | array | 否 | 标注区域列表（虚线框 + 标签），可为空数组 |

**`regions[]`：**

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 否 | 区域唯一标识 |
| `label` | string | 否 | 标注文本，如 `腐蚀,锈蚀区域`、`隐患部位`，前端直接展示 |
| `kind` | string | 是 | 区域类型，见枚举；前端据此配色（`corrosion` 红 / `hazard_area` 蓝 / `wear` 橙） |
| `bbox` | object | 否 | 归一化坐标（0~1）：`x` / `y` / `width` / `height` |
| `confidence` | number | 是 | 置信度 0~1，不可量化时为 `null` |

> 前端用 bbox 在原图上叠虚线框 + 标签，并裁出"隐患部位放大图"，后端无需提供裁剪图片 URL。

### 4.5 ③ `evidence` 分析依据（原型图 3）

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `laws` | array | 否 | 相关法律法规依据，无内容时为空数组 |
| `rules` | array | 否 | 企业规则依据，无内容时为空数组 |

**`laws[]`：**

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 否 | 法规标题，如 `《中华人民共和国特种设备安全法》` |
| `article` | string | 是 | 条款号，如 `第十三条`；没有明确条款号时为 `null` |
| `articleContent` | string | 是 | 命中的条款原文；知识库未提供明确条款原文时为 `null`，前端不得自行补写 |
| `excerpt` | string | 否 | 依据说明，包括适用范围、检查要点或隐患参考项，不再作为条款原文展示（卡片内 3 行截断，悬浮展示全文） |
| `violationReason` | string | 是 | 当前隐患与该条款/检查要求的对应说明；照片只能证明可见现象，不能据此直接认定违法或最终等级 |
| `aiSummary` | string | 是 | AI 根据当前隐患、图片现象和该条依据归纳的适用说明；必须以知识库原文为边界 |

**`rules[]`：**

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 否 | 规则名称（后端已合成，如 `设备泄漏或减薄处置规则`；编码类信息需要时可由后端并入标题） |
| `riskLevelText` | string | 是 | 关联风险等级说明，如 `高风险` |
| `excerpt` | string | 否 | 正文摘要（同 laws） |
| `aiSummary` | string | 是 | AI 根据当前隐患和规则内容归纳的适用说明 |

### 4.6 ④ `findings[]` 隐患识别结果（原型图 4）

> **顺序即表格行顺序**，前端不排序；条目 > 3 时前端展示"展开全部（共 N 项）"。
> 无识别结果时返回**空数组**，前端显示空态。

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `description` | string | 否 | 隐患描述（识别结果），表第一列 |
| `reason` | string | 是 | 识别依据说明（表第一列第二行小字），如 `检测依据：图像特征识别` |
| `location` | string/null | 是 | 隐患部位，表第二列；无法定位时为 `null`（前端"待确认"） |
| `riskBadge` | object | 否 | 风险等级徽标，`{ "text": "高" }`（取值 `高` / `中` / `低`；未判定时 `{ "text": null }`，前端显示"待确认"） |
| `confidenceText` | string | 是 | 置信度展示文本，保留两位小数，如 `"0.93"`；未量化时为 `null`（前端显示 `-`） |
| `basisText` | string | 是 | 判定依据展示文本（顿号连接好的字符串），如 `图像特征、法规、规则`；无依据时为 `null`（前端显示 `-`） |

### 4.7 ⑤ `suggestion` 风险分析与建议（原型图 5）

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `impacts` | array | 否 | 风险影响分析条目（5.1 列表，顺序即展示顺序），可为空数组 |
| `actions` | array | 否 | 整改建议条目（5.2 编号列表，任意长度），可为空数组 |
| `deadline` | object | 否 | 建议整改时限（5.3） |

**`deadline`：**

| 字段 | 类型 | 可空 | 说明 |
| --- | --- | --- | --- |
| `isUrgent` | boolean | 否 | 是否紧急（`true`=红色徽标"紧急"，否则橙色"一般"） |
| `text` | string | 否 | 建议文案，后端组装好，前端原样展示 |

> **前端职责仅剩**：图片相对地址拼接 Base URL；时间格式化（`yyyy-MM-dd HH:mm:ss`）；风险等级徽标配色（按 `riskBadge.text` 映射样式）。无任何字段映射与结构转换。

---

## 5. 字段与原型图映射（后端对齐表）

| 原型图区块 | 响应字段 |
| --- | --- |
| 标题：隐患单分析详情 / 下载分析报告 | 页面静态文案；报告文件名由前端用 `basic.reportNo` 生成 |
| 1. 基础信息 | `basic.reportNo`(编号)、`basic.createdAt`(创建时间)、`basic.source`(隐患来源)、`basic.model`(隐患类别展示位)、`basic.analyst`(隐患类型展示位)、`basic.analyzedAt`(分析时间) |
| 2. 识别图像与隐患部位 | `media.images[]`（大图/多角度切换）、`media.images[].regions[]`（虚线框+标签）、`media.imageBasis`（识别依据） |
| 3. 分析依据 | 3.1 图像识别依据：`media.images[index].url` + 页面静态文案；3.2 `evidence.laws[]`；3.3 `evidence.rules[]` |
| 4. 隐患识别结果（多模态分析） | `findings[]`（描述、依据说明、部位、风险等级徽标、置信度、依据） |
| 5. 风险分析与建议 | 5.1 `suggestion.impacts[]`；5.2 `suggestion.actions[]`；5.3 `suggestion.deadline`（紧急徽标 + 文案） |
| 备注（人工审核提示） | 页面静态文案 |

---

## 6. 图片接口

```http
GET /api/v1/hazard-identifications/{id}/images/{index}
```

- 原图：不传参返回原始图片。
- 缩略图（可选实现）：`GET .../images/0?w=128`、`?w=128&h=96`，按等比缩放返回；未实现时前端直接用原图地址（列表页大图数量多时建议实现，为列表性能关键）。
- `404`：图片不存在；`415`：格式不支持（同前）。

---

## 7. 错误码

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
| `basic.source` | `安全检查`、`巡检`、`缺陷`、`隐患排查`、`图片上传识别` |
| `findings[].riskBadge.text` | `高`、`中`、`低`（展示文本，直接渲染；为 `null` 时前端显示"待确认"） |
| `findings[].basisText` 来源枚举 | `图像特征`、`法规`、`规则`、`知识库`（后端拼顿号字符串，前端直接展示） |
| `media.images[].regions[].kind` | `hazard_area`（隐患部位/蓝色）、`corrosion`（腐蚀/红色）、`crack`（裂纹/红色）、`wear`（磨损/橙色）、`other`；后端可扩展，前端未匹配类型时按默认样式 |

> 枚举可扩展：新增值不影响已有前端逻辑（未知值按其默认样式/文本兜底展示）。

---

## 9. 实现建议（后端）

1. 详情接口建议内部判断：若该记录已有分析结果则直接返回缓存；否则执行一次分析（视觉模型 + 知识库查询）后返回并缓存，历史记录不重复执行。
2. `images[].regions` 建议由视觉模型输出归一化 bbox 与标签文本；无法输出时返回空数组，前端不展示标注框，页面其它区块不受影响。
3. `identification_basis`、`findings[].reason`、`suggestion.deadline.text` 等文案字段允许直接使用模型生成语句，由后端组装并保证非空文案可读即可。
4. `findings[].riskBadge.text` / `basisText` / `confidenceText` / `suggestion.deadline.{isUrgent,text}` 等展示值由后端统一组装（模型枚举 → `高`/`中`/`低`、`图像特征`/`法规`/`规则`/`知识库`、置信度两位小数、时限文案），前端不再处理。
