"""Local design comparison. Run while the normal preview is on port 8011."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TAB_VARIANTS = {
    "inset-divider": """
      .workspace-tab + .workspace-tab::before {
        content: "";
        position: absolute;
        left: 0;
        top: 9px;
        width: 1px;
        height: 16px;
        background: rgba(188, 200, 201, 0.22);
      }
    """,
    "frame-seam": """
      .workspace-tabs .workspace-tab + .workspace-tab {
        box-shadow: inset 1px 0 rgba(188, 200, 201, 0.16);
      }
    """,
    "recessed-gutter": """
      .workspace-tabs {
        gap: 2px;
        background: #07090a;
      }
    """,
    "faded-divider": """
      .workspace-tab + .workspace-tab::before {
        content: "";
        position: absolute;
        left: 0;
        top: 6px;
        width: 1px;
        height: 22px;
        background: linear-gradient(
          180deg,
          transparent,
          rgba(188, 200, 201, 0.2) 32%,
          rgba(188, 200, 201, 0.2) 68%,
          transparent
        );
      }
    """,
}


class Preview(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        params = dict(parse_qsl(parsed.query))
        if parsed.path == "/" and params.get("data-source") != "local":
            query = parse_qsl(parsed.query, keep_blank_values=True)
            query.append(("data-source", "local"))
            location = urlunsplit(("", "", parsed.path, urlencode(query), parsed.fragment))
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            with urlopen('http://127.0.0.1:8011' + self.path) as r:
                data, content_type = r.read(), r.headers.get('Content-Type', 'application/octet-stream')
        except Exception as e:
            self.send_error(502, str(e)); return
        variant_css = TAB_VARIANTS.get(params.get("tab-variant", ""))
        if variant_css and "text/html" in content_type:
            markup = data.decode("utf-8")
            markup = markup.replace(
                "</head>",
                f'<style data-tab-variant="{params["tab-variant"]}">{variant_css}</style></head>',
            )
            data = markup.encode("utf-8")
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers(); self.wfile.write(data)
    def log_message(self, *args): pass
if __name__ == '__main__':
    print('Navigation comparison: http://127.0.0.1:8034', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8034), Preview).serve_forever()
