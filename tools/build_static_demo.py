#!/usr/bin/env python3
"""Build a static, backend-free demo of the dashboard for GitHub Pages.

The real dashboard needs the Python server (it polls ``/api/stats``). GitHub Pages
only serves static files, so this script bakes a fabricated stats snapshot into a
copy of ``dashboard.html`` and injects a tiny ``fetch`` shim that answers the
``/api/stats`` call from that snapshot — no server, no real data, no network.

    python tools/build_static_demo.py            # writes ./site/
    python tools/build_static_demo.py --out dir

The shipped ``portmint_pulse/web/dashboard.html`` is NOT modified; we transform a
copy on the way out.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Make both the package and the sibling tools/ importable regardless of CWD.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gen_demo import _DEMO_LIMITS, generate  # noqa: E402  (path set above)
from portmint_pulse.server import _FAVICON_SVG  # noqa: E402
from portmint_pulse.transcripts import RANGES, TranscriptStore  # noqa: E402


def build_stats() -> dict:
    """Aggregate synthetic sessions into one /api/stats payload PER range, so the
    demo's range selector works without a backend. Returns {range_key: payload}.
    """
    tmp = Path(tempfile.mkdtemp(prefix="pulse-static-"))
    # ~14 months of history so Month/3M/6M/Year all show real data (5Y shows what
    # exists). Hourly "Day" view reads today's generated files.
    generate(tmp, days=420, seed=7)
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(tmp))
    store.refresh()
    out: dict = {}
    # Mirror the server: a single last-30-days API-equivalent value for "money's worth".
    month_value = store.aggregate("month")["period"]["cost"]
    for key in RANGES:
        data = store.aggregate(key)
        data["limits"] = _DEMO_LIMITS
        data["timezone"] = "UTC"
        data["value_30d_usd"] = month_value
        # A stable, obviously-illustrative timestamp (no real local time leaked).
        data["generated_at"] = "demo · synthetic data"
        out[key] = data
    return out


# Injected just inside <body>: a ribbon + a fetch shim that answers /api/stats
# from the baked snapshot. Runs before the dashboard's own script (which is at the
# end of <body>), so the dashboard never reaches the network.
_INJECT_TEMPLATE = """
<style>
  .pulse-demo-ribbon{{position:sticky;top:0;z-index:50;display:flex;gap:10px;
    align-items:center;justify-content:center;flex-wrap:wrap;
    padding:8px 14px;font:600 13px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
    color:#03130d;background:linear-gradient(115deg,#5cf0c4,#34e0b3 45%,#0ea5e9)}}
  .pulse-demo-ribbon a{{color:#03130d;font-weight:800;text-decoration:underline}}
</style>
<div class="pulse-demo-ribbon">
  <span>🛟 Live demo — fabricated data, no backend.</span>
  <a href="https://github.com/colelevy08/portmint-pulse">Install Portmint Pulse to see your own usage →</a>
</div>
<script>
  // DEMO MODE: no server here. Answer the dashboard's /api/stats?range=… call from
  // a baked snapshot per range, so the range selector works exactly like the real app.
  window.__PULSE_DEMO__ = {stats_json};
  (function () {{
    const orig = window.fetch ? window.fetch.bind(window) : null;
    window.fetch = function (url, opts) {{
      const s = String(url);
      if (s.indexOf("/api/stats") !== -1) {{
        const m = s.match(/[?&]range=([^&]+)/);
        const key = m ? decodeURIComponent(m[1]) : "month";
        const data = window.__PULSE_DEMO__[key] || window.__PULSE_DEMO__["month"];
        return Promise.resolve(new Response(JSON.stringify(data), {{
          status: 200, headers: {{ "Content-Type": "application/json" }},
        }}));
      }}
      return orig ? orig(url, opts) : Promise.reject(new Error("fetch unavailable"));
    }};
  }})();
</script>
"""


def build(out_dir: Path) -> None:
    src = Path(_REPO_ROOT) / "portmint_pulse" / "web" / "dashboard.html"
    html = src.read_text(encoding="utf-8")

    inject = _INJECT_TEMPLATE.format(stats_json=json.dumps(build_stats()))
    # Insert right after the opening <body> so it runs before the dashboard script.
    html = html.replace("<body>", "<body>\n" + inject, 1)
    # Use a relative favicon path (absolute "/favicon.svg" breaks on a project Pages URL).
    html = html.replace('href="/favicon.svg"', 'href="favicon.svg"')

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / "favicon.svg").write_text(_FAVICON_SVG, encoding="utf-8")
    # Tell Pages not to run Jekyll over our files.
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built static demo into {out_dir}/ ({(out_dir / 'index.html').stat().st_size // 1024} KB index.html)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the static GitHub Pages demo.")
    ap.add_argument("--out", default="site", help="Output directory (default: site).")
    args = ap.parse_args()
    # Stamp the build date into the page title-time via the snapshot above; nothing
    # here depends on the wall clock except the fabricated generated_at label.
    _ = datetime.now(timezone.utc)
    build(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
