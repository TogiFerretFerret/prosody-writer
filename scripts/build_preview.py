"""Embed local assets so HTML previews don't require a /static origin route."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent
static = root / "prosody_writer/static"
template = static / "template.html"
html = template.read_text()
html = html.replace('<link rel="stylesheet" href="/static/style.css">',
                    '<style>\n' + (static / 'style.css').read_text() + '\n</style>')
html = html.replace('<script src="/static/editor.js"></script>',
                    '<script>\n' + (static / 'editor.js').read_text() + '\n</script>')
(static / "index.html").write_text(html)
(root / "index.html").write_text(html)
