# Deployment

The public website is a static Netlify deploy built from a curated `dist/`
directory. The build copies only the UI and the JSON payloads required by the
browser app.

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
only when the browser app needs to fetch or serve them publicly.

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

## Data Tracking Cleanup

The `.gitignore` rules keep generated data out of future commits while allowing
the public JSON payloads needed by the static site.

To remove already-tracked generated data from Git while keeping the files on
disk locally:

```sh
git ls-files -ci --exclude-standard -z data | xargs -0 git rm --cached
```

Then review the staged deletions before committing:

```sh
git status --short
```

If a public payload is missing from Git status after cleanup, check
`scripts/public_site_files.txt` and the `.gitignore` exceptions.
