// Firebase web setup — Auth only, for now.
//
// These values are NOT secret: they identify the project, they don't grant
// access. From Firebase console -> Project settings -> General -> "Your apps".
import { initializeApp } from 'firebase/app'
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
} from 'firebase/auth'

const firebaseConfig = {
  apiKey: 'AIzaSyAV0yHB3eDYKJsCBBNxdVE6Hmq3oZkqA2s',
  authDomain: 'thermoplan-benetmilian.firebaseapp.com',
  projectId: 'thermoplan-benetmilian',
  storageBucket: 'thermoplan-benetmilian.firebasestorage.app',
  messagingSenderId: '83995178357',
  appId: '1:83995178357:web:7238e8f3fb7cb4d921cf3c',
}

const app = initializeApp(firebaseConfig)
const auth = getAuth(app)
const provider = new GoogleAuthProvider()

/** Subscribe to sign-in state. Calls back with a User, or null when signed out. */
export function onUser(cb) {
  return onAuthStateChanged(auth, cb)
}

export function signIn() {
  return signInWithPopup(auth, provider)
}

export function signOutUser() {
  return signOut(auth)
}

/** Authorization header for an /api/* call. Throws if not signed in. */
export async function authHeaders() {
  const user = auth.currentUser
  if (!user) throw new Error('Not signed in')
  return { Authorization: `Bearer ${await user.getIdToken()}` }
}
