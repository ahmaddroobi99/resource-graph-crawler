from crawler.discovery import extract_from_html, extract_paths_from_text


BASE = "http://54.214.7.161/"


def test_html_discovers_browser_resource_attributes_and_styles():
    html = """
    <a href='/docs/'>docs</a><img src='/img/a.png'>
    <script src='/static/main.js'></script><link href='/style.css'>
    <iframe src='/frame'></iframe><form action='/submit'></form>
    <div data-endpoint='/data.json'></div>
    <style>.x { background: url('/bg.png'); }</style>
    """
    found = extract_from_html(html, BASE)
    assert "http://54.214.7.161/static/main.js" in found
    assert "http://54.214.7.161/bg.png" in found
    assert "http://54.214.7.161/data.json" in found


def test_html_discovers_style_attribute():
    found = extract_from_html('<div style="background: url(../img/bg.png)"></div>',
                              "http://54.214.7.161/docs/page/")
    assert "http://54.214.7.161/docs/img/bg.png" in found


def test_text_discovery_handles_quoted_paths_and_filters_external_urls():
    found = extract_paths_from_text("const menu = ['/docs/upstream/', 'https://example.com/x'];", BASE)
    assert "http://54.214.7.161/docs/upstream/" in found
    assert all("example.com" not in url for url in found)
