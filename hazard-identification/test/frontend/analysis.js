const params = new URLSearchParams(window.location.search)
const defaultApi = window.location.port === '8787'
  ? `${window.location.origin}/api/v1`
  : 'http://127.0.0.1:8787/api/v1'
const API_BASE = (params.get('api') || defaultApi).replace(/\/$/, '')
const recordId = params.get('id') || ''
const $ = id => document.getElementById(id)
const state = {
  result: null,
  analysis: null,
  selectedImageIndex: 0,
  expandedFindings: false,
  imageCache: new Map(),
}

function setServiceStatus(text, type) {
  const node = $('serviceStatus')
  node.textContent = text
  node.className = `service-status is-${type}`
}

function listText(value, fallback = '-') {
  if (Array.isArray(value)) return value.filter(Boolean).join('；') || fallback
  return value || fallback
}

function uniqueTexts(values) {
  return [...new Set((values || []).map(item => String(item || '').trim()).filter(Boolean))]
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

function validRegions(result) {
  const images = result?.images || []
  return (Array.isArray(result?.regions) ? result.regions : [])
    .filter(region => images[region.image_index])
}

function drawRegionLabel(context, text, x, y) {
  const label = text || '隐患部位'
  context.font = 'bold 18px Microsoft YaHei, sans-serif'
  const labelWidth = context.measureText(label).width + 28
  const left = Math.max(8, Math.min(x, 1000 - labelWidth - 8))
  const top = Math.max(8, y - 46)
  context.fillStyle = '#f34d45'
  context.fillRect(left, top, labelWidth, 36)
  context.fillStyle = '#fff'
  context.fillText(label, left + 14, top + 24)
}

function drawMainImage(canvas, image, region) {
  const width = 1000
  const height = 560
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  const frame = drawContained(context, image, width, height)
  if (!region) return
  const [x1, y1, x2, y2] = (region.bbox || []).map(Number)
  if (![x1, y1, x2, y2].every(Number.isFinite)) return
  const left = frame.left + clamp(x1) * frame.width
  const top = frame.top + clamp(y1) * frame.height
  const boxWidth = Math.max(10, (clamp(x2) - clamp(x1)) * frame.width)
  const boxHeight = Math.max(10, (clamp(y2) - clamp(y1)) * frame.height)
  context.save()
  context.fillStyle = 'rgba(243, 77, 69, 0.08)'
  context.fillRect(left, top, boxWidth, boxHeight)
  context.strokeStyle = '#f34d45'
  context.lineWidth = 4
  context.setLineDash([12, 8])
  context.strokeRect(left, top, boxWidth, boxHeight)
  context.restore()
  drawRegionLabel(context, region.label, left, top)
}

function drawRegionCrop(canvas, image, region) {
  const width = 1000
  const height = 500
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!region || !Array.isArray(region.bbox)) {
    drawContained(context, image, width, height)
    return
  }
  const [x1, y1, x2, y2] = region.bbox.map(Number)
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
  context.save()
  context.fillStyle = 'rgba(243, 77, 69, 0.06)'
  context.fillRect(boxLeft, boxTop, boxWidth, boxHeight)
  context.strokeStyle = '#f34d45'
  context.lineWidth = 4
  context.setLineDash([12, 8])
  context.strokeRect(boxLeft, boxTop, boxWidth, boxHeight)
  context.restore()
  drawRegionLabel(context, region.label, boxLeft + boxWidth - 190, boxTop)
}

