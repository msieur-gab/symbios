"""article: a web address → a readable markdown file, made on the board.

The board fetches the page, keeps the article and drops the rest, and writes markdown under the
same front matter brainboard archives with (title, url, author, siteName, excerpt, cover,
keywords, published, savedAt), so both libraries read alike. Python only: readability and
html2text come from Debian (python3-readability, python3-html2text), the rest is the standard
library and lxml, which readability brings.

    python3 article.py URL          # the markdown, on the screen
    python3 article.py URL FOLDER   # saved in FOLDER as <slug>-<date>.md
"""
import datetime
import email.utils
import ipaddress
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse

AGENT = "Mozilla/5.0 (X11; Linux aarch64; rv:128.0) Gecko/20100101 Firefox/128.0"
LIMIT = 5_000_000  # a page larger than this isn't an article


def fetch(url):
    """The page's HTML and the address it really lives at (after redirects)."""
    public(url)
    ask = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urllib.request.urlopen(ask, timeout=20) as r:
            public(r.geturl())  # a redirect doesn't lead the board to read its own network either
            raw = r.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise ValueError("that page is too large to be an article")
            return raw.decode(r.headers.get_content_charset() or "utf-8", errors="replace"), r.geturl()
    except urllib.error.HTTPError as e:
        if e.code in (401, 402, 403, 429):
            raise ValueError("that site turned the board away (a paywall, or a check that it is a person)") from None
        raise ValueError("that site answered with error %d" % e.code) from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError("the board couldn't reach that site") from None


