import './style.css'
import { registerSW } from 'virtual:pwa-register'
import { onUser, signIn, signOutUser, authHeaders } from './firebase.js'

registerSW({ immediate: true })

const app = document.querySelector('#app')

const DEFAULTS = {
  weeks_ahead: 1,
  years_back: 3,
  window_weeks: 3,
  max_minutes: 90,
  fantasy_count: 3,
  collection: 'Lunchbox',
}

const state = {
  user: null,
  phase: 'idle', // idle -> ready -> done
  busy: false,
  settings: { ...DEFAULTS },
  inputs: null,
  prompt: '',
  menu: '',
}

function set(patch) {
  Object.assign(state, patch)
  render()
}

onUser((user) => set({ user, phase: 'idle', inputs: null, prompt: '', menu: '' }))

function render() {
  app.innerHTML = `
    <main class="shell">
      <header class="topbar">
        ${
          state.user
            ? `<span class="who">${escapeHtml(state.user.email)} · <button id="signout" class="link" type="button">sign out</button></span>`
            : `<button id="signin" type="button" class="signin">Sign in with Google</button>`
        }
      </header>
      <div class="mark" aria-hidden="true"><img src="/favicon.svg" width="56" height="56" alt="" /></div>
      <h1>Thermoplan</h1>
      <p class="tag">Weekly menu planner for Cookidoo</p>
      ${state.user ? signedIn() : ''}
      <p id="status" class="note"></p>
    </main>
  `
  wire()
}

function signedIn() {
  const s = state.settings
  const idle = state.phase === 'idle'
  const label = state.busy
    ? idle
      ? 'Fetching…'
      : 'Generating…'
    : idle
      ? 'Fetch inputs'
      : 'Generate menu'

  return `
    <div class="actions">
      <button id="primary" type="button"${state.busy ? ' disabled' : ''}>${label}</button>
      ${
        idle
          ? ''
          : `<button id="reset" type="button" class="icon" title="Start over" aria-label="Start over"${
              state.busy ? ' disabled' : ''
            }>⟳</button>`
      }
    </div>

    ${
      idle
        ? `<label class="week">Week${weekSelect(s.weeks_ahead)}</label>
           <details class="settings">
             <summary>Settings</summary>
             <label>Years back<input data-k="years_back" type="number" min="1" max="6" value="${s.years_back}" /></label>
             <label>Window ± weeks<input data-k="window_weeks" type="number" min="0" max="8" value="${s.window_weeks}" /></label>
             <label>Max minutes<input data-k="max_minutes" type="number" min="10" max="600" step="10" value="${s.max_minutes}" /></label>
             <label>Collection<input data-k="collection" type="text" value="${escapeHtml(s.collection)}" /></label>
           </details>`
        : ''
    }

    ${state.inputs ? counts(state.inputs) : ''}

    ${
      idle
        ? ''
        : `<label class="field-label" for="prompt">Prompt</label>
           <textarea id="prompt" rows="14" spellcheck="false">${escapeHtml(state.prompt)}</textarea>`
    }

    ${
      state.menu
        ? `<label class="field-label" for="menu">Menu</label>
           <textarea id="menu" rows="18" spellcheck="false">${escapeHtml(state.menu)}</textarea>`
        : ''
    }
  `
}

function weekSelect(selected) {
  const now = new Date()
  const toMonday = (8 - now.getDay()) % 7 || 7
  const opts = []
  for (let w = 1; w <= 6; w++) {
    const mon = new Date(now)
    mon.setDate(now.getDate() + toMonday + 7 * (w - 1))
    const sun = new Date(mon)
    sun.setDate(mon.getDate() + 6)
    const prefix = w === 1 ? 'Next week' : `In ${w} weeks`
    opts.push(
      `<option value="${w}"${w === selected ? ' selected' : ''}>${prefix} · ${fmtDay(mon)}–${fmtDay(sun)}</option>`,
    )
  }
  return `<select data-k="weeks_ahead">${opts.join('')}</select>`
}

function fmtDay(d) {
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

function counts(d) {
  return `
    <ul class="counts">
      <li><b>${d.already_planned.reduce((n, x) => n + x.recipes.length, 0)}</b> already planned (locked)</li>
      <li><b>${d.history.length}</b> history days</li>
      <li><b>${d.collections.length}</b> collection recipes${
        d.collection_name ? ` — ${escapeHtml(d.collection_name)}` : ''
      }</li>
    </ul>`
}

function wire() {
  if (!state.user) {
    document
      .querySelector('#signin')
      ?.addEventListener('click', () => signIn().catch((e) => status(`Sign-in failed — ${e.message}`)))
    return
  }

  document.querySelector('#signout').addEventListener('click', () => signOutUser())

  document.querySelectorAll('[data-k]').forEach((el) =>
    el.addEventListener('input', () => {
      const k = el.dataset.k
      state.settings[k] = k === 'collection' ? el.value : Number(el.value)
    }),
  )
  document.querySelector('#prompt')?.addEventListener('input', (e) => (state.prompt = e.target.value))
  document.querySelector('#menu')?.addEventListener('input', (e) => (state.menu = e.target.value))

  document
    .querySelector('#reset')
    ?.addEventListener('click', () => set({ phase: 'idle', inputs: null, prompt: '', menu: '' }))

  document
    .querySelector('#primary')
    .addEventListener('click', () => (state.phase === 'idle' ? fetchInputs() : generate()))
}

async function apiPost(path, body) {
  // On 403, the ID token may just be stale (access granted after sign-in) -
  // force a fresh token and retry once.
  for (const force of [false, true]) {
    const res = await fetch(path, {
      method: 'POST',
      headers: { ...(await authHeaders(force)), 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (res.status !== 403 || force) return res
  }
}

async function fetchInputs() {
  set({ busy: true })
  status('Fetching from Cookidoo… this can take ~30s')
  try {
    const res = await apiPost('/api/prepare', state.settings)
    const text = await res.text()
    if (!res.ok) throw new Error(`${res.status} — ${text.slice(0, 300)}`)
    const d = JSON.parse(text)
    set({ busy: false, phase: 'ready', inputs: d, prompt: d.prompt, menu: '' })
    status(`Week of ${d.week_of}`)
  } catch (e) {
    set({ busy: false })
    status(`Failed — ${e.message}`)
  }
}

async function generate() {
  set({ busy: true })
  status('Asking the model… this can take ~30s')
  try {
    const d = state.inputs
    const res = await apiPost('/api/generate', {
      prompt: state.prompt,
      history: d.history,
      collections: d.collections,
      already_planned: d.already_planned,
    })
    const text = await res.text()
    if (!res.ok) throw new Error(`${res.status} — ${text.slice(0, 300)}`)
    const { menu } = JSON.parse(text)
    set({ busy: false, phase: 'done', menu })
    status('')
  } catch (e) {
    set({ busy: false })
    status(`Failed — ${e.message}`)
  }
}

function status(t) {
  const el = document.querySelector('#status')
  if (el) el.textContent = t
}

function escapeHtml(s) {
  return String(s).replace(
    /[&<>"]/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c],
  )
}
