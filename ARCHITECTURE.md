# Architecture

The crawler models the website as a directed graph: fetched URLs are nodes,
and references in their bodies are edges. `fetcher.py` is the only network
layer. It sends Basic Auth, bounds redirects to the challenge host, and
returns response objects without raising on HTTP failures.

`url_utils.py` resolves references, strips fragments, and enforces the exact
host boundary. `frontier.py` owns the FIFO queue, visited set, and deduplicated
results. `discovery.py` parses HTML tags, data attributes, styles, JavaScript,
CSS, and generic quoted path strings. `extractor.py` matches only exact body
passwords; it never examines response headers.

`engine.py` performs BFS. Each dequeued URL is marked visited before fetching,
then its body is extracted and its newly discovered in-scope resources are
queued. Images receive a raw-byte scan, with OCR available when optional
libraries are installed. The crawl is complete only when the queue is empty
and `discovered <= visited`; a page limit intentionally reports incomplete
when it interrupts that condition.
