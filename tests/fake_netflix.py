"""A tiny stand-in for the Netflix pages the scraper touches (stdlib only).

Mirrors the markup seen on the real site: /ProfilesGate redirects to /browse, where each profile is a
<button data-uia="profile-selector+tile-ID"> (locked ones carry a "+lock" marker); each profile's
activity lives at /settings/viewed/ID, with a "Show More" button and per-row "Hide" controls.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PROFILES = {"AAA": "Ben", "BBB": "Kids"}
LOCKED = {"BBB"}
TOTALS = {"AAA": 45, "BBB": 3}
PAGE = 20
BROKEN_GATE = False  # when True the profile picker uses markup the scraper does not recognise
DELETE_HITS = []  # paths of any "Hide from viewing history" clicks (must stay empty)


def rows(name, start, stop):
    out = []
    for i in range(start, stop):
        title = f'{name} Show: Season 1: "Episode {i}"' if i == 0 else f"{name} title {i}"
        out.append(
            f'<li class="retableRow" data-uia="activity-row"><div class="col date nowrap">26-{(i % 9) + 1}-{(i % 28) + 1:02d}</div>'
            f'<div class="col title"><a href="/title/{1000 + i}">{title}</a></div>'
            f'<div class="col report"><a class="reportLink" href="/reportproblem/{1000 + i}">Report a problem</a></div>'
            f'<div class="col delete"><a class="deleteBtn" data-uia="delete-activity-button" href="#" '
            f"onclick=\"fetch('/__delete/{1000 + i}');return false\">&#8856;</a></div></li>"
        )
    return "".join(out)


def gate_html():
    tiles = "".join(
        f'<button data-uia="profile-selector+tile-{pid}" tabindex="0" type="button"><div>'
        + (f'<span data-uia="profile-selector+tile-{pid}+lock"><span role="img"></span></span>' if pid in LOCKED else "")
        + f"</div><span><span>{name}</span></span></button>"
        for pid, name in PROFILES.items()
    )
    return (
        '<html><head><title>Netflix</title></head><body><div data-uia="profile-gate-screen">'
        f'<h1>Who\'s watching?</h1><div data-uia="profile-selector">{tiles}</div></div></body></html>'
    )


ACTIVITY = """<!doctype html><html><head><title>Viewing Activity - Account - Netflix</title></head><body>
<h1 data-uia="viewing-activity-header">Activity for {name}</h1>
<ul class="structural retable stdHeight">{rows}</ul>
{button}
<script>
let page = 1;
const btn = document.getElementById('more');
if (btn) btn.addEventListener('click', async () => {{
  const r = await fetch('/settings/viewed/{pid}/more?page=' + page);
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

    def _send(self, body, ctype="text/html", status=200):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, where):
        self.send_response(302)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        authed = self._cookies().get("NetflixId") == "valid"
        if u.path == "/login":
            return self._send("<html><body>Sign in</body></html>")
        if u.path.startswith("/__delete/"):
            DELETE_HITS.append(u.path)
            return self._send("deleted")
        if not authed:
            return self._redirect("/login")
        if u.path == "/ProfilesGate":
            return self._redirect("/browse")
        if u.path == "/browse":
            if BROKEN_GATE:
                return self._send('<html><head><title>Who is watching</title></head><body><a href="/browse?profile=1">Ben</a></body></html>')
            return self._send(gate_html())
        parts = u.path.strip("/").split("/")
        if parts[:2] == ["settings", "viewed"] and len(parts) >= 3 and parts[2] in PROFILES:
            pid, total = parts[2], TOTALS[parts[2]]
            name = PROFILES[pid]
            if len(parts) == 4 and parts[3] == "more":
                n = int(q["page"][0])
                lo, hi = PAGE * n, min(PAGE * (n + 1), total)
                return self._send(json.dumps({"html": rows(name, lo, hi), "more": hi < total}), "application/json")
            button = '<button id="more" class="btn btn-blue btn-small" type="button">Show More</button>' if total > PAGE else ""
            return self._send(ACTIVITY.format(pid=pid, name=name, rows=rows(name, 0, min(PAGE, total)), button=button))
        self._send("not found", status=404)


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
