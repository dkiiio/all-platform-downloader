import pytest
from gallery_dl import extractor

from xdl.urls import extract_urls, is_x, normalize


def test_extract_stops_at_chinese_punctuation():
    text = "看这个：https://x.com/a/status/1，还有“https://x.com/b/status/2”。（https://x.com/c）【https://x.com/d】"
    assert extract_urls(text) == [
        "https://x.com/a/status/1",
        "https://x.com/b/status/2",
        "https://x.com/c",
        "https://x.com/d",
    ]


@pytest.mark.parametrize("tail", [".", ",", ")", "!", "?", ";", ":", "'", '"', ").", "。", "！"])
def test_extract_strips_trailing_punctuation(tail):
    assert extract_urls("see https://x.com/a/status/1" + tail) == ["https://x.com/a/status/1"]


def test_extract_dedupes_and_keeps_order():
    text = "https://b.com/1 https://a.com/2\nhttps://b.com/1 and https://a.com/2."
    assert extract_urls(text) == ["https://b.com/1", "https://a.com/2"]


def test_extract_multiple_in_prose():
    text = "First <https://youtu.be/xyz> then (http://example.org/p?q=1&r=2) done"
    assert extract_urls(text) == ["https://youtu.be/xyz", "http://example.org/p?q=1&r=2"]


def test_extract_stops_at_glued_chinese_text():
    text = "看这个https://x.com/someone/media好 和 https://www.bilibili.com/video/BV1GJ411x7h7看看"
    assert extract_urls(text) == ["https://x.com/someone/media", "https://www.bilibili.com/video/BV1GJ411x7h7"]
    # 浏览器复制出来的中文是 %xx 编码,不受影响
    assert extract_urls("https://x.com/search?q=%E4%B8%AD") == ["https://x.com/search?q=%E4%B8%AD"]


def test_extract_nothing():
    assert extract_urls("没有链接 www.x.com") == []


STATUS = "https://x.com/jack/status/20"


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://twitter.com/jack/status/20", STATUS),
        ("https://www.twitter.com/jack/status/20/", STATUS),
        ("https://mobile.twitter.com/jack/status/20", STATUS),
        ("https://mobile.x.com/jack/status/20", STATUS),
        ("https://m.twitter.com/jack/status/20", STATUS),
        ("https://m.x.com/jack/status/20", STATUS),
        ("https://fxtwitter.com/jack/status/20", STATUS),
        ("https://vxtwitter.com/jack/status/20", STATUS),
        ("https://fixupx.com/jack/status/20", STATUS),
        ("https://X.com/jack/status/20?s=20&t=abcDEF", STATUS),
        ("https://twitter.com/jack/statuses/20", STATUS),
        ("https://x.com/jack/status/20/photo/1", STATUS),
        ("https://x.com/jack/status/20/video/1", STATUS),
        ("https://x.com/i/web/status/20", "https://x.com/i/status/20"),
        ("https://twitter.com/i/status/20", "https://x.com/i/status/20"),
        ("https://twitter.com/jack?s=20", "https://x.com/jack"),
        ("https://mobile.twitter.com/jack/media/", "https://x.com/jack/media"),
        ("https://twitter.com/search?q=cat&src=typed_query&s=20", "https://x.com/search?q=cat&src=typed_query"),
    ],
)
def test_normalize_x(url, expected):
    assert normalize(url) == expected


@pytest.mark.parametrize(
    "url",
    ["https://www.youtube.com/watch?v=abc&t=10", "https://notx.com/jack/status/20?s=20", "https://example.com/a/"],
)
def test_normalize_leaves_other_sites(url):
    assert normalize(url) == url


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://x.com/a", True),
        ("https://www.twitter.com/a", True),
        ("http://fixvx.com/a", True),
        ("https://xx.com/a", False),
        ("https://x.com.evil.org/a", False),
        ("https://youtube.com", False),
        ("not a url", False),
    ],
)
def test_is_x(url, expected):
    assert is_x(url) is expected


@pytest.mark.parametrize(
    "url",
    [
        "https://twitter.com/jack/status/20?s=20",
        "https://fxtwitter.com/jack/status/20/photo/1",
        "https://mobile.twitter.com/jack/statuses/20",
        "https://x.com/i/web/status/20",
        "https://twitter.com/i/status/20",
    ],
)
def test_normalized_status_supported_by_gallery_dl(url):
    found = extractor.find(normalize(url))
    assert found is not None and type(found).__name__ == "TwitterTweetExtractor"


def test_normalized_search_supported_by_gallery_dl():
    found = extractor.find(normalize("https://twitter.com/search?q=cat&s=20"))
    assert type(found).__name__ == "TwitterSearchExtractor"
