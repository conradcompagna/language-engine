"""HTML5-parser allowlist and a resource policy for inert reading snapshots."""
from html import escape
import re

import nh3

RESOURCE_POLICY = (
    "default-src 'none'; script-src 'none'; connect-src 'none'; "
    "img-src data:; style-src 'unsafe-inline'; font-src data:; "
    "base-uri 'none'; form-action 'none'; frame-src 'none'; object-src 'none'"
)
DOCUMENT_POLICY = RESOURCE_POLICY + "; sandbox; frame-ancestors 'self'"
TAGS = {
    "a", "abbr", "article", "aside", "b", "bdi", "bdo", "blockquote", "br",
    "caption", "cite", "code", "col", "colgroup", "dd", "del", "details",
    "div", "dl", "dt", "em", "figcaption", "figure", "footer", "h1", "h2",
    "h3", "h4", "h5", "h6", "header", "hr", "i", "img", "ins", "kbd",
    "li", "main", "mark", "nav", "ol", "p", "pre", "q", "rp", "rt", "ruby",
    "s", "samp", "section", "small", "span", "strong", "style", "sub",
    "summary", "sup", "table", "tbody", "td", "th", "thead", "tfoot", "time",
    "tr", "u", "ul", "var", "wbr",
}
ATTRIBUTES = {
    "*": {"class", "id", "title", "style", "lang", "dir"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan", "scope"},
    "col": {"span"}, "colgroup": {"span"}, "ol": {"start", "reversed"},
    "li": {"value"}, "details": {"open"},
}
RASTER_DATA_URL = re.compile(r"^data:image/(?:png|jpeg|gif|webp|avif);base64,[a-z0-9+/=\s]+$", re.I)


def _attribute(tag, name, value):
    if name == "src":
        return value if tag == "img" and RASTER_DATA_URL.fullmatch(value) else None
    return value


def sanitize_snapshot(html):
    # Styles remain inside an inert frame; CSP blocks their external resources.
    # Links have no href, forms and nested documents are removed, and only
    # self-contained raster image URLs survive attribute filtering.
    cleaned = nh3.clean(
        html, tags=TAGS, attributes=ATTRIBUTES, attribute_filter=_attribute,
        clean_content_tags={"script", "iframe", "object", "embed", "svg", "math", "template"},
        url_schemes={"data"}, url_relative="deny", strip_comments=True,
    )
    return (
        '<!doctype html><html data-docrender-web-snapshot="1"><head>'
        '<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="'
        + escape(RESOURCE_POLICY, quote=True) + '">'
        '<meta name="referrer" content="no-referrer">'
        '<style>html,body{min-height:100%;overflow-x:hidden}*{animation:none!important;'
        'transition:none!important}a,button,input,textarea,select{pointer-events:none!important}</style>'
        '</head><body>' + cleaned + '</body></html>'
    )
