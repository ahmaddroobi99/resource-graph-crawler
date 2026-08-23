Project setup + config + password regex + README skeleton

HTTP Client / Fetcher (Basic Auth, timeouts, redirects, status handling)


URL utilities (normalize, resolve relative, same-host scope, strip fragments)


Data structures: Frontier (queue) + Visited set + Results set

HTML Parser / Discovery (BeautifulSoup or regex for a/img/script/link/iframe/form + data attributes)

Generic text / JS / CSS discovery (extract path-like strings from any text resource)

Content-Type router + Password Extractor (regex + ignore header-only passwords)

Core BFS crawl loop + completeness condition (frontier empty)

Optional processors: Images (save + OCR with pytesseract or easyocr) + any PDF if present

CLI entrypoint, pretty output of 8 passwords, crawl stats, how-we-know-complete explanation, packaging Architecture should be layered and modular so each task produces a testable module.


I'll draft the full requirements.md now based on this. 

any additional edge cases you spotted (e.g. base64, comments, JSON endpoints, pagination that needs special handling)?