def public(url):
    """Only pages of the public web: the board doesn't fetch from itself or the network it sits on."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("an article address starts with http:// or https://")
    try:
        found = {i[4][0] for i in socket.getaddrinfo(u.hostname, None)}
    except OSError:
        raise ValueError("the board couldn't find that site") from None
    if not all(ipaddress.ip_address(a.split("%")[0]).is_global for a in found):
        raise ValueError("that address is not on the public web")


def day(raw):
    """A date as a site writes it → YYYY-MM-DD, or None."""
    text = (raw or "").strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    try:
        return email.utils.parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError):
        return None


def writer(raw):
    """An author as a site writes it → the name alone, or None ("By …", "Unknown", a profile link)."""
    text = re.sub(r"^(by|written by|author)\s*[:\-–]?\s*", "", re.sub(r"\s+", " ", raw or "").strip(), flags=re.I).strip()
    return None if not text or text.lower() in ("by", "written by", "author", "unknown", "unknown author") or text.startswith("http") else text


def card(tree, url):
    """What the page says about itself in its <meta> tags: the same reading brainboard does."""
    def meta(*names):
        for name in names:
            for m in tree.xpath("//meta[@property=$n or @name=$n or @itemprop=$n]/@content", n=name):
                if m.strip():
                    return m.strip()
        return ""
    data = linked(tree)
    cover = meta("og:image", "twitter:image", "og:image:url")
    keywords = []
    for t in tree.xpath('//meta[@property="article:tag"]/@content') or meta("keywords").split(","):
        if t.strip() and t.strip() not in keywords:
            keywords.append(t.strip())
    return {
        "title": meta("og:title", "twitter:title"),
        "author": writer(meta("author", "article:author", "parsely-author", "citation_author", "dc.creator")) or writer(data.get("author")),
        "siteName": meta("og:site_name") or urlparse(url).hostname.removeprefix("www."),
        "excerpt": re.sub(r"\s+", " ", meta("og:description", "twitter:description", "description")),
        "cover": urljoin(url, cover) if cover else "",
        "keywords": keywords[:6],
        "published": day(meta("article:published_time", "og:published_time", "datePublished", "parsely-pub-date", "date", "dc.date",
                              "citation_publication_date")) or day(data.get("published")),
    }


def linked(tree):
    """The author and date from the page's structured data (schema.org JSON-LD), which some sites
    fill in instead of <meta> tags: the first article it describes, wherever it is nested."""
    found, named, nodes = {}, {}, []
    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            nodes.append(node)
            if isinstance(node.get("@id"), str) and isinstance(node.get("name"), str):
                named[node["@id"]] = node["name"]  # a person described once, pointed at from the article
            walk(node.get("@graph"))
    for script in tree.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            walk(json.loads(script))
        except ValueError:
            pass
    for node in nodes:
        kinds = node.get("@type") if isinstance(node.get("@type"), list) else [node.get("@type")]
        if any(str(k).endswith(("Article", "Posting", "Report", "WebPage")) for k in kinds):
            who = node.get("author")
            who = who[0] if isinstance(who, list) and who else who
            who = who.get("name") or named.get(who.get("@id")) if isinstance(who, dict) else who
            if isinstance(who, str):
                found.setdefault("author", who)
            if isinstance(node.get("datePublished"), str):
                found.setdefault("published", node["datePublished"])
    return found


# ---- site furniture, ported from brainboard's cleanArticle.js (the reasons are told there) ----
# A block that stands alone and is a label, not a sentence ("Advertisement", "Listen 1.0x"),
# goes; a caption stays, because it sits against its image.
MEDIA = re.compile(r"^(!\[[^\]]*\]\([^)]*\)\s*$|!\[\[|<\s*(video|img|picture|figure|iframe|audio|source|embed|object)\b)", re.I)
KEEP = [r"^#{1,6}\s", r"^[-*+>|]", r"^\d+[.)]\s", r"\]\(", r"^!\[", r"^(```|~~~)", r"[.!?:…]$", r"[\"“”«»]",
        r"[.!?…][)\"”'’]$", r"^\\?[-–—]\s*\S", r"(?i)^By\b", r"\s/\s\w{3,9}\.?\s\d{1,2},\s\d{4}$"]


def furniture(block):
    t = re.sub(r"\s+", " ", block.strip())
    return bool(t) and len(t) <= 60 and len(t.split(" ")) <= 8 and not any(re.search(k, t) for k in KEEP)


def tidy(md):
    blocks, out, fenced = re.split(r"\n\s*\n", md), [], False
    for i, b in enumerate(blocks):
        odd = len(re.findall(r"^(```|~~~)", b, flags=re.M)) % 2
        if fenced or odd:
            fenced = fenced != bool(odd)
            out.append(b)
            continue
        beside = (i > 0 and MEDIA.match(blocks[i - 1].strip())) or (i < len(blocks) - 1 and MEDIA.match(blocks[i + 1].strip()))
        if not furniture(b) or beside:
            out.append(b)
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(out)).strip() + "\n"


def read(url):
    """A web address → the article: its card and its markdown."""
    import html2text
    import lxml.html
    from readability import Document
    html, url = fetch(url)
    article = card(lxml.html.fromstring(html), url)
    doc = Document(html, url=url)
    to_md = html2text.HTML2Text(baseurl=url)
    to_md.body_width = 0        # no hard line breaks inside a paragraph
    to_md.unicode_snob = True   # keep the page's own quotes and dashes
    markdown = tidy(to_md.handle(doc.summary(html_partial=True)))
    if len(markdown.split()) < 60:
        raise ValueError("no readable article was found on that page (it may sit behind a paywall)")
    title = article["title"] or doc.short_title() or "Untitled"
    title = re.sub(r"\s+[|\-–—·:]\s+%s$" % re.escape(article["siteName"]), "", title) or title  # "… | The Site"
    return {**article, "title": title, "url": url, "markdown": markdown}


def text(a, now=None):
    """The article as the file it becomes: brainboard's front matter, then the markdown."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    q = lambda s: json.dumps(s, ensure_ascii=False)
    lines = ["---", "title: " + q(a["title"]), "url: " + a["url"],
             a["author"] and "author: " + q(a["author"]),
             a["siteName"] and "siteName: " + a["siteName"],
             a["excerpt"] and "excerpt: " + q(a["excerpt"]),
             a["cover"] and "cover: " + q(a["cover"]),
             a["keywords"] and "keywords: " + q(a["keywords"]),
             a["published"] and "published: " + a["published"],
             "savedAt: " + now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)]
    return "\n".join([l for l in lines if l] + ["---", "", ""]) + a["markdown"]


def shelf(folder):
    """The articles kept in a folder, newest first: each one's front matter and its file name."""
    cards = []
    for entry in os.scandir(folder) if os.path.isdir(folder) else []:
        if not entry.name.endswith(".md"):
            continue
        with open(entry.path, encoding="utf-8", errors="replace") as f:
            head = re.match(r"---\n(.*?)\n---\n", f.read(8000), re.S)
        card = {"file": entry.name}
        for line in head.group(1).split("\n") if head else []:
            key, _, value = line.partition(": ")
            try:
                card[key] = json.loads(value) if value[:1] in ('"', "[") else value
            except ValueError:
                card[key] = value
        cards.append(card)
    return sorted(cards, key=lambda c: str(c.get("savedAt", "")), reverse=True)


def name(a, now=None):
    slug = re.sub(r"[^a-z0-9]+", "-", a["title"].lower()).strip("-")[:60].strip("-") or "article"
    return "%s-%s.md" % (slug, (now or datetime.date.today()).isoformat())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    a = read(sys.argv[1])
    if len(sys.argv) > 2:
        os.makedirs(sys.argv[2], exist_ok=True)
        path = os.path.join(sys.argv[2], name(a))
        open(path, "w", encoding="utf-8").write(text(a))
        print(path)
    else:
        print(text(a))
