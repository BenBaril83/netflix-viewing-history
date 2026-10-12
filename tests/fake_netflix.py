"""A tiny stand-in for the Netflix pages the scraper touches (stdlib only)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PROFILES = {"AAA": "Ben", "BBB": "Kids"}
PAGE = 20
BROKEN_GATE = False  # when True the profile picker uses markup the scraper does not recognise


def rows(profile, start, stop):
    return "".join(
        f'<li class="retableRow"><div class="col date nfa">10/{(i % 28) + 1}/26</div>'
        f'<div class="col title"><a href="/title/{1000 + i}">{profile} title {i}</a></div></li>'
        for i in range(start, stop)
    )


TOTALS = {"AAA": 45, "BBB": 3}

ACTIVITY = """<!doctype html><html><body><ul class="retable">{rows}</ul>
{button}
<script>
let page = 1;
const btn = document.getElementById('more');
if (btn) btn.addEventListener('click', async () => {{
  const r = await fetch('/viewingactivity/more?page=' + page);
  const j = await r.json();
  document.querySelector('ul.retable').insertAdjacentHTML('beforeend', j.html);
  page++;
  if (!j.more) btn.remove();
}});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _cookies(self):
        return dict(c.strip().split("=", 1) for c in self.headers.get("Cookie", "").split(";") if "=" in c)

    def _send(self, body, ctype="text/html", status=200, headers=()):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u, cookies = urlparse(self.path), self._cookies()
        q = parse_qs(u.query)
        authed = cookies.get("NetflixId") == "valid"
        if u.path == "/login":
            return self._send("<html><body>Sign in</body></html>")
        if u.path == "/ProfilesGate" and not authed:
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        if u.path == "/ProfilesGate" and BROKEN_GATE:
            return self._send('<html><head><title>Who is watching</title></head><body><a href="/browse?profile=1">Ben</a></body></html>')
        if u.path == "/ProfilesGate":
            links = "".join(
                f'<a href="/SwitchProfile?tkn={t}"><span class="profile-name">{n}</span></a>'
                for t, n in PROFILES.items()
            ) if authed else "<p>Sign in</p>"
            return self._send(f"<html><body>{links}</body></html>")
        if u.path == "/SwitchProfile":
            self.send_response(302)
            self.send_header("Set-Cookie", f"profile={q['tkn'][0]}; Path=/")
            self.send_header("Set-Cookie", "NetflixId=valid; Path=/")  # simulate cookie rotation
            self.send_header("Location", "/browse")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        if u.path == "/browse":
            return self._send("<html><body>browse</body></html>")
        if not authed:
            return self._send("<html><body>login</body></html>", status=403)
        profile = cookies.get("profile", "AAA")
        total = TOTALS[profile]
        name = PROFILES[profile]
        if u.path == "/viewingactivity":
            button = '<button id="more" class="btn btn-blue btn-small">Show More</button>' if total > PAGE else ""
            return self._send(ACTIVITY.format(rows=rows(name, 0, min(PAGE, total)), button=button))
        if u.path == "/viewingactivity/more":
            n = int(q["page"][0])
            lo, hi = PAGE * n, min(PAGE * (n + 1), total)
            return self._send(json.dumps({"html": rows(name, lo, hi), "more": hi < total}), "application/json")
        self._send("not found", status=404)


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
