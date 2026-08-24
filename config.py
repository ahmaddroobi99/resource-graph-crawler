"""Configuration for the Visualping crawler challenge."""

import re


BASE_URL = "http://54.214.7.161/"
ALLOWED_HOST = "54.214.7.161"
USERNAME = "ahmad.droobi2"
PASSWORD = "2dd4b97903ace571f147"
PASSWORD_REGEX = r"VISUALPING\{[0-9a-fA-F]{16}\}"
COMPILED_PASSWORD_RE = re.compile(PASSWORD_REGEX)
EXAMPLE_PASSWORD = "VISUALPING{0000deadbeef0000}"
MAX_PAGES = 500
REQUEST_TIMEOUT = 10
USER_AGENT = "VisualpingCrawler/1.0 (student challenge)"
