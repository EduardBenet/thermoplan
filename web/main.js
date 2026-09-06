import './style.css'
import { registerSW } from 'virtual:pwa-register'
import { onUser, signIn, signOutUser, authHeaders } from './firebase.js'

registerSW({ immediate: true })

const app = document.querySelector('#app')

function render(user) {
  app.innerHTML = `
    <main class="shell">
      <div class="mark" aria-hidden="true">
        <img src="/favicon.svg" width="56" height="56" alt="" />
      </div>
      <h1>Thermoplan</h1>
      <p class="tag">Weekly menu planner for Cookidoo</p>
      ${user ? signedInControls(user) : `<button id="signin" type="button">Sign in with Google</button>`}
      <p id="status" class="note"></p>
      <section id="out" hidden></section>
    </main>
  `

  if (user) {
    wireSignedIn()
  } else {
    document
      .querySelector('#signin')
      .addEventListener('click', () => signIn().catch((err) => setStatus(`Sign-in failed — ${err.message}`)))
  }
}

function signedInControls(user) {
  return `
    <button id="plan" type="button">Fetch next week's inputs</button>
    <details class="settings">
      <summary>Settings</summary>
      <label>Years back<input id="s-years" type="number" min="1" max="6" value="3" /></label>
      <label>Window ± weeks<input id="s-window" type="number" min="0" max="8" value="3" /></label>
      <label>Max minutes<input id="s-max" type="number" min="10" max="600" step="10" value="90" /></label>
      <label>Fantasy count<input id="s-fantasy" type="number" min="0" max="20" value="3" /></label>
      <label>Collection<input id="s-collection" type="text" value="Lunchbox" /></label>
    </details>
    <p class="who">${escapeHtml(user.email)} · <button id="signout" class="link" type="button">sign out</button></p>
  `
}

function readSettings() {
  const int = (id) => Number(document.querySelector(id).value)
  return {
    years_back: int('#s-years'),
    window_weeks: int('#s-window'),
    max_minutes: int('#s-max'),
    fantasy_count: int('#s-fantasy'),
    collection: document.querySelector('#s-collection').value.trim(),
  }
}

function wireSignedIn() {
  document.querySelector('#signout').addEventListener('click', () => signOutUser())

  const btn = document.querySelector('#plan')
  const out = document.querySelector('#out')

  btn.addEventListener('click', async () => {
    btn.disabled = true
    out.hidden = true
    setStatus('Fetching from Cookidoo… this can take ~30s')

    try {
      const res = await fetch('/api/prepare', {
        method: 'POST',
        headers: { ...(await authHeaders()), 'Content-Type': 'application/json' },
        body: JSON.stringify(readSettings()),
      })
      const text = await res.text()
      if (!res.ok) throw new Error(`${res.status} — ${text.slice(0, 300)}`)

      const data = JSON.parse(text)
      setStatus(`Week of ${data.week_of}`)
      out.innerHTML = renderData(data)
      out.hidden = false
    } catch (err) {
      setStatus(`Failed — ${err.message}`)
    } finally {
      btn.disabled = false
    }
  })
}

function renderData(data) {
  return `
    <ul class="counts">
      <li><b>${data.already_planned.reduce((n, d) => n + d.recipes.length, 0)}</b> already planned (locked)</li>
      <li><b>${data.history.length}</b> history days</li>
      <li><b>${data.collections.length}</b> collection recipes${
        data.collection_name ? ` — ${escapeHtml(data.collection_name)}` : ''
      }</li>
      <li><b>${data.fantasy.length}</b> fantasy recipes under 90 min (${data.fantasy_skipped_no_time} skipped)</li>
    </ul>
    <label class="prompt-label" for="prompt">Prompt — edit before generating</label>
    <textarea id="prompt" rows="18" spellcheck="false">${escapeHtml(data.prompt)}</textarea>
  `
}

function setStatus(text) {
  const el = document.querySelector('#status')
  if (el) el.textContent = text
}

function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c])
}

onUser(render)
