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


def test_binary_scan_reads_utf16_metadata():
    # Passwords hidden in UTF-16 image metadata (e.g. JPEG EXIF UserComment)
    # are invisible to a UTF-8-only scan.
    payload = "VISUALPING{db7e533a9cef7f72}".encode("utf-16-le")
    assert extract_passwords_from_bytes(payload) == {"VISUALPING{db7e533a9cef7f72}"}


def test_decodes_javascript_character_code_array():
    from crawler.extractor import extract_encoded_passwords
    beacon = [86, 73, 83, 85, 65, 76, 80, 73, 78, 71, 123,
              102, 98, 55, 50, 53, 101, 49, 102, 51, 100, 54, 55, 50, 56, 98, 49, 125]
    text = "var _beacon = [%s];" % ", ".join(str(n) for n in beacon)
    assert extract_encoded_passwords(text) == {"VISUALPING{fb725e1f3d6728b1}"}


def test_decodes_base64_encoded_password():
    import base64
    from crawler.extractor import extract_encoded_passwords
    token = base64.b64encode(b"VISUALPING{0123456789abcdef}").decode()
    assert extract_encoded_passwords(f"data-blob='{token}'") == {"VISUALPING{0123456789abcdef}"}


def test_encoded_extraction_has_no_false_positives():
    from crawler.extractor import extract_encoded_passwords
    assert extract_encoded_passwords("just some [1, 2, 3, 4, 5, 6, 7, 8] ordinary text") == set()
