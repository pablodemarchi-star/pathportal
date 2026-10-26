"""Small allowlist for the Logistics instructions editor."""
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit


class InstructionsParser(HTMLParser):
    tags = {"p", "div", "br", "ul", "ol", "li", "strong", "b", "em", "i", "u", "a", "font", "span"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.stack = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.tags:
            return
        attrs = dict(attrs)
        safe = ""
        if tag == "a":
            href = attrs.get("href", "").strip()
            try:
                scheme = urlsplit(href).scheme.lower()
            except ValueError:
                scheme = ""
            if scheme in {"https", "http", "mailto"}:
                safe = f' href="{escape(href, quote=True)}" target="_blank" rel="noopener noreferrer"'
        if tag == "font" and attrs.get("size") in {"1", "2", "3", "4", "5", "6", "7"}:
            safe = f' size="{attrs["size"]}"'
        self.output.append(f"<{tag}{safe}>")
        if tag != "br":
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag not in self.stack:
            return
        while self.stack:
            current = self.stack.pop()
            self.output.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, value):
        self.output.append(escape(value))
        self.text.append(value)


def sanitize_instructions(value):
    parser = InstructionsParser()
    parser.feed(value or "")
    parser.close()
    if not "".join(parser.text).replace("\xa0", " ").strip():
        return ""
    return "".join(parser.output) + "".join(f"</{tag}>" for tag in reversed(parser.stack))
