"""BFS frontier and crawl result state."""

from collections import deque

from config import EXAMPLE_PASSWORD
from crawler.url_utils import normalize


class Visited:
    """Set of normalized resources already fetched or attempted."""

    def __init__(self) -> None:
        self._items: set[str] = set()

    def add(self, url: str) -> None:
        self._items.add(normalize(url))

    def __contains__(self, url: str) -> bool:
        return normalize(url) in self._items

    def __len__(self) -> int:
        return len(self._items)

    def as_set(self) -> set[str]:
        return set(self._items)


class Frontier:
    """Deduplicated FIFO queue of URLs waiting to be visited."""

    def __init__(self, visited: Visited | None = None) -> None:
        self._queue: deque[str] = deque()
        self._pending: set[str] = set()
        self._visited = visited

    def add(self, url: str) -> bool:
        normalized = normalize(url)
        if normalized in self._pending or (self._visited and normalized in self._visited):
            return False
        self._queue.append(normalized)
        self._pending.add(normalized)
        return True

    def get(self) -> str | None:
        if not self._queue:
            return None
        url = self._queue.popleft()
        self._pending.remove(url)
        return url

    @property
    def empty(self) -> bool:
        return not self._queue

    @property
    def is_empty(self) -> bool:
        return self.empty

    def __len__(self) -> int:
        return len(self._queue)


class Results:
    """Deduplicated password results, excluding the example value."""

    def __init__(self) -> None:
        self._items: set[str] = set()

    def add(self, password: str) -> bool:
        if password == EXAMPLE_PASSWORD:
            return False
        before = len(self._items)
        self._items.add(password)
        return len(self._items) > before

    def update(self, passwords: set[str]) -> None:
        for password in passwords:
            self.add(password)

    def get_all(self) -> list[str]:
        return sorted(self._items)

    def __len__(self) -> int:
        return len(self._items)
