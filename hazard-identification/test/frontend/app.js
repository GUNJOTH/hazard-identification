const params = new URLSearchParams(window.location.search)
const defaultApi = window.location.port === '8787'
  ? `${window.location.origin}/api/v1`
  : 'http://127.0.0.1:8787/api/v1'
const API_BASE = (params.get('api') || defaultApi).replace(/\/$/, '')

const $ = id => document.getElementById(id)

function setServiceStatus(text, type) {
  const node = $('serviceStatus')
  node.textContent = text
  node.className = `service-status is-${type}`
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`
    try {
      const payload = await response.json()
      detail = typeof payload.detail === 'string' ? payload.detail : detail
    } catch (error) {
      // 保留状态码兜底提示
    }
    throw new Error(detail)
  }
  return response.json()
}

function analysisUrl(id) {
  return `./analysis.html?id=${encodeURIComponent(id)}&api=${encodeURIComponent(API_BASE)}`
}

function renderRecords(records) {
  const keyword = $('keywordInput').value.trim().toLowerCase()
  const filtered = records.filter(item => [
    item.description, item.category, item.type, item.location, item.equipment_name
  ].join(' ').toLowerCase().includes(keyword))
  $('filterTotal').textContent = `共 ${filtered.length} 条`
  if (!filtered.length) {
    $('recordList').innerHTML = '<div class="list-empty">暂无匹配的隐患记录</div>'
    return
  }
  $('recordList').innerHTML = filtered.map(item => {
    const major = item.level === '重大隐患'
    return `
      <article class="record-card" data-record-url="${analysisUrl(item.id)}">
        <div class="record-card__top">
          <span class="record-card__category">隐患单</span>
          <span class="record-item__level ${major ? 'major' : ''}">${item.level || '待确认'}</span>
        </div>
        <div class="record-card__title">${item.description || '待补充隐患描述'}</div>
        <div class="record-card__fields">
          <div><span>隐患类别</span><strong>${item.category || '待分类'}</strong></div>
          <div><span>隐患类型</span><strong>${item.type || '待确认'}</strong></div>
          <div><span>设备名称</span><strong>${item.equipment_name || '待现场确认'}</strong></div>
          <div><span>发现来源</span><strong>${item.discovery_source || '隐患排查'}</strong></div>
          <div><span>整改时限</span><strong>${item.rectification_deadline || '待确认'}</strong></div>
        </div>
        <div class="record-card__footer">
          <span>${item.image_count || 0} 张图片 · ${item.manual_review_required ? '需人工复核' : '已识别'}</span>
          <button class="analysis-button" data-record-url="${analysisUrl(item.id)}" type="button">隐患分析 →</button>
        </div>
      </article>
    `
  }).join('')
}

async function loadRecords() {
  try {
    const payload = await request('/hazard-identifications?page=1&page_size=50')
    const records = payload.items || []
    $('recordTotal').textContent = records.length
    $('majorTotal').textContent = records.filter(item => item.level === '重大隐患').length
    $('reviewTotal').textContent = records.filter(item => item.manual_review_required).length
    renderRecords(records)
    setServiceStatus('服务在线', 'online')
    return records
  } catch (error) {
    $('recordTotal').textContent = '0'
    $('majorTotal').textContent = '0'
    $('reviewTotal').textContent = '0'
    $('recordList').innerHTML = `<div class="list-empty">${error.message}<br><small>请确认 8787 后端已启动</small></div>`
    setServiceStatus('服务不可用', 'error')
    return []
  }
}

let records = []
$('keywordInput').addEventListener('input', () => renderRecords(records))
$('refreshButton').addEventListener('click', async () => { records = await loadRecords() })
$('recordList').addEventListener('click', event => {
  const card = event.target.closest('[data-record-url]')
  if (card) window.location.href = card.dataset.recordUrl
})

loadRecords()
