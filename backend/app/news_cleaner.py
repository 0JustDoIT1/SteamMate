"""Steam 뉴스 본문 정리(순수 함수). 공식 공지는 BBCode, 외부 피드는 HTML이라 둘 다 평문으로 바꾼다.

- 이미지·영상 임베드·자리표시자({STEAM_CLAN_IMAGE} 등)는 지운다(본문을 앱에서 다시 게시하지 않는다).
- 링크는 글자만 남긴다. 목록 항목은 "• ", 제목은 줄로 둔다.
- maxlength로 잘린 본문(닫는 태그 없음, 끝에 "...")도 안전하게 처리한다.
결과는 문단 사이 빈 줄 한 개, 그 밖의 공백은 한 칸으로 정리한다.
"""

import html
import re

# 내용까지 통째로 지우는 태그: 이미지, 영상 미리보기
_DROP_BLOCKS = re.compile(r"\[(img|previewyoutube)[^\]]*\].*?\[/\1\]", re.IGNORECASE | re.DOTALL)
# 자리표시자 이미지 주소, 내용 없이 쓰이는 임베드(닫는 태그가 없거나 잘린 경우)
_PLACEHOLDER = re.compile(r"\{STEAM_[A-Z_]+\}\S*")
_SELF_CLOSING = re.compile(r"\[(img|previewyoutube|dynamiclink)[^\]]*\]", re.IGNORECASE)
_BLOCK_OPEN = re.compile(r"\[(p|h[1-6]|list|olist|table|tr|quote|code)(=[^\]]*)?\]", re.IGNORECASE)
_BLOCK_CLOSE = re.compile(r"\[/(p|h[1-6]|list|olist|table|tr|quote|code)\]", re.IGNORECASE)
# 앞의 줄바꿈까지 먹어 항목 사이에 빈 줄이 생기지 않게. "[*][p]문장[/p][/*]" 형식은 [p]도 함께 먹는다.
_LIST_ITEM = re.compile(r"\s*\[\*\]\s*(?:\[p\])?", re.IGNORECASE)
_LIST_ITEM_END = re.compile(r"\[/\*\]")
_ANY_TAG = re.compile(r"\[/?[a-zA-Z][a-zA-Z0-9]*(?:[= ][^\]]*)?\]")
_UNCLOSED_TAIL = re.compile(r"\[[^\]]*$")  # maxlength로 태그 중간에서 잘린 꼬리

_HTML_DROP = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HTML_BLOCK = re.compile(r"</?(p|div|br|h[1-6]|li|ul|ol|tr|blockquote)[^>]*>", re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")
# 폭 없는 공백·방향 표시 등 보이지 않는 문자(실제 공지에 섞여 있음)
_INVISIBLE = re.compile(r"[\u200b-\u200f\u2060\ufeff]")


_ESCAPED = "\x00"  # BBCode의 "\[" = 글자 그대로의 "[" (예: "\[ GAMEPLAY ]"). 태그로 지우지 않게 잠시 바꿔 둔다.


def clean_news(contents: str) -> str:
    text = contents.replace("\\[", _ESCAPED)
    text = _HTML_DROP.sub("", text)
    text = _DROP_BLOCKS.sub("", text)
    text = _PLACEHOLDER.sub("", text)
    text = _SELF_CLOSING.sub("", text)
    text = _LIST_ITEM.sub("\n• ", text)
    text = _LIST_ITEM_END.sub("", text)
    text = _BLOCK_OPEN.sub("\n\n", text)
    text = _BLOCK_CLOSE.sub("\n\n", text)
    text = _ANY_TAG.sub("", text)
    text = _UNCLOSED_TAIL.sub("", text)
    text = _HTML_BLOCK.sub("\n\n", text)
    text = _HTML_TAG.sub("", text)
    text = html.unescape(text).replace(_ESCAPED, "[")
    text = _INVISIBLE.sub("", text)
    return _normalize(text)


def _normalize(text: str) -> str:
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        lines = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in block.split("\n")]
        lines = [line for line in lines if line and line != "•"]
        if lines:
            paragraphs.append("\n".join(lines))
    return "\n\n".join(paragraphs)


def excerpt(text: str, limit: int = 200) -> str:
    """앞부분 limit자. 단어 중간에서 자르지 않고 줄임표를 붙인다. 줄바꿈은 공백으로."""
    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) <= limit:
        return flat
    cut = flat[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" .,;:·•") + "…"


# [url=주소]글자[/url] — 주소에 따옴표가 붙는 경우도 있다(PUBG: [url="https://pubg.com/news/11306"])
_URL_BLOCK = re.compile(r"""\[url=["']?(https?://[^"'\]\s]+)["']?\](.*?)\[/url\]""", re.IGNORECASE | re.DOTALL)


def link_only_target(contents: str) -> str | None:
    """본문이 외부 링크 하나("전문은 여기서")뿐인 공지면 그 주소, 아니면 None.

    예: PUBG 공지는 이미지 + "Read the full announcement here!" 링크만 있어 발췌가 매번 같은 문장이 된다.
    """
    links = _URL_BLOCK.findall(contents)
    if not links or clean_news(_URL_BLOCK.sub("", contents)):
        return None
    return links[0][0]
