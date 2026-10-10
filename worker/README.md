# Shared launch verification setup

GitHub Pages cannot accept writes. This project uses a Cloudflare Worker to update `data/verified_launches.json` through GitHub's API. Visitors do not need GitHub accounts.

## One-time setup

1. In GitHub, create a **fine-grained personal access token** limited to `pbangiola/southern-lake-michigan-flow` with **Contents: Read and write**. Do not commit or paste this token into website code.
2. Create a Cloudflare Worker named `flow-launch-verification`. Paste the contents of `worker/launch-verification.js` as its code and deploy it.
3. In Cloudflare Worker **Settings → Variables and Secrets**, add an encrypted **secret** named `GITHUB_TOKEN` containing the token. Redeploy if prompted.
4. Copy the deployed Worker URL (ending in `.workers.dev`) into `web/launch-api-config.js` as `window.LAUNCH_VERIFICATION_API='https://YOUR-WORKER.workers.dev';`, commit and push.
5. Visit the Pages site, verify a launch, then check `data/verified_launches.json` for its ID. Wait for GitHub Pages to publish the updated file, and reload from a second browser to confirm the green marker is shared.

The Worker accepts only POSTs from `https://pbangiola.github.io` and validates the launch ID and requested boolean state. The GitHub token stays server-side. Origin restrictions are not authentication: a determined caller can still invoke a public endpoint, so **this is a community-editable flag, not independently verified access information**. If abuse occurs, add Cloudflare rate limiting, bot challenges, or an authenticated review flow.

Without a Worker URL, the site retains browser-local verification and does **not** claim to write shared data. Changes made in the browser before the shared backend is enabled are not automatically published.