async function renderSelectedImage() {
  const result = state.result
  const images = result?.images || []
  const item = images[state.selectedImageIndex]
  if (!item) return
  try {
    const image = await loadImage(imageUrl(item.url))
    const regions = validRegions(result)
    const region = regions.find(item => item.image_index === state.selectedImageIndex) || null
    drawMainImage($('detailMainCanvas'), image, region)
    if (region) {
      $('regionFocusEmpty').classList.add('hidden')
      drawRegionCrop($('regionFocusCanvas'), image, region)
      $('basisCanvas').classList.remove('hidden')
      drawRegionCrop($('basisCanvas'), image, region)
      $('regionFocusDescription').textContent = region.description || '已定位隐患区域'
      $('basisDescription').textContent = `依据识别结果，定位并核验${region.label || '隐患'}，直观反映设备当前状态。`
    } else {
      $('regionFocusEmpty').classList.remove('hidden')
      drawContained($('regionFocusCanvas').getContext('2d'), image, 1000, 500)
      drawContained($('basisCanvas').getContext('2d'), image, 1000, 500)
      $('regionFocusDescription').textContent = '当前图片没有可绘制的区域坐标'
      $('basisDescription').textContent = '当前记录暂未返回可绘制区域，请以原图和文字分析为准。'
    }
  } catch (error) {
    $('mainImageEmpty').textContent = '识别图像加载失败'
    $('mainImageEmpty').classList.remove('hidden')
  }
}

function renderGallery(result) {
  const images = result.images || []
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
  const draft = result.hazard_info || {}
  $('detailRecordId').textContent = result.id || '-'
  $('detailDescription').textContent = draft.description || '待补充隐患描述'
  $('detailCategory').textContent = draft.category || '待分类'
  $('detailType').textContent = draft.type || '待确认'
  $('detailLevel').textContent = draft.level || '待确认'
  $('detailSource').textContent = draft.discovery_source || '隐患排查'
  $('detailEquipment').textContent = draft.equipment_name || '待现场确认'
  $('detailLocation').textContent = draft.location || '待现场确认'
  $('detailTime').textContent = formatTime(draft.discovery_time || result.created_at)
  $('detailDeadline').textContent = draft.rectification_deadline || '待确认'
  $('detailSpecial').textContent = draft.special_equipment_involved || '待确认'
  $('detailStatus').textContent = draft.remediation?.status || '待整改'
}

function basisItem(item, kind) {
  const icon = kind === 'legal' ? '▣' : '✓'
  return `<div class="basis-item">
    <span class="basis-item-icon ${kind}">${icon}</span>
    <div><strong>${escapeHtml(item.document || '隐患规则库')}</strong><p>${escapeHtml(item.content || '已命中相关依据')}</p></div>
  </div>`
}

function renderBasis(result) {
  const evidence = result.hazard_info?.evidence || []
  const legal = evidence.filter(item => /法|规程|标准|条例/.test(item.document || ''))
  const rules = evidence.filter(item => !legal.includes(item))
  $('legalBasis').innerHTML = legal.length
    ? legal.slice(0, 4).map(item => basisItem(item, 'legal')).join('')
    : '<div class="basis-empty">暂无已配置的法律法规召回记录</div>'
  $('ruleBasis').innerHTML = rules.length
    ? rules.slice(0, 4).map(item => basisItem(item, 'rule')).join('')
    : '<div class="basis-empty">暂无企业规则召回记录</div>'
}

function findingRows(result, analysis) {
  const draft = result.hazard_info || {}
  const regions = validRegions(result)
  if (regions.length) {
    return regions.map((region, index) => ({
      index: index + 1,
      description: region.description || draft.description || '待补充隐患描述',
      location: region.label || draft.location || '待现场确认',
      level: draft.level || '待确认',
      confidence: region.confidence ?? analysis?.confidence,
      basis: '图像特征、规则依据',
    }))
  }
  return [{
    index: 1,
    description: draft.description || analysis?.summary || '待补充隐患描述',
    location: draft.location || analysis?.focus_hint || '待现场确认',
    level: draft.level || '待确认',
    confidence: analysis?.confidence,
    basis: '图像特征、规则依据',
  }]
}

