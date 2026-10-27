"""Small allowlist for the Logistics instructions editor."""
from html import escape
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit


def safe_color(value):
    value = value.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}(?:[0-9a-f]{3})?", value):
        return value
    if value in {"red", "blue", "green", "purple", "violet", "black", "white", "inherit"}:
        return value
    match = re.fullmatch(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", value)
    return value if match and all(int(item) <= 255 for item in match.groups()) else ""


def safe_style(value):
    styles = {}
    for declaration in value.split(";"):
        prop, sep, val = declaration.partition(":")
        prop, val = prop.strip().lower(), val.strip().lower()
        if not sep:
            continue
        if prop == "color" and safe_color(val):
            styles[prop] = safe_color(val)
        elif prop == "font-size":
            match = re.fullmatch(r"(\d+(?:\.\d+)?)(px|pt|em|rem|%)", val)
            if val in {"x-small", "small", "medium", "large", "x-large", "xx-large"} or (
                match and 0 < float(match[1]) <= {"px": 96, "pt": 72, "em": 6, "rem": 6, "%": 600}[match[2]]
            ):
                styles[prop] = val
        elif prop == "font-weight" and val in {"normal", "bold", "400", "500", "600", "700", "800", "900"}:
            styles[prop] = val
        elif prop == "font-style" and val in {"normal", "italic"}:
            styles[prop] = val
        elif prop == "text-decoration" and val in {"none", "underline", "line-through"}:
            styles[prop] = val
    return "; ".join(f"{prop}: {val}" for prop, val in styles.items())


class InstructionsParser(HTMLParser):
    tags = {"p", "div", "br", "ul", "ol", "li", "strong", "b", "em", "i", "u", "a", "font", "span"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.stack = []
        self.text = []
        self.blocked = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "iframe", "object", "svg", "math"}:
            self.blocked.append(tag)
        if self.blocked:
            return
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
            safe += f' size="{attrs["size"]}"'
        if tag == "font" and safe_color(attrs.get("color", "")):
            safe += f' color="{escape(safe_color(attrs["color"]), quote=True)}"'
        style = safe_style(attrs.get("style", ""))
        if style:
            safe += f' style="{escape(style, quote=True)}"'
        self.output.append(f"<{tag}{safe}>")
        if tag != "br":
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.blocked:
            if tag == self.blocked[-1]:
                self.blocked.pop()
            return
        if tag not in self.stack:
            return
        while self.stack:
            current = self.stack.pop()
            self.output.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, value):
        if self.blocked:
            return
        self.output.append(escape(value))
        self.text.append(value)


def sanitize_instructions(value):
    parser = InstructionsParser()
    parser.feed(value or "")
    parser.close()
    if not "".join(parser.text).replace("\xa0", " ").strip():
        return ""
    return "".join(parser.output) + "".join(f"</{tag}>" for tag in reversed(parser.stack))
