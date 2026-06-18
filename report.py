import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

_env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
    autoescape=select_autoescape(["html"]),
)


def render_html(stats, player):
    return _env.get_template("report.html").render(stats=stats, player=player)


def render_pdf(stats, player):
    try:
        from weasyprint import HTML
    except Exception:
        return None
    html = render_html(stats, player)
    try:
        return HTML(string=html).write_pdf()
    except Exception:
        return None
