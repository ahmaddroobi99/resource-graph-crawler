from types import SimpleNamespace

from crawler.extractor import extract_passwords, extract_passwords_from_bytes, extract_passwords_from_response


def test_extracts_exact_passwords_and_ignores_example():
    text = "VISUALPING{349a583fba34c301} VISUALPING{0000deadbeef0000} VISUALPING{short}"
    assert extract_passwords(text) == {"VISUALPING{349a583fba34c301}"}


def test_header_only_match_is_ignored():
    response = SimpleNamespace(
        text="body has no credential",
        headers={"X-Debug": "VISUALPING{349a583fba34c301}"},
    )
    assert extract_passwords_from_response(response) == set()


def test_binary_ascii_scan():
    assert extract_passwords_from_bytes(b"prefix VISUALPING{abcdef0123456789} suffix") == {
        "VISUALPING{abcdef0123456789}"
    }
