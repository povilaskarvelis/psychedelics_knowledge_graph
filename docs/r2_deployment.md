# R2 query API deployment

The public website remains a static Netlify project. The REST and MCP service is
a separate code-only container deployed from the same GitHub repository. Its
versioned data releases live in Cloudflare R2 and are never committed to Git.

The checked-in `render.yaml` configures the container deployment. At startup,
the container downloads and verifies only `public_api.duckdb`, `schema.json`,
and `manifest.json`. Database and Parquet download endpoints redirect clients to
R2, using short-lived signed URLs unless a public R2 custom domain is configured.

## One-time Cloudflare setup

1. In **Cloudflare > Storage & databases > R2**, enable R2 and create a bucket.
   `psychedelics-kg-releases` is a suitable name. Use the Standard storage class.
2. Decide whether this is a normal bucket or an EU-jurisdiction bucket. A normal
   bucket with a European location hint still uses the normal endpoint. Set
   `PKG_R2_JURISDICTION=eu` only if Cloudflare explicitly identifies the bucket
   as an EU-jurisdiction bucket.
3. Create a bucket-scoped **Object Read & Write** S3 API token for the local
   release publisher. Save its Access Key ID and Secret Access Key immediately.
4. Create a separate bucket-scoped **Object Read only** S3 API token for the
   deployed API. The Render service must not receive the write token.

No Admin token is required by the application or publisher.

## Configure the local publisher

Install the API/publisher dependencies:

```bash
python3 -m pip install -r services/query_api/requirements.txt
```

Put the publisher's read/write credentials in the ignored `.env` file:

```dotenv
PKG_R2_ACCOUNT_ID=<cloudflare-account-id>
PKG_R2_BUCKET=psychedelics-kg-releases
PKG_R2_ACCESS_KEY_ID=<publisher-access-key-id>
PKG_R2_SECRET_ACCESS_KEY=<publisher-secret-access-key>
PKG_R2_PREFIX=query-api
PKG_R2_JURISDICTION=
```

Use `PKG_R2_JURISDICTION=eu` for an EU-jurisdiction bucket. Alternatively, set
`PKG_R2_ENDPOINT_URL` to the exact S3 endpoint Cloudflare shows for the bucket.

Load those variables into the shell and publish the already-active release:

```bash
set -a
source .env
set +a
python3 pipeline/publish/publish_query_api_r2.py
```

The publisher verifies every local file against its manifest, uploads objects
under an immutable release prefix, verifies R2 object size and SHA-256 metadata,
and writes `query-api/active.json` last. Re-running it is safe: matching release
objects are reused, while a conflicting immutable object stops activation.

## Deploy the API from GitHub

Publish the first R2 release before creating the service; otherwise its first
startup correctly fails because no active remote database exists.

1. Commit and push the API code and `render.yaml` to GitHub.
2. In Render, choose **New > Blueprint**, connect the GitHub repository, and use
   the root `render.yaml` Blueprint.
3. When prompted, enter the deployed API's separate read-only values for:
   `PKG_R2_ACCOUNT_ID`, `PKG_R2_BUCKET`, `PKG_R2_ACCESS_KEY_ID`, and
   `PKG_R2_SECRET_ACCESS_KEY`.
4. If the bucket uses the EU jurisdiction, add
   `PKG_R2_JURISDICTION=eu` to the Render service environment before deploying.
5. If Render assigns a hostname other than
   `psychedelics-kg-api.onrender.com`, add the assigned hostname to
   `PKG_MCP_ALLOWED_HOSTS`.
6. Deploy and verify `/healthz`, `/docs`, and `/mcp` on the Render hostname.

The Blueprint uses `/healthz` as its process health check. The HTTP server starts
immediately so documentation and health checks remain available while the active
R2 database loads. `/readyz` returns 503 until the database has downloaded and
passed checksum validation; catalogue requests return a retryable 503 while it
is loading.

## Domain and browser access

Add `api.psychedelicskg.com` as a custom domain on the Render service, then add
the DNS record Render supplies at the current DNS provider. The checked-in
defaults already use:

```dotenv
PKG_PUBLIC_BASE_URL=https://api.psychedelicskg.com
PKG_CORS_ORIGINS=https://psychedelicskg.com,https://www.psychedelicskg.com
PKG_MCP_ALLOWED_HOSTS=api.psychedelicskg.com,psychedelics-kg-api.onrender.com
PKG_MCP_ALLOWED_ORIGINS=https://psychedelicskg.com,https://www.psychedelicskg.com
```

The bucket can remain private. In that mode, download endpoints issue signed R2
URLs valid for 15 minutes. If browser JavaScript will follow those URLs, add an
R2 CORS policy allowing `GET` and `HEAD` from both website origins. For example:

```json
[
  {
    "AllowedOrigins": [
      "https://psychedelicskg.com",
      "https://www.psychedelicskg.com"
    ],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

Later, a public R2 custom domain such as `data.psychedelicskg.com` can replace
signed download URLs. Set `PKG_R2_PUBLIC_BASE_URL=https://data.psychedelicskg.com`
on Render after the domain is active. This setting is optional and is not needed
for the initial private-bucket deployment.

## Automatic deployment after data updates

Create a deploy hook in the Render service settings and put its secret URL only
in the local `.env` file:

```dotenv
PKG_DEPLOY_HOOK_URL=<render-deploy-hook-url>
```

For every future data release, run:

```bash
set -a
source .env
set +a
ACTIVATE_DEFAULT=1 PUBLISH_QUERY_API_R2=1 \
  bash scripts/build_routed_kg_payload.sh <new-run-id>
```

The sequence is:

1. build and validate the normalized KG and narrow public catalogue;
2. make the local/UI release current;
3. upload and verify the immutable R2 release;
4. switch the remote active pointer;
5. trigger a zero-downtime container deployment;
6. download and verify the new core database before the new instance is healthy.

If no deploy hook is configured, publishing still succeeds; manually redeploy or
restart the API service so it synchronizes the new active release.

## Failure and rollback behavior

- An upload or checksum failure leaves the previous R2 `active.json` untouched.
- A failed container sync leaves `/readyz` unavailable and catalogue requests
  return 503 while documentation and process health checks remain reachable.
- API pagination cursors remain bound to their release and return HTTP 409 after
  a release change.
- To roll back, promote the desired older local run and publish it again. The
  guarded promotion creates a new release ID while preserving the older
  immutable R2 objects for auditability.

## Static browser payloads

This deployment removes the API database and bulk tables from GitHub. The
existing browser-detail JSON remains on the current Netlify path for now. Moving
that 41 MB detail payload to R2 requires enabling a public R2 data domain (or an
API-backed signed-URL loader) before removing it from Git, so that migration is
intentionally not activated until the R2 account and domain exist.
