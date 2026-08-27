const params = new URLSearchParams(window.location.search)
const defaultApi = window.location.port === '8787'
  ? `${window.location.origin}/api/v1`
  : 'http://127.0.0.1:8787/api/v1'
const API_BASE = (params.get('api') || defaultApi).replace(/\/$/, '')
const recordId = params.get('id') || ''
const $ = id => document.getElementById(id)
const state = {
  result: null,
  selectedImageIndex: 0,
  expandedFindings: false,
  imageCache: new Map(),
}

function setServiceStatus(text, type) {
  const node = $('serviceStatus')
  node.textContent = text
  node.className = `service-status is-${type}`
}

function uniqueTexts(values) {
  return [...new Set((Array.isArray(values) ? values : []).map(item => String(item || '').trim()).filter(Boolean))]
}

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-')
}

function imageUrl(url) {
  if (!url) return ''
  if (/^https?:\/\//i.test(url)) return url
  return `${API_BASE.replace(/\/api\/v1$/, '')}${url.startsWith('/') ? url : `/${url}`}`
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function displayValue(value, fallback = '-') {
  const text = String(value ?? '').trim()
  return text || fallback
}

function clamp(value, min = 0, max = 1) {
  return Math.min(max, Math.max(min, Number(value) || 0))
}

function loadImage(url) {
  if (state.imageCache.has(url)) return state.imageCache.get(url)
  const promise = new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('图片加载失败'))
    image.src = url
  })
  state.imageCache.set(url, promise)
  return promise
}

function drawContained(context, image, width, height) {
  context.fillStyle = '#f5f8fc'
  context.fillRect(0, 0, width, height)
  const scale = Math.min(width / image.naturalWidth, height / image.naturalHeight)
  const drawWidth = image.naturalWidth * scale
  const drawHeight = image.naturalHeight * scale
  const left = (width - drawWidth) / 2
  const top = (height - drawHeight) / 2
  context.drawImage(image, left, top, drawWidth, drawHeight)
  return { left, top, width: drawWidth, height: drawHeight }
}

function drawContainedCanvas(canvas, image, width, height) {
  canvas.width = width
  canvas.height = height
  return drawContained(canvas.getContext('2d'), image, width, height)
}

function regionBounds(region) {
  const bbox = region?.bbox
  if (!bbox || typeof bbox !== 'object') return null
  const x = clamp(bbox.x)
  const y = clamp(bbox.y)
  const width = clamp(bbox.width)
  const height = clamp(bbox.height)
  const x2 = clamp(x + width)
  const y2 = clamp(y + height)
  if (x2 <= x || y2 <= y) return null
  return [x, y, x2, y2]
}

function validRegions(result, imageIndex = state.selectedImageIndex) {
  const image = result?.media?.images?.[imageIndex]
  return Array.isArray(image?.regions) ? image.regions : []
}

function regionColor(kind) {
  if (kind === 'hazard_area') return '#1769e8'
  if (kind === 'wear') return '#e99427'
  return '#f34d45'
}

function drawRegionLabel(context, text, x, y, color, width = 1000) {
  const label = text || '隐患部位'
  context.font = 'bold 18px Microsoft YaHei, sans-serif'
  const labelWidth = context.measureText(label).width + 28
  const left = Math.max(8, Math.min(x, width - labelWidth - 8))
  const top = Math.max(8, y - 46)
  context.fillStyle = color
  context.fillRect(left, top, labelWidth, 36)
  context.fillStyle = '#fff'
  context.fillText(label, left + 14, top + 24)
}

