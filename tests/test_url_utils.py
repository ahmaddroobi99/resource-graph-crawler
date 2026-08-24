from crawler.url_utils import is_in_scope, make_absolute, normalize


def test_resolves_relative_and_removes_fragment():
    base = "http://54.214.7.161/docs/topic/"
    assert make_absolute(base, "../about#section") == "http://54.214.7.161/docs/about"


def test_rejects_external_host():
    assert not is_in_scope("http://example.com/page")
    assert make_absolute("http://54.214.7.161/", "https://example.com/") is None


def test_root_path_is_stable():
    assert normalize("http://54.214.7.161/#top") == "http://54.214.7.161/"
