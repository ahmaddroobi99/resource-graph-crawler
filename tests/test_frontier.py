from crawler.frontier import Frontier, Results, Visited


def test_frontier_deduplicates_pending_and_visited_urls():
    visited = Visited()
    frontier = Frontier(visited)
    assert frontier.add("http://54.214.7.161/page#one")
    assert not frontier.add("http://54.214.7.161/page#two")
    assert frontier.get() == "http://54.214.7.161/page"
    visited.add("http://54.214.7.161/page")
    assert not frontier.add("http://54.214.7.161/page")


def test_results_ignore_example_and_deduplicate():
    results = Results()
    assert results.add("VISUALPING{0000000000000001}")
    assert not results.add("VISUALPING{0000000000000001}")
    assert not results.add("VISUALPING{0000deadbeef0000}")
    assert len(results) == 1
