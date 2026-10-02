"""Clean article HTML and convert it to Markdown with source citations."""
from html import escape
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter


class ArticleConverter(MarkdownConverter):
    def convert_hN(self, n, el, text, parent_tags):
        heading = super().convert_hN(n, el, text, parent_tags)
        anchor = el.get("id")
        return ('\n\n<a id="' + escape(anchor, quote=True) + '"></a>' if anchor else '') + heading

    def convert_a(self, el, text, parent_tags):
        link = super().convert_a(el, text, parent_tags)
        anchor = el.get("id") or el.get("name")
        return ('<a id="' + escape(anchor, quote=True) + '"></a>' if anchor else '') + link

    def convert_pre(self, el, text, parent_tags):
        # Keep whitespace exactly, including blank lines and nested backticks.
        content = el.get_text().replace("\r\n", "\n").replace("\r", "\n")
        longest = max((len(m.group()) for m in re.finditer(r"\x60+", content)), default=0)
        fence = chr(96) * max(3, longest + 1)
        code = el.find("code")
        classes = (code.get("class", []) if code else []) + el.get("class", [])
        language = next((c.removeprefix("language-") for c in classes if c.startswith("language-")), "")
        language = re.sub(r"[^\w+-]", "", language)
        return "\n\n" + fence + language + "\n" + content + ("" if content.endswith("\n") else "\n") + fence + "\n\n"


def article_markdown(article: dict) -> str:
    title = " ".join(article["title"].split())
    url = article["html_url"]
    if not title or urlsplit(url).scheme not in ("http", "https") or "\n" in url or "\r" in url:
        raise ValueError("Article has an invalid title or source URL")
    soup = BeautifulSoup(article.get("body") or "", "html.parser")
    for element in soup.select("script, style, nav, footer, form, noscript, .advertisement, .ads, [role='navigation']"):
        element.decompose()
    # Binary image payloads are not searchable text. Keep their captions and
    # direct readers to the original article instead of embedding base64 in Markdown.
    for element in soup.find_all("img"):
        if str(element.get("src", "")).strip().lower().startswith("data:image/"):
            caption = element.get("alt") or element.get("title") or "Embedded image"
            note = soup.new_tag("span")
            note.string = f"{caption} (image available in original article)"
            element.replace_with(note)
    # Embedded videos are useful content; preserve their links instead of losing them.
    for element in soup.find_all("iframe"):
        src = element.get("src")
        if src:
            link = soup.new_tag("a", href=src)
            link.string = element.get("title") or "Embedded video"
            element.replace_with(link)
        else:
            element.decompose()
    if not soup.get_text(strip=True) and not soup.find("img"):
        raise ValueError(f"Article {article['id']} has an empty body")
    body = ArticleConverter(heading_style="ATX", bullets="-", strip_pre=None).convert(str(soup)).strip()
    if not body:
        raise ValueError(f"Article {article['id']} converted to empty Markdown")
    # Leave relative links unchanged; Article URL gives their original base.
    return f"# {title}\n\nArticle URL: {url}\n\n{body}\n"