function renderFindings(result, analysis) {
  const rows = findingRows(result, analysis)
  const visible = state.expandedFindings ? rows : rows.slice(0, 3)
  $('findingRows').innerHTML = visible.map(row => {
    const confidence = typeof row.confidence === 'number' ? row.confidence.toFixed(2) : '待确认'
    const levelClass = row.level === '重大隐患' ? 'high' : row.level === '一般隐患' ? 'medium' : 'unknown'
    return `<tr>
      <td>${row.index}</td>
      <td><strong>${escapeHtml(row.description)}</strong><small>检测依据：图像特征识别</small></td>
      <td>${escapeHtml(row.location)}</td>
      <td><span class="risk-level ${levelClass}">${escapeHtml(row.level)}</span></td>
      <td>${confidence}</td>
      <td>${escapeHtml(row.basis)}</td>
    </tr>`
  }).join('')
  const more = $('expandFindings')
  if (rows.length > 3) {
    more.classList.remove('hidden')
    more.textContent = state.expandedFindings ? '收起结果⌃' : `展开全部（共 ${rows.length} 项）⌄`
  } else {
    more.classList.add('hidden')
  }
}

function renderRiskSuggestions(result, analysis) {
  const draft = result.hazard_info || {}
  const riskItems = uniqueTexts([
    analysis?.risk_assessment,
    analysis?.impact,
    analysis?.root_cause,
    ...(analysis?.key_findings || []),
  ])
  $('riskAnalysisList').innerHTML = riskItems.length
    ? riskItems.slice(0, 5).map(item => `<div>${escapeHtml(item)}</div>`).join('')
    : '<div class="table-empty">等待 AI 分析</div>'
  const actions = uniqueTexts(analysis?.recommended_actions || draft.suggested_actions || [])
  $('actionList').innerHTML = actions.length
    ? actions.slice(0, 5).map((item, index) => `<div><b>${index + 1}</b><span>${escapeHtml(item)}</span></div>`).join('')
    : '<div class="table-empty">暂无整改建议</div>'
  const deadline = draft.rectification_deadline
  $('deadlineBadge').className = `deadline-badge ${deadline ? 'is-set' : ''}`
  $('deadlineBadge').innerHTML = `<span>◷</span><b>${deadline ? '已设定' : '待确认'}</b>`
  $('deadlineText').textContent = deadline ? `建议整改完成：${deadline}` : '请结合现场情况确认整改时限'
  $('deadlineHint').textContent = deadline ? '完成风险评估并按期制定整改方案' : '完成风险评估并制定整改方案'
}

function renderDetail(result) {
  state.result = result
  renderBasicInfo(result)
  renderGallery(result)
  renderBasis(result)
  renderFindings(result, state.analysis)
  renderRiskSuggestions(result, state.analysis)
}

function renderContentAnalysis(analysis) {
  state.analysis = analysis
  renderBasicInfo(state.result)
  renderFindings(state.result, analysis)
  renderRiskSuggestions(state.result, analysis)
}

function renderContentAnalysisError(error) {
  $('riskAnalysisList').innerHTML = `<div class="table-empty">${escapeHtml(error.message || 'AI 分析暂时不可用')}</div>`
  $('actionList').innerHTML = '<div class="table-empty">请稍后重试</div>'
  renderFindings(state.result, null)
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
  renderFindings(state.result, state.analysis)
})

if (!recordId) {
  setServiceStatus('缺少记录 ID', 'error')
} else {
  request(`/hazard-identifications/${encodeURIComponent(recordId)}`)
    .then(async result => {
      renderDetail(result)
      setServiceStatus('服务在线', 'online')
      try {
        const analysis = await request(`/hazard-identifications/${encodeURIComponent(recordId)}/analysis`, { method: 'POST' })
        const refreshed = await request(`/hazard-identifications/${encodeURIComponent(recordId)}`)
        renderDetail(refreshed)
        renderContentAnalysis(analysis)
      } catch (error) {
        renderContentAnalysisError(error)
      }
    })
    .catch(error => setServiceStatus(error.message || '加载失败', 'error'))
}
