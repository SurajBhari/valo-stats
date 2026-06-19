import contextlib
import io
import logging
import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

import assets
import insights

# WeasyPrint complains loudly to its logger/stderr when its native (GTK/Pango)
# libraries are missing — expected on Windows dev machines, where we fall back
# to HTML. Silence that logger so the console isn't polluted; the real PDF path
# still runs on the Render Docker image, which has the libraries.
logging.getLogger("weasyprint").setLevel(logging.CRITICAL)
logging.getLogger("fontTools").setLevel(logging.CRITICAL)

_env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
    autoescape=select_autoescape(["html"]),
)


def render_html(stats, player):
    tips = insights.generate(stats)
    agent_icons = {a["name"]: assets.agent_icon(a["name"]) for a in stats.get("per_agent", [])}
    map_icons = {m["name"]: assets.map_icon(m["name"]) for m in stats.get("per_map", [])}
    player = dict(player)
    player["card_img"] = assets.card_image(player.get("card"))
    player["rank_img"] = assets.rank_icon(player.get("rank_icon_url"))
    player["border_img"] = assets.level_border(player.get("level"))
    return _env.get_template("report.html").render(
        stats=stats, player=player, tips=tips,
        agent_icons=agent_icons, map_icons=map_icons)


def render_pdf(stats, player):
    """Render the report to PDF bytes, or return None if WeasyPrint's native
    libraries are unavailable (caller then serves the HTML fallback)."""
    try:
        # WeasyPrint print()s a multi-line native-library banner to stdout when
        # GTK/Pango are missing; capture both streams during the import.
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            from weasyprint import HTML
    except Exception:
        return None
    html = render_html(stats, player)
    try:
        return HTML(string=html).write_pdf()
    except Exception:
        return None
