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

const SOURCE_LABEL = {
  already_planned: 'locked',
  history: 'history',
  collections: 'collection',
  fantasy: 'fantasy',
  other: 'new',
}

const state = {
  user: null,
  phase: 'idle', // idle -> ready -> done
  busy: false,
  settings: { ...DEFAULTS },
  inputs: null,
  prompt: '',
  menu: null, // { days: [{ date, weekday, meals: [{ _id, meal, recipe_name, recipe_id, source, note }] }] }
}

let entrySeq = 0

function set(patch) {
  Object.assign(state, patch)
  render()
}

onUser((user) => set({ user, phase: 'idle', inputs: null, prompt: '', menu: null }))

function render() {
  app.innerHTML = `
    <main class="shell">
      ${
        state.user
          ? `<header class="topbar"><span class="who">${escapeHtml(state.user.email)} · <button id="signout" class="link" type="button">sign out</button></span></header>`
          : ''
      }
      <div class="mark" aria-hidden="true"><img src="/favicon.svg" width="56" height="56" alt="" /></div>
      <h1>Thermoplan</h1>
      <p class="tag">Weekly menu planner for Cookidoo</p>
      ${
        state.user
          ? signedIn()
          : `<button id="signin" type="button">Sign in with Google</button>`
      }
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
        : `<details class="prompt-box"${state.menu ? '' : ' open'}>
             <summary>Prompt</summary>
             <textarea id="prompt" rows="14" spellcheck="false">${escapeHtml(state.prompt)}</textarea>
           </details>`
    }

    ${state.menu ? gallery(state.menu) : ''}
    ${
      state.menu
        ? `<button id="push" type="button"${state.busy ? ' disabled' : ''}>Push to Cookidoo calendar</button>`
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

function gallery(menu) {
  const days = (menu.days || [])
    .map(
      (day) => `
      <section class="day">
        <h3>${escapeHtml(day.weekday || '')} <span>${escapeHtml(day.date || '')}</span></h3>
        <div class="cards">
          ${
            (day.meals || []).map(card).join('') ||
            `<p class="empty">nothing planned</p>`
          }
        </div>
      </section>`,
    )
    .join('')
  return `<div class="gallery">${days}</div>`
}

function card(m) {
  const src = SOURCE_LABEL[m.source] || m.source || ''
  return `
    <article class="card">
      <button class="card-x" data-remove="${m._id}" title="Remove" aria-label="Remove">×</button>
      <span class="card-meal">${escapeHtml(m.meal || '')}</span>
      <span class="card-name">${escapeHtml(m.recipe_name || '')}</span>
      ${m.note ? `<span class="card-note">${escapeHtml(m.note)}</span>` : ''}
      <span class="card-src src-${escapeHtml(m.source || 'other')}">${escapeHtml(src)}</span>
    </article>`
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

  document.querySelectorAll('[data-remove]').forEach((el) =>
    el.addEventListener('click', () => removeEntry(Number(el.dataset.remove))),
  )

  document
    .querySelector('#reset')
    ?.addEventListener('click', () => set({ phase: 'idle', inputs: null, prompt: '', menu: null }))

  document
    .querySelector('#primary')
    .addEventListener('click', () => (state.phase === 'idle' ? fetchInputs() : generate()))

  document.querySelector('#push')?.addEventListener('click', pushToCalendar)
}

function norm(s) {
  return String(s)
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '') // strip accents
    .replace(/[^a-z0-9\s]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Resolve each gallery entry to a real Cookidoo recipe id, using the datasets
 *  we fetched. Returns { days: [{date, recipe_ids}], unresolved: [labels] }. */
function resolveMenu() {
  const byName = new Map()
  const known = new Set()
  const add = (id, name) => {
    if (!id) return
    known.add(String(id))
    if (name) byName.set(norm(name), String(id))
  }
  const d = state.inputs
  d.already_planned.forEach((day) => day.recipes.forEach((r) => add(r.id, r.name)))
  d.history.forEach((day) => day.recipes.forEach((r) => add(r.id, r.name)))
  d.collections.forEach((r) => add(r.id, r.name))

  const byDate = {}
  const unresolved = []
  for (const day of state.menu.days) {
    for (const m of day.meals || []) {
      let id = m.recipe_id && String(m.recipe_id).trim()
      if (!id || !known.has(id)) id = byName.get(norm(m.recipe_name)) || null
      if (id) (byDate[day.date] ||= []).push(id)
      else unresolved.push(`${day.weekday} — ${m.recipe_name}`)
    }
  }
  return {
    days: Object.entries(byDate).map(([date, recipe_ids]) => ({ date, recipe_ids })),
    unresolved,
  }
}

async function pushToCalendar() {
  const { days, unresolved } = resolveMenu()
  const count = days.reduce((n, x) => n + x.recipe_ids.length, 0)
  if (!count) {
    status('Nothing to push — no recipes could be matched to Cookidoo ids')
    return
  }

  let msg = `Add ${count} recipe(s) to the Cookidoo calendar?`
  if (unresolved.length)
    msg += `\n\nSkipped (no Cookidoo id):\n- ${unresolved.join('\n- ')}`
  if (!confirm(msg)) return

  set({ busy: true })
  status('Pushing to Cookidoo…')
  try {
    const res = await apiPost('/api/save', { days })
    const text = await res.text()
    if (!res.ok) throw new Error(`${res.status} — ${text.slice(0, 300)}`)
    const r = JSON.parse(text)
    set({ busy: false })
    const bits = [`added ${r.added}`, `${r.already_there} already there`]
    if (r.unsupported.length) bits.push(`${r.unsupported.length} unsupported`)
    status(bits.join(' · '))
  } catch (e) {
    set({ busy: false })
    status(`Failed — ${e.message}`)
  }
}

function removeEntry(id) {
  for (const day of state.menu.days) day.meals = (day.meals || []).filter((m) => m._id !== id)
  render()
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
    set({ busy: false, phase: 'ready', inputs: d, prompt: d.prompt, menu: null })
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
    set({ busy: false, phase: 'done', menu: withIds(menu) })
    status('')
  } catch (e) {
    set({ busy: false })
    status(`Failed — ${e.message}`)
  }
}

function withIds(menu) {
  for (const day of menu.days || [])
    for (const m of day.meals || []) m._id = ++entrySeq
  return menu
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
