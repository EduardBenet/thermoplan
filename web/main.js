import './style.css'
import { registerSW } from 'virtual:pwa-register'

registerSW({ immediate: true })

const app = document.querySelector('#app')

app.innerHTML = `
  <main class="shell">
    <div class="mark" aria-hidden="true">
      <img src="/favicon.svg" width="56" height="56" alt="" />
    </div>
    <h1>Thermoplan</h1>
    <p class="tag">Weekly menu planner</p>
    <button id="plan" type="button">Fetch next week's inputs</button>
    <p id="status" class="note">
      Pulls history, saved collections and For You suggestions from Cookidoo.
    </p>
    <section id="out" hidden></section>
  </main>
`

const btn = document.querySelector('#plan')
const statusEl = document.querySelector('#status')
const out = document.querySelector('#out')

btn.addEventListener('click', async () => {
  btn.disabled = true
  out.hidden = true
  statusEl.textContent = 'Fetching from Cookidoo… this can take ~30s'

  try {
    const res = await fetch('/api/prepare', { method: 'POST' })
    const text = await res.text()
    if (!res.ok) throw new Error(`${res.status} — ${text.slice(0, 300)}`)

    const data = JSON.parse(text)
    statusEl.textContent = `Week of ${data.week_of}`
    out.innerHTML = `
      <ul class="counts">
        <li><b>${data.history.length}</b> history days (last ${yearsSpan(data)} years)</li>
        <li><b>${data.collections.length}</b> collection recipes${
          data.collection_name ? ` — ${escapeHtml(data.collection_name)}` : ' — no collection set'
        }</li>
        <li><b>${data.fantasy.length}</b> fantasy recipes under 90 min (${data.fantasy_skipped_no_time} skipped, no time)</li>
      </ul>
      <details>
        <summary>Prompt</summary>
        <pre>${escapeHtml(data.prompt)}</pre>
      </details>
      <details>
        <summary>Raw JSON</summary>
        <pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>
      </details>
    `
    out.hidden = false
  } catch (err) {
    statusEl.textContent = `Failed — ${err.message}`
  } finally {
    btn.disabled = false
  }
})

function yearsSpan(data) {
  const years = new Set(data.history.map((d) => d.years_back))
  return years.size || 0
}

function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c])
}
