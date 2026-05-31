<script setup>
import { computed, ref } from 'vue'
import { withBase } from 'vitepress'

const apiBase = (import.meta.env.VITE_FITOPS_DEPLOY_API_BASE_URL || '').replace(/\/+$/, '')
const hfToken = ref('')
const hfRepo = ref('')
const githubToken = ref('')
const githubRepo = ref('')
const stravaClientId = ref('')
const stravaClientSecret = ref('')
const password = ref('')
const passwordConfirm = ref('')
const jobId = ref('')
const status = ref('idle')
const error = ref('')
const events = ref([])
const result = ref(null)
const totp = ref(null)

const computedCallbackDomain = computed(() => {
  const repo = hfRepo.value.trim()
  if (!repo.includes('/')) return ''
  const [owner, space] = repo.split('/', 2)
  if (!owner || !space) return ''
  return `${owner}-${space}.hf.space`
})

const callbackDomain = computed(() => {
  return result.value?.callback_domain || computedCallbackDomain.value
})

const canSubmit = computed(() => {
  return Boolean(
    apiBase &&
    hfToken.value.trim() &&
    githubToken.value.trim() &&
    githubRepo.value.trim() &&
    password.value &&
    password.value === passwordConfirm.value &&
    status.value !== 'running'
  )
})

function addEvent(message, level = 'info') {
  events.value.push({ message, level, at: new Date().toISOString() })
}

async function startDeploy() {
  error.value = ''
  events.value = []
  result.value = null
  totp.value = null
  status.value = 'running'
  addEvent('Starting deploy job...')

  try {
    const response = await fetch(`${apiBase}/api/deploy/hf/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        hf_token: hfToken.value.trim(),
        hf_repo: hfRepo.value.trim() || null,
        github_token: githubToken.value.trim(),
        github_repo: githubRepo.value.trim(),
        dashboard_password: password.value,
        strava_client_id: stravaClientId.value.trim() || null,
        strava_client_secret: stravaClientSecret.value.trim() || null
      })
    })

    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || `Deploy API returned ${response.status}`)
    }

    jobId.value = payload.job_id
    if (payload.totp) {
      totp.value = payload.totp
    }
    addEvent(`Job ${payload.job_id} created.`)
    streamEvents(payload.job_id)
  } catch (err) {
    status.value = 'failed'
    error.value = err.message || 'Deploy failed to start.'
    addEvent(error.value, 'error')
  }
}

function streamEvents(id) {
  const source = new EventSource(`${apiBase}/api/deploy/hf/jobs/${id}/events`)

  source.addEventListener('message', (event) => {
    const payload = JSON.parse(event.data)
    if (payload.message) {
      addEvent(payload.message, payload.level || 'info')
    }
    if (payload.totp) {
      totp.value = payload.totp
    }
    if (payload.status) {
      status.value = payload.status
    }
    if (payload.result) {
      result.value = payload.result
    }
    if (payload.error) {
      error.value = payload.error
    }
    if (payload.status === 'succeeded' || payload.status === 'failed') {
      source.close()
    }
  })

  source.addEventListener('error', () => {
    addEvent('Lost the live event stream. Refresh job status from the Deploy API if the job is still running.', 'warn')
    source.close()
  })
}
</script>

<template>
  <div class="deploy-wizard">
    <p v-if="!apiBase" class="deploy-alert">
      The docs site is not configured with <code>VITE_FITOPS_DEPLOY_API_BASE_URL</code>, so the live wizard is disabled on this build.
    </p>

    <div class="deploy-intro">
      <h2 id="deploy-online">Deploy FitOps Online</h2>
      <p>Create a private HuggingFace Space, protect it with password + 2FA, and optionally prefill Strava setup so your first dashboard login goes straight to OAuth and sync.</p>
      <div class="deploy-links">
        <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noopener">HF token</a>
        <a href="https://github.com/settings/tokens" target="_blank" rel="noopener">GitHub token</a>
        <a href="https://www.strava.com/settings/api" target="_blank" rel="noopener">Strava API settings</a>
        <a :href="withBase('/getting-started/authentication')" target="_blank" rel="noopener">Strava guide</a>
        <a :href="withBase('/assets/fitops-icon.png')" target="_blank" rel="noopener">FitOps logo</a>
      </div>
    </div>

    <div class="deploy-grid">
      <label>
        <span>HuggingFace token</span>
        <input v-model="hfToken" type="password" autocomplete="off" placeholder="hf_xxx" />
      </label>
      <label>
        <span>HF Space repo</span>
        <input v-model="hfRepo" autocomplete="off" placeholder="yourname/fitops-dashboard" />
        <small>Optional. If empty, FitOps uses your HF username and <code>fitops-dashboard</code>.</small>
      </label>
      <label>
        <span>GitHub token</span>
        <input v-model="githubToken" type="password" autocomplete="off" placeholder="ghp_xxx" />
      </label>
      <label>
        <span>GitHub backup repo</span>
        <input v-model="githubRepo" autocomplete="off" placeholder="yourname/fitops-backups" />
      </label>
      <label>
        <span>Strava Client ID</span>
        <input v-model="stravaClientId" autocomplete="off" placeholder="175267" />
        <small>Optional. Find it on the Strava API settings page.</small>
      </label>
      <label>
        <span>Strava Client Secret</span>
        <input v-model="stravaClientSecret" type="password" autocomplete="off" placeholder="Paste after clicking Show in Strava" />
        <small>Optional. This pre-fills setup; OAuth still happens after deploy.</small>
      </label>
      <label>
        <span>Dashboard password</span>
        <input v-model="password" type="password" autocomplete="new-password" />
      </label>
      <label>
        <span>Confirm password</span>
        <input v-model="passwordConfirm" type="password" autocomplete="new-password" />
      </label>
    </div>

    <p v-if="callbackDomain" class="deploy-hint">
      Strava Authorization Callback Domain: <code>{{ callbackDomain }}</code>
    </p>
    <p v-else class="deploy-hint">
      If you leave the HF Space repo empty, the exact Strava callback domain appears after deploy.
    </p>

    <button class="deploy-button" :disabled="!canSubmit" @click="startDeploy">
      Start Deployment
    </button>

    <p v-if="password && passwordConfirm && password !== passwordConfirm" class="deploy-alert">
      Passwords do not match.
    </p>

    <section v-if="totp" class="deploy-panel">
      <h3>Two-Factor Login Key</h3>
      <p>Add this key to your authenticator app. You will need its 6-digit code when signing in to the deployed dashboard.</p>
      <code>{{ totp.manual_key }}</code>
    </section>

    <section v-if="events.length" class="deploy-panel">
      <h3>Progress</h3>
      <ol class="deploy-events">
        <li v-for="event in events" :key="event.at + event.message" :class="`deploy-event-${event.level}`">
          {{ event.message }}
        </li>
      </ol>
    </section>

    <section v-if="result" class="deploy-panel deploy-result">
      <h3>Your Dashboard Is Live</h3>
      <p><a :href="result.app_url" target="_blank" rel="noopener">{{ result.app_url }}</a></p>
      <p>HF Space: <a :href="result.space_url" target="_blank" rel="noopener">{{ result.space_url }}</a></p>
      <p>Strava Authorization Callback Domain: <code>{{ result.callback_domain }}</code></p>
      <p><a href="https://www.strava.com/settings/api" target="_blank" rel="noopener">Open Strava API settings</a></p>
    </section>

    <p v-if="error" class="deploy-alert">{{ error }}</p>
  </div>
</template>
