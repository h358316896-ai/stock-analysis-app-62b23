// 简单原型交互与假数据
document.addEventListener('DOMContentLoaded', ()=>{
  const hotList = document.getElementById('hotList')
  const stockTitle = document.getElementById('stockTitle')
  const stockPrice = document.getElementById('stockPrice')
  const priceDelta = document.getElementById('priceDelta')
  const searchBtn = document.getElementById('searchBtn')
  const symbolInput = document.getElementById('symbol')
  const marketSelect = document.getElementById('market')
  const onboardModal = document.getElementById('onboardModal')
  const onboardStart = document.getElementById('onboardStart')
  const onboardDismiss = document.getElementById('onboardDismiss')

  const API_BASE = window.API_BASE || 'http://localhost:5000'

  // 假热榜数据
  const hot = [
    {name:'贵州茅台 600519', change:'+2.3%'},
    {name:'宁德时代 300750', change:'-1.2%'},
    {name:'平安银行 000001', change:'+0.4%'}
  ]
  hotList.innerHTML = hot.map(h=>`<li>${h.name} <span style="color:#6b7280">${h.change}</span></li>`).join('')

  async function fetchQuote(symbol, market){
    try{
      const res = await fetch(`${API_BASE}/quote?symbol=${encodeURIComponent(symbol)}&market=${encodeURIComponent(market)}`)
      if(!res.ok) throw new Error('fetch failed')
      return await res.json()
    }catch(e){
      console.warn('使用本地假数据，真实代理不可用:', e.message)
      return null
    }
  }

  async function showStock(symbol, market){
    stockTitle.textContent = symbol || '示例：600519';
    const data = await fetchQuote(symbol, market)
    if(data && data.price){
      stockPrice.textContent = data.price
      priceDelta.textContent = (data.change_percent>0?'+':'')+data.change_percent+'%'
    }else{
      // 回退到随机假数据
      const price = (Math.random()*1000+10).toFixed(2)
      const delta = ((Math.random()-0.5)*4).toFixed(2)
      stockPrice.textContent = price
      priceDelta.textContent = (delta>0?'+':'')+delta+'%'
    }

    // 延迟加载图表占位（模拟降低首屏渲染成本）
    // 请求历史数据并绘制 K 线（如果代理可用）
    setTimeout(async ()=>{
      const hist = await fetchHistory(symbol, market)
      if(hist && hist.length>0){
        await loadChartScripts()
        renderCandlestick(hist)
        document.getElementById('chartPlaceholder').style.display = 'none'
      } else {
        document.getElementById('chartPlaceholder').textContent = '图表数据不可用（回退占位）'
      }
    }, 700)
  }

  searchBtn.addEventListener('click', ()=>{
    const s = symbolInput.value.trim() || '600519'
    const m = marketSelect.value || 'cn'
    showStock(s, m)
    // 埋点：用户搜索股票
    trackEvent('search_symbol', { symbol: s, market: m })
  })

  const freeStartBtn = document.getElementById('freeStartBtn')
  const enterBtn = document.getElementById('enterBtn')
  const trialBtn = document.getElementById('trialBtn')
  if(freeStartBtn){
    freeStartBtn.addEventListener('click', ()=> trackEvent('click_free_start'))
  }
  if(enterBtn){
    enterBtn.addEventListener('click', ()=> trackEvent('click_enter_terminal'))
  }
  if(trialBtn){
    trialBtn.addEventListener('click', ()=> trackEvent('click_trial'))
  }

  // 初始示例
  showStock('600519','cn')

  // 首访引导逻辑：如果 localStorage 中没有标记，则显示引导
  try{
    const seen = localStorage.getItem('stock_onboard_shown')
    if(!seen){
      if(onboardModal){ onboardModal.setAttribute('aria-hidden','false') }
    }
  }catch(e){/* ignore */}

  if(onboardStart){
    onboardStart.addEventListener('click', ()=>{
      if(onboardModal) onboardModal.setAttribute('aria-hidden','true')
      try{ localStorage.setItem('stock_onboard_shown','1') }catch(e){}
      // focus input for quick start
      symbolInput && symbolInput.focus()
      trackEvent('onboard_start')
    })
  }
  if(onboardDismiss){
    onboardDismiss.addEventListener('click', ()=>{
      if(onboardModal) onboardModal.setAttribute('aria-hidden','true')
      try{ localStorage.setItem('stock_onboard_shown','1') }catch(e){}
      trackEvent('onboard_dismiss')
    })
  }
})

// ---------------- Chart integration ----------------
async function fetchHistory(symbol, market){
  const API_BASE = window.API_BASE || 'http://localhost:5000'
  try{
    const res = await fetch(`${API_BASE}/history?symbol=${encodeURIComponent(symbol)}&market=${encodeURIComponent(market)}&period=60d&interval=1d`)
    if(!res.ok) return null
    const j = await res.json()
    return j.records || null
  }catch(e){
    return null
  }
}

function loadScript(src){
  return new Promise((resolve, reject)=>{
    if(document.querySelector(`script[src="${src}"]`)) return resolve()
    const s = document.createElement('script')
    s.src = src
    s.onload = ()=>resolve()
    s.onerror = ()=>reject(new Error('load failed '+src))
    document.head.appendChild(s)
  })
}

function trackEvent(eventName, params={}){
  try{
    if(window.gtag){
      gtag('event', eventName, params)
    }
  }catch(e){
    console.warn('gtag trackEvent failed', e)
  }
}

async function loadChartScripts(){
  // Load Chart.js and chartjs-chart-financial plugin from CDN
  const chartCdn = 'https://cdn.jsdelivr.net/npm/chart.js'
  const finCdn = 'https://cdn.jsdelivr.net/npm/chartjs-chart-financial@3.3.0/dist/chartjs-chart-financial.min.js'
  await loadScript(chartCdn)
  await loadScript(finCdn)
}

let _chart = null
function renderCandlestick(records){
  if(typeof Chart === 'undefined' || typeof Chart.FinancialController === 'undefined'){
    console.warn('Chart scripts not loaded')
    return
  }
  const ctx = document.getElementById('chartCanvas').getContext('2d')
  const data = records.map(r=>({x:new Date(r.t), o:r.o, h:r.h, l:r.l, c:r.c}))
  if(_chart){ _chart.destroy(); _chart = null }
  _chart = new Chart(ctx, {
    type: 'candlestick',
    data: {datasets:[{label:'Price',data:data}]},
    options: {
      plugins:{legend:{display:false}},
      scales:{x:{type:'time',time:{unit:'day'}},y:{position:'right'}}
    }
  })
}
