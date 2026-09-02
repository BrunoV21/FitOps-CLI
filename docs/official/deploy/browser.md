# Deploy from the Browser

Use this page to create a private FitOps dashboard on HuggingFace Spaces without installing Python or running the CLI locally.

The browser wizard sends your deployment details to the FitOps Deploy API. The API runs the same HuggingFace deployment flow as `fitops deploy hf`, using the HuggingFace and GitHub tokens you provide for this one deployment job.

::: warning Security model
Tokens are sent to the Deploy API for the active job only. The hosted API keeps them in memory, redacts them from job events, and drops them when the job finishes or expires. If you prefer not to send tokens to the hosted API, use the [local CLI deploy flow](./huggingface.md).
:::

## What You Need

| Requirement | Why |
|---|---|
| HuggingFace account | Owns the private Space that runs your dashboard |
| HuggingFace write token | Lets FitOps create/update your Space |
| GitHub account | Owns the private backup repository |
| GitHub token with `repo` scope | Lets FitOps read/write backup releases and configure keepalive |
| Authenticator app | Stores the dashboard two-factor login key |
| Strava API app | Optional during deploy, but needed before activity sync |

Strava Client ID and Client Secret are optional in the wizard. If you provide them, FitOps stores them in the deployed Space and sends you straight to Strava OAuth on first setup. OAuth is still required before FitOps can sync activities.

## Deploy Wizard

<script setup>
import DeployWizard from '../.vitepress/theme/components/DeployWizard.vue'
</script>

<DeployWizard />

## After Deployment

1. Add the generated Authorization Callback Domain in [Strava API settings](https://www.strava.com/settings/api).
2. Open the dashboard URL shown by the wizard.
3. Sign in with your dashboard password and authenticator code.
4. Complete Strava OAuth in the deployed dashboard.
5. Wait for the first sync to finish, then open the dashboard.

## Prefer the Terminal?

The local CLI flow remains available and does not call the hosted Deploy API:

```bash
fitops deploy hf \
  --hf-token hf_xxxxxxxxxxxxxxxxxxxx \
  --hf-repo yourname/fitops-dashboard \
  --github-token ghp_xxxxxxxxxxxxxxxxxxxx \
  --github-repo yourname/fitops-backups \
  --strava-client-id 175267 \
  --strava-client-secret xxxxxxxxxxxxxxxxxxxx
```

See [HuggingFace Spaces](./huggingface.md) for the full local deployment reference.

## Deploy API Operator Notes

The browser wizard expects a hosted API running the FitOps deploy app. This repo includes a HuggingFace Space Docker context at `fitops/cloud/deploy_api_space/` and a GitHub Actions workflow that pushes it.

Create these GitHub repository settings before running **Deploy FitOps Deploy API Space**:

| GitHub setting | Type | Purpose |
|---|---|---|
| `HF_TOKEN` | Secret | HuggingFace token allowed to create/update the Deploy API Space |
| `FITOPS_DEPLOY_API_BASE_URL` | Variable | Public Deploy API base URL injected into the docs build |
| `FITOPS_DEPLOY_API_HF_SPACE_REPO` | Variable | Target Space repo, for example `yourname/fitops-deploy-api` |
| `FITOPS_DEPLOY_API_SPACE_URL` | Variable | Public Space URL used by the keepalive workflow |
| `FITOPS_DEPLOY_ALLOWED_ORIGINS` | Variable | Comma-separated docs origins allowed to call the API |

Optional GitHub variables:

| Variable | Default | Purpose |
|---|---:|---|
| `FITOPS_DEPLOY_RATE_LIMIT_PER_HOUR` | `5` | Job creation limit per client IP |
| `FITOPS_DEPLOY_MAX_CONCURRENT_JOBS` | `2` | Maximum in-process deploy jobs |
| `FITOPS_DEPLOY_JOB_TIMEOUT_SECONDS` | `900` | Deploy timeout |
| `FITOPS_DEPLOY_JOB_TTL_SECONDS` | `3600` | In-memory job retention |

The workflow creates or updates a private Docker Space and stores the runtime configuration as Space secrets. A second workflow pings `/health` every 20 minutes so the Deploy API Space stays warm.

For a manual API runtime, run:

```bash
uvicorn fitops.cloud.deploy_api:app --host 0.0.0.0 --port 7860
```

Configure these environment variables on the API runtime:

| Variable | Required | Purpose |
|---|---:|---|
| `FITOPS_DEPLOY_ALLOWED_ORIGINS` | yes | Comma-separated docs origins allowed to call the API |
| `FITOPS_DEPLOY_RATE_LIMIT_PER_HOUR` | no | Job creation limit per client IP, default `5` |
| `FITOPS_DEPLOY_MAX_CONCURRENT_JOBS` | no | Maximum in-process deploy jobs, default `2` |
| `FITOPS_DEPLOY_JOB_TIMEOUT_SECONDS` | no | Deploy timeout, default `900` |
| `FITOPS_DEPLOY_JOB_TTL_SECONDS` | no | In-memory job retention, default `3600` |

Configure the docs build with the public API base URL:

```bash
VITE_FITOPS_DEPLOY_API_BASE_URL=https://your-deploy-api.example.com npm run docs:build
```

The API stores jobs in memory only. Restarting the API clears running and completed jobs.
