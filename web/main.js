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
    <button id="plan" type="button" disabled>Plan next week</button>
    <p class="note">Placeholder build &mdash; login and the planning backend come next.</p>
  </main>
`
