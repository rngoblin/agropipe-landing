"""Сборка статического превью landing/ для GitHub Pages (docs/).

Только для просмотра дизайна. GitHub Pages не запускает Python, поэтому
POST /api/lead в этой сборке не работает — форма покажет общую ошибку
сервера с телефоном как запасным каналом (см. content.yaml, error_generic),
это штатное поведение form.js при недоступном бэкенде, не баг.

Использует те же landing/templates/*.j2 и landing/content.yaml, что и
настоящий сервер (api/lead.py) — правки текста и вёрстки подхватятся сюда
без изменений в этом скрипте.

    .venv/bin/python3 scripts/build_static_preview.py
"""
import shutil
from pathlib import Path

import jinja2
import yaml

ROOT = Path(__file__).resolve().parent.parent
LANDING = ROOT / "landing"
DOCS = ROOT / "docs"


def rewrite_paths(html: str) -> str:
    return (
        html.replace('href="/static/', 'href="static/')
        .replace('src="/static/', 'src="static/')
        .replace('srcset="/static/', 'srcset="static/')
        .replace('href="/privacy"', 'href="privacy.html"')
        .replace('href="/"', 'href="index.html"')
    )


def main() -> None:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(LANDING / "templates")))
    content = yaml.safe_load((LANDING / "content.yaml").read_text(encoding="utf-8"))

    if DOCS.exists():
        shutil.rmtree(DOCS)
    DOCS.mkdir(parents=True)

    index_html = env.get_template("index.html.j2").render(
        content=content, form_state=None, form_rendered_at="0", preview_mode=True
    )
    (DOCS / "index.html").write_text(rewrite_paths(index_html), encoding="utf-8")

    privacy_html = env.get_template("privacy.html.j2").render(content=content, preview_mode=True)
    (DOCS / "privacy.html").write_text(rewrite_paths(privacy_html), encoding="utf-8")

    shutil.copytree(LANDING / "static", DOCS / "static")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Готово: {DOCS}")


if __name__ == "__main__":
    main()
