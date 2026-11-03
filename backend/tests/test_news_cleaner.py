from app.news_cleaner import clean_news, excerpt, link_only_target

# 2026-11-03 실제 공식 공지 구조를 따른 가공 예시
BBCODE = """[img]{STEAM_CLAN_IMAGE}/3949769/98759babb408.png[/img]

[h2]Patch Notes[/h2]
[p]Greetings [b]Terrarians[/b]! Read the [url=https://example.com/blog]full blog[/url] &amp; enjoy.[/p]
[list]
[*][i]Fixed[/i] a crash
[*]Added crossplay
[/list]
[previewyoutube=abc123;full][/previewyoutube]
[p][dynamiclink href="https://store.steampowered.com/app/105600"][/dynamiclink][/p]
[p]Thanks![/p]"""


def test_bbcode_to_plain_text():
    assert clean_news(BBCODE) == (
        "Patch Notes\n\n"
        "Greetings Terrarians! Read the full blog & enjoy.\n\n"
        "• Fixed a crash\n"
        "• Added crossplay\n\n"
        "Thanks!"
    )


def test_html_feed_to_plain_text():
    raw = '<img src="https://x/a.jpg"/><p>Hello&nbsp;<b>world</b></p><script>alert(1)</script><ul><li>one</li></ul>'
    assert clean_news(raw) == "Hello world\n\none"


def test_truncated_by_maxlength_is_safe():
    # maxlength로 잘리면 닫는 태그가 없고 태그 중간에서 끊길 수 있다
    raw = "[p]First part[/p][img]{STEAM_CLAN_IMAGE}/1/abc.png[/img][p]Second [url=https://exa..."
    assert clean_news(raw) == "First part\n\nSecond"


def test_unclosed_image_and_placeholder_removed():
    assert clean_news("[img]{STEAM_CLAN_LOC_IMAGE}/1/x.png Text after") == "Text after"


def test_empty_and_image_only():
    assert clean_news("") == ""
    assert clean_news("[img]{STEAM_CLAN_IMAGE}/1/x.png[/img]") == ""


def test_excerpt_cuts_at_word_boundary():
    text = "word " * 100
    out = excerpt(text, 23)
    assert out == "word word word word…" and len(out) <= 24


def test_excerpt_short_text_unchanged_and_flattened():
    assert excerpt("Line one\n\nLine two", 200) == "Line one Line two"


def test_escaped_bracket_and_closing_list_item():
    # CS2 패치노트 형식: "\[ 섹션 ]" 은 글자 그대로, 목록 항목은 [/*]로 닫힌다
    raw = r"[p]\[ GAMEPLAY ][/p][list][*][p]Added toggle.[/p][/*][*][p]Fixed bug.[/p][/*][/list]"
    assert clean_news(raw) == "[ GAMEPLAY ]\n\n• Added toggle.\n\n• Fixed bug."


def test_invisible_characters_removed():
    assert clean_news("[p]Hello!\u200b \ufeffSo[/p]") == "Hello! So"


def test_link_only_announcement():
    # 2026-11-03 PUBG 공지 실제 구조
    raw = (
        '[p][img src="{STEAM_CLAN_IMAGE}/27971017/19fde67d.jpg"][/img][/p]'
        '[h2][url="https://pubg.com/news/11306"]Read the full announcement here![/url][/h2]'
    )
    assert link_only_target(raw) == "https://pubg.com/news/11306"


def test_link_inside_real_text_is_not_link_only():
    assert link_only_target("[p]Patch is live. [url=https://x.example/notes]Notes[/url][/p]") is None
    assert link_only_target("[p]No links here[/p]") is None