function drawMainImage(canvas, image, regions) {
  const width = 1000
  const height = 560
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  const frame = drawContained(context, image, width, height)
  regions.forEach(region => {
    const bounds = regionBounds(region)
    if (!bounds) return
    const [x1, y1, x2, y2] = bounds
    const left = frame.left + x1 * frame.width
    const top = frame.top + y1 * frame.height
    const boxWidth = Math.max(10, (x2 - x1) * frame.width)
    const boxHeight = Math.max(10, (y2 - y1) * frame.height)
    const color = regionColor(region.kind)
    context.save()
    context.fillStyle = `${color}18`
    context.fillRect(left, top, boxWidth, boxHeight)
    context.strokeStyle = color
    context.lineWidth = 4
    context.setLineDash([12, 8])
    context.strokeRect(left, top, boxWidth, boxHeight)
    context.restore()
    drawRegionLabel(context, region.label, left, top, color, width)
  })
}

function drawRegionCrop(canvas, image, region) {
  const width = 1000
  const height = 500
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  const bounds = regionBounds(region)
  if (!bounds) {
    drawContained(context, image, width, height)
    return
  }
  const [x1, y1, x2, y2] = bounds
  const paddingX = Math.max((x2 - x1) * 0.08, 0.02)
  const paddingY = Math.max((y2 - y1) * 0.08, 0.02)
  const cropX = Math.max(0, x1 - paddingX)
  const cropY = Math.max(0, y1 - paddingY)
  const cropRight = Math.min(1, x2 + paddingX)
  const cropBottom = Math.min(1, y2 + paddingY)
  const cropWidth = Math.max(cropRight - cropX, 0.01)
  const cropHeight = Math.max(cropBottom - cropY, 0.01)
  const scale = Math.min(width / (cropWidth * image.naturalWidth), height / (cropHeight * image.naturalHeight))
  const drawWidth = cropWidth * image.naturalWidth * scale
  const drawHeight = cropHeight * image.naturalHeight * scale
  const left = (width - drawWidth) / 2
  const top = (height - drawHeight) / 2
  context.fillStyle = '#f5f8fc'
  context.fillRect(0, 0, width, height)
  context.drawImage(
    image,
    cropX * image.naturalWidth,
    cropY * image.naturalHeight,
    cropWidth * image.naturalWidth,
    cropHeight * image.naturalHeight,
    left,
    top,
    drawWidth,
    drawHeight,
  )
  const boxLeft = left + ((x1 - cropX) / cropWidth) * drawWidth
  const boxTop = top + ((y1 - cropY) / cropHeight) * drawHeight
  const boxWidth = Math.max(10, ((x2 - x1) / cropWidth) * drawWidth)
  const boxHeight = Math.max(10, ((y2 - y1) / cropHeight) * drawHeight)
  const color = regionColor(region.kind)
  context.save()
  context.fillStyle = `${color}10`
  context.fillRect(boxLeft, boxTop, boxWidth, boxHeight)
  context.strokeStyle = color
  context.lineWidth = 4
  context.setLineDash([12, 8])
  context.strokeRect(boxLeft, boxTop, boxWidth, boxHeight)
  context.restore()
  drawRegionLabel(context, region.label, boxLeft + boxWidth - 190, boxTop, color, width)
}

async function renderSelectedImage() {
  const result = state.result
  const images = result?.media?.images || []
  const item = images[state.selectedImageIndex]
  if (!item) return
  try {
    const image = await loadImage(imageUrl(item.url))
    const regions = validRegions(result)
    const region = regions[0] || null
    drawMainImage($('detailMainCanvas'), image, regions)
    if (region) {
      $('regionFocusEmpty').classList.add('hidden')
      drawRegionCrop($('regionFocusCanvas'), image, region)
      drawRegionCrop($('basisCanvas'), image, region)
      $('regionFocusDescription').textContent = region.description || '已定位隐患区域'
      $('basisDescription').textContent = result.media.imageBasis || '依据识别结果，定位并核验隐患部位。'
    } else {
      $('regionFocusEmpty').classList.remove('hidden')
      drawContainedCanvas($('regionFocusCanvas'), image, 1000, 500)
      drawContainedCanvas($('basisCanvas'), image, 1000, 500)
      $('regionFocusDescription').textContent = '当前图片没有可绘制的区域坐标'
      $('basisDescription').textContent = result.media.imageBasis || '当前记录暂未返回可绘制区域，请以原图和文字分析为准。'
    }
  } catch (error) {
    $('mainImageEmpty').textContent = '识别图像加载失败'
    $('mainImageEmpty').classList.remove('hidden')
  }
}

