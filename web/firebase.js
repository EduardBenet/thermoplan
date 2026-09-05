// Firebase web setup — App Check only, for now.
//
// These values are NOT secret: they identify the project, they don't grant
// access. Copy them from Firebase console -> Project settings -> General ->
// "Your apps" -> SDK setup and configuration.
import { initializeApp } from 'firebase/app'
import { initializeAppCheck, ReCaptchaV3Provider, getToken } from 'firebase/app-check'

const firebaseConfig = {
  apiKey: 'TODO-from-console',
  authDomain: 'thermoplan-benetmilian.firebaseapp.com',
  projectId: 'thermoplan-benetmilian',
  appId: 'TODO-from-console',
}

// reCAPTCHA v3 site key: Firebase console -> App Check -> your web app -> reCAPTCHA v3.
const RECAPTCHA_V3_SITE_KEY = 'TODO-from-console'

// On `npm run dev` reCAPTCHA can't attest localhost. This prints a debug token
// to the browser console on first load; register it under App Check -> Manage
// debug tokens so local calls are accepted.
if (import.meta.env.DEV) {
  self.FIREBASE_APPCHECK_DEBUG_TOKEN = true
}

const app = initializeApp(firebaseConfig)

const appCheck = initializeAppCheck(app, {
  provider: new ReCaptchaV3Provider(RECAPTCHA_V3_SITE_KEY),
  isTokenAutoRefresh: true,
})

/** Headers that make an /api/* call pass the function's App Check gate. */
export async function apiHeaders() {
  const { token } = await getToken(appCheck)
  return { 'X-Firebase-AppCheck': token }
}
