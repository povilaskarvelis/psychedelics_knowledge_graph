# R2 public data and private API deployment

The public website remains a static Netlify project. The REST and MCP service is
a separate code-only container deployed from the same GitHub repository. Public
website data and API runtime data are both versioned in Cloudflare R2, but they
live in different buckets: the website-data bucket is public and the API bucket
is private. Neither generated release is committed to Git.

The checked-in `render.yaml` configures the container deployment. At startup,
the container privately downloads and verifies only `public_api.duckdb`,
`schema.json`, and `manifest.json`. The service has no bulk-download routes and
the build produces no public Parquet copies.

## One-time Cloudflare setup

1. Use the existing `psychedelics-kg-releases` bucket as the public website-data
   bucket. It remains connected to `data.psychedelicskg.com` and stores the graph
   payloads, Methods bibliography, Methods flow summary, and graph-inclusion
   audit.
2. Create a separate private API bucket, for example
   `psychedelics-kg-api-private`. Do not connect a custom domain and do not enable
   its `r2.dev` URL.
3. Decide whether these are normal buckets or EU-jurisdiction buckets. A normal
   bucket with a European location hint still uses the normal endpoint. Set
   the corresponding jurisdiction variable to `eu` only when Cloudflare
   explicitly identifies the bucket as an EU-jurisdiction bucket.
4. Create bucket-scoped **Object Read & Write** credentials for the local
   publisher. They must cover the browser and API buckets; separate tokens are
   preferable when convenient.
5. Create a separate **Object Read only** token scoped only to the private API
   bucket for Render. Render must not receive a write token or browser-bucket
   credentials.

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
PKG_R2_BROWSER_PREFIX=browser
PKG_R2_JURISDICTION=

PKG_API_R2_ACCOUNT_ID=<cloudflare-account-id>
PKG_API_R2_BUCKET=psychedelics-kg-api-private
PKG_API_R2_ACCESS_KEY_ID=<private-api-publisher-access-key-id>
PKG_API_R2_SECRET_ACCESS_KEY=<private-api-publisher-secret-access-key>
PKG_API_R2_PREFIX=query-api
PKG_API_R2_JURISDICTION=
```

Use the matching jurisdiction variable for an EU-jurisdiction bucket.
Alternatively, set `PKG_R2_ENDPOINT_URL` or `PKG_API_R2_ENDPOINT_URL` to the
exact S3 endpoint Cloudflare shows for that bucket.

Load those variables into the shell and publish the already-active release:

```bash
set -a
source .env
set +a
python3 pipeline/publish/publish_browser_payload_r2.py
python3 pipeline/publish/publish_query_api_r2.py
```

The publishers validate every required local artifact, upload objects under
immutable release prefixes, verify R2 object size and SHA-256 metadata, and
replace the small public `browser/active.json` and private
`query-api/active/catalogue-v2.json` pointers only after their release files are
complete. Re-running them is safe: matching objects are reused, while a
conflicting immutable object stops activation.

## Deploy the API from GitHub

Publish the first R2 release before creating the service; otherwise its first
startup correctly fails because no active remote database exists.

1. Commit and push the API code and `render.yaml` to GitHub.
2. In Render, choose **New > Blueprint**, connect the GitHub repository, and use
   the root `render.yaml` Blueprint.
3. When prompted, enter the deployed API's private-bucket read-only values for:
   `PKG_API_R2_ACCOUNT_ID`, `PKG_API_R2_BUCKET`,
   `PKG_API_R2_ACCESS_KEY_ID`, and `PKG_API_R2_SECRET_ACCESS_KEY`.
4. If the bucket uses the EU jurisdiction, add
   `PKG_API_R2_JURISDICTION=eu` to the Render service environment before deploying.
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

Connect `data.psychedelicskg.com` only to the browser bucket under **Settings >
Custom Domains**. The custom domain makes the allowlisted browser payloads
readable through Cloudflare and allows them to use Cloudflare's cache. Add an R2
CORS policy allowing `GET` and `HEAD` from both website origins:

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

The website reads `https://data.psychedelicskg.com/browser/active.json`, then
loads only the immutable graph and Methods files named by that validated
pointer. Production does not silently fall back to Netlify files when R2 is
unavailable. The graph UI can use its local generated graph pointer during
development; the Methods page exercises the same R2 path used in production.

Because Cloudflare does not cache JSON by default, add a Cache Rule for the
immutable release objects:

- hostname equals `data.psychedelicskg.com`;
- URI path starts with `/browser/releases/`;
- Cache eligibility is **Eligible for cache**;
- Edge TTL respects the origin cache-control header.

Do not include `/browser/active.json` in that rule. The active pointer must be
revalidated so new releases become visible immediately, while the versioned
release files are safe to cache indefinitely.

Never connect the private API bucket to `data.psychedelicskg.com` or another
public hostname. Render reads that bucket only through authenticated S3 calls.

## One-time migration from the shared bucket

The earlier deployment stored browser and API objects together. After the first
successful private API publish and Render verification:

1. delete the `query-api/` prefix from the public browser bucket;
2. confirm that `https://data.psychedelicskg.com/query-api/active/catalogue-v2.json`
   no longer returns an object;
3. retain only `browser/` objects in the public bucket.

Do not perform this cleanup before the API is reading successfully from the new
private bucket. Deleting old objects is intentional and is not part of the
automatic publisher.

## Automatic deployment after data updates

Create a deploy hook in the Render service settings and put its secret URL only
in the local `.env` file:

```dotenv
PKG_DEPLOY_HOOK_URL=<render-deploy-hook-url>
```

For a new evidence/data release, run:

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
3. upload and verify the immutable browser and API releases;
4. switch their remote active pointers;
5. trigger a zero-downtime container deployment;
6. download and verify the new core database before the new instance is healthy.

For a change limited to authors, public fields, API code, or browser payloads,
keep the current evidence snapshot and run:

```bash
bash scripts/refresh_public_release.sh
```

This command loads the ignored `.env`, rebuilds both public outputs, gives them
one shared public release ID, validates every referenced graph and Methods file,
builds the code-only static site, publishes the matching public and private API
data to their versioned R2 pointers, and then triggers the deploy hook when
configured. Data updates no longer require committing generated payloads or
rebuilding Netlify. Use `NO_R2_PUBLISH=1` only for a local dry run.

If no deploy hook is configured, publishing still succeeds; manually redeploy or
restart the API service so it synchronizes the new active release.

## Failure and rollback behavior

- An upload or checksum failure leaves the previous versioned R2 active pointer untouched.
- A failed container sync leaves `/readyz` unavailable and catalogue requests
  return 503 while documentation and process health checks remain reachable.
- API pagination cursors remain bound to their release and return HTTP 409 after
  a release change.
- To roll back, promote the desired older local run and publish it again. The
  guarded promotion creates a new release ID while preserving the older
  immutable R2 objects for auditability.

## Public website-data layout

Public graph and Methods files are stored under immutable
`browser/releases/...` keys. The stable `browser/active.json` pointer contains
the release ID and the exact manifest, graph, dashboard, detail, bibliography,
Methods flow, and inclusion-audit object keys. The pointer is written last and
served with revalidation; versioned payload files use immutable one-year cache
headers. This keeps routine data refreshes independent of GitHub and Netlify
while preserving deterministic rollback to an older release.