function renderGallery(result) {
  const images = result.media?.images || []
  const container = $('detailThumbnails')
  if (!images.length) {
    $('mainImageEmpty').classList.remove('hidden')
    $('regionFocusEmpty').classList.remove('hidden')
    return
  }
  $('mainImageEmpty').classList.add('hidden')
  state.selectedImageIndex = Math.min(state.selectedImageIndex, images.length - 1)
  container.innerHTML = images.map((item, index) => `
    <button class="detail-thumbnail ${index === state.selectedImageIndex ? 'is-active' : ''}" data-image-index="${index}" type="button">
      <img src="${imageUrl(item.url)}" alt="识别图片 ${index + 1}">
      <span>${index + 1}</span>
    </button>`).join('')
  container.querySelectorAll('[data-image-index]').forEach(button => {
    button.addEventListener('click', () => {
      state.selectedImageIndex = Number(button.dataset.imageIndex)
      container.querySelectorAll('.detail-thumbnail').forEach(item => item.classList.remove('is-active'))
      button.classList.add('is-active')
      renderSelectedImage()
    })
  })
  renderSelectedImage()
}

function renderBasicInfo(result) {
  const basic = result.basic || {}
  $('detailReportNo').textContent = displayValue(basic.reportNo, recordId || '-')
  $('detailCreatedAt').textContent = formatTime(basic.createdAt)
  $('detailSource').textContent = displayValue(basic.source, '待确认')
  $('detailModel').textContent = displayValue(basic.model, '待确认')
  $('detailAnalyst').textContent = displayValue(basic.analyst, '待确认')
  $('detailAnalyzedAt').textContent = formatTime(basic.analyzedAt)
}

function basisItem(item, kind) {
  const icon = kind === 'legal' ? '▣' : '✓'
  const title = item.title
  const detailLabel = kind === 'legal'
    ? (item.article ? `条款号：${item.article}` : '法规/目录依据')
    : (item.riskLevelText ? `关联风险：${item.riskLevelText}` : '规则内容')
  const contentLabel = kind === 'legal'
    ? (item.articleContent ? '违反条款内容' : '依据说明')
    : '规则内容'
  const content = item.articleContent || item.excerpt || '已命中相关依据'
  const reason = kind === 'legal' ? item.violationReason : ''
  const aiSummary = item.aiSummary
  return `<div class="basis-item">
    <span class="basis-item-icon ${kind}">${icon}</span>
    <div><strong>${escapeHtml(title || '隐患依据')}</strong><em class="basis-item-label">${escapeHtml(detailLabel)}</em><p class="basis-item-content"><b>${escapeHtml(contentLabel)}：</b>${escapeHtml(content)}</p>${aiSummary ? `<p class="basis-item-ai"><b>AI归纳：</b>${escapeHtml(aiSummary)}</p>` : ''}${reason ? `<p class="basis-item-reason"><b>对应说明：</b>${escapeHtml(reason)}</p>` : ''}</div>
  </div>`
}

function renderBasis(result) {
  const evidence = result.evidence || {}
  const legal = Array.isArray(evidence.laws) ? evidence.laws : []
  const rules = Array.isArray(evidence.rules) ? evidence.rules : []
  $('legalBasis').innerHTML = legal.length
    ? legal.slice(0, 4).map(item => basisItem(item, 'legal')).join('')
    : '<div class="basis-empty">暂无已配置的法律法规依据</div>'
  $('ruleBasis').innerHTML = rules.length
    ? rules.slice(0, 4).map(item => basisItem(item, 'rule')).join('')
    : '<div class="basis-empty">暂无企业规则依据</div>'
}

