from crawler.url_utils import is_in_scope, make_absolute, normalize


def test_resolves_relative_and_removes_fragment():
    base = "http://54.214.7.161/docs/topic/"
    assert make_absolute(base, "../about#section") == "http://54.214.7.161/docs/about"


def test_rejects_external_host():
    assert not is_in_scope("http://example.com/page")
    assert make_absolute("http://54.214.7.161/", "https://example.com/") is None


def test_root_path_is_stable():
    assert normalize("http://54.214.7.161/#top") == "http://54.214.7.161/"


def test_strips_tracking_and_pagination_params():
    # utm/ref/v/hl/page tags never identify a distinct resource, so they are
    # dropped and every variant collapses onto the same canonical URL.
    canonical = "http://54.214.7.161/docs/"
    assert normalize("http://54.214.7.161/docs/?utm_source=internal") == canonical
    assert normalize("http://54.214.7.161/docs/?ref=nav&v=3") == canonical
    assert normalize("http://54.214.7.161/report/?page=2") == "http://54.214.7.161/report/"


def test_preserves_meaningful_query_params():
    assert normalize("http://54.214.7.161/search?q=alerts") == "http://54.214.7.161/search?q=alerts"
