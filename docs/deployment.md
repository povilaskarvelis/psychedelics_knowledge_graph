# Deployment

The public website is a static Netlify deploy built from a curated `dist/`
directory. The build contains only the UI and static presentation assets.
Generated graph and Methods datasets are served from the public Cloudflare R2
release; the private API database is served to Render from a separate private
R2 bucket.

GitHub Pages is not used for the public site. Keep Netlify as the single
deployment path so the repository does not maintain parallel generated site
outputs.

Use `dist/` for both Netlify deploys and local previews. The old `site/`
output is retired and should not be rebuilt.

## Netlify

Use the settings in `netlify.toml`:

- Build command: `bash scripts/build_site.sh`
- Publish directory: `dist`

The public file list lives in `scripts/public_site_files.txt`. Add files there
only for website code and static presentation assets. Generated data belongs in
the versioned R2 release, not in the Netlify bundle.

The build does not copy generated data. Full extraction-pointer and
canonical-corpus parity is enforced during guarded promotion, where the
intentionally untracked working datasets are available. The R2 publisher then
requires and verifies every graph and Methods release file before it changes the
active public pointer.

## Agent API and MCP

The REST/OpenAPI and MCP service is deployed separately from the static Netlify
site. GitHub contains application code and curated pipeline inputs; generated
public graph and Methods JSON is published to a public Cloudflare R2 bucket,
while the API's unpublished query database is kept in a separate private R2
bucket. No Parquet or database downloads are published. See
[R2 deployment](r2_deployment.md) for the Cloudflare, Render, DNS,
first-publish, and recurring-update checklist.

## Custom Domain

After the Netlify site exists, add both domains in Netlify:

- `psychedelicskg.com`
- `www.psychedelicskg.com`

If DNS stays at GoDaddy, use the DNS records Netlify shows for the site. For a
standard Netlify setup this is typically:

```text
A      @      75.2.60.5
CNAME  www    <netlify-site-name>.netlify.app
```

## Feedback Form

The private visitor feedback form is defined in `feedback/index.html` and
submitted through Netlify Forms under the name `site-feedback`. Keep form
detection enabled in the Netlify Forms settings. To receive each verified
submission by email, add a form submission notification under **Project
configuration > Notifications** in Netlify.

Test the form on a deploy preview or the production site. A local static server
can verify the page layout, but it does not process Netlify form submissions.

## Generated-data tracking

The `.gitignore` rules keep generated data out of future commits. Website data
is published by the R2 publisher and is not read from the Git checkout by
Netlify.

To remove already-tracked generated data from Git while keeping the files on
disk locally:

```sh
git ls-files -ci --exclude-standard -z data | xargs -0 git rm --cached
```

Then review the staged deletions before committing:

```sh
git status --short
```

Review the staged deletions carefully: curated registries and manual override
files remain source-controlled inputs and should not be removed.