function findingRows(result) {
  return (Array.isArray(result.findings) ? result.findings : []).map((item, index) => ({
    index: index + 1,
    description: item.description,
    reason: item.reason,
    location: item.location,
    risk: item.riskBadge?.text,
    confidence: item.confidenceText,
    basis: item.basisText,
  }))
}

function renderFindings(result) {
  const rows = findingRows(result)
  const visible = state.expandedFindings ? rows : rows.slice(0, 3)
  $('findingRows').innerHTML = visible.length
    ? visible.map(row => {
      const levelClass = row.risk === '高' ? 'high' : row.risk === '中' ? 'medium' : row.risk === '低' ? 'low' : 'unknown'
      return `<tr>
        <td>${row.index}</td>
        <td><strong>${escapeHtml(displayValue(row.description))}</strong><small>${escapeHtml(displayValue(row.reason))}</small></td>
        <td>${escapeHtml(displayValue(row.location, '待确认'))}</td>
        <td><span class="risk-level ${levelClass}">${escapeHtml(displayValue(row.risk, '待确认'))}</span></td>
        <td>${escapeHtml(displayValue(row.confidence))}</td>
        <td>${escapeHtml(displayValue(row.basis))}</td>
      </tr>`
    }).join('')
    : '<tr><td colspan="6" class="table-empty">暂无隐患识别结果</td></tr>'
  const more = $('expandFindings')
  if (rows.length > 3) {
    more.classList.remove('hidden')
    more.textContent = state.expandedFindings ? '收起结果⌃' : `展开全部（共 ${rows.length} 项）⌄`
  } else {
    more.classList.add('hidden')
  }
}

function renderRiskSuggestions(result) {
  const suggestion = result.suggestion || {}
  const impacts = uniqueTexts(suggestion.impacts)
  $('riskAnalysisList').innerHTML = impacts.length
    ? impacts.slice(0, 5).map(item => `<div>${escapeHtml(item)}</div>`).join('')
    : '<div class="table-empty">暂无风险影响分析</div>'
  const actions = uniqueTexts(suggestion.actions)
  $('actionList').innerHTML = actions.length
    ? actions.slice(0, 5).map((item, index) => `<div><b>${index + 1}</b><span>${escapeHtml(item)}</span></div>`).join('')
    : '<div class="table-empty">暂无整改建议</div>'
  const deadline = suggestion.deadline || {}
  const urgent = deadline.isUrgent === true
  $('deadlineBadge').className = `deadline-badge ${urgent ? '' : 'is-set'}`
  $('deadlineBadge').innerHTML = `<span>◷</span><b>${urgent ? '紧急' : '一般'}</b>`
  $('deadlineText').textContent = displayValue(deadline.text, '待确认整改时限')
  $('deadlineHint').textContent = urgent ? '请优先完成风险控制并制定整改方案' : '按分析建议完成整改并复核'
}

function renderDetail(result) {
  state.result = result
  renderBasicInfo(result)
  renderGallery(result)
  renderBasis(result)
  renderFindings(result)
  renderRiskSuggestions(result)
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`
    try {
      const payload = await response.json()
      detail = typeof payload.detail === 'string' ? payload.detail : detail
    } catch (error) {
      // 使用状态码兜底提示
    }
    throw new Error(detail)
  }
  return response.json()
}

function listUrl() {
  return `./index.html?api=${encodeURIComponent(API_BASE)}`
}

$('backToList').href = listUrl()
$('downloadReport').addEventListener('click', () => window.print())
$('expandFindings').addEventListener('click', () => {
  state.expandedFindings = !state.expandedFindings
  renderFindings(state.result)
})

if (!recordId) {
  setServiceStatus('缺少记录 ID', 'error')
} else {
  request(`/hazard-identifications/${encodeURIComponent(recordId)}`)
    .then(result => {
      renderDetail(result)
      setServiceStatus('服务在线', 'online')
    })
    .catch(error => setServiceStatus(error.message || '加载失败', 'error'))
}
