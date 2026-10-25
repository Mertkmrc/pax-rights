from pax_rights.ingest.parse import clean_line, dehyphenate, strip_repeating_lines


def test_strips_page_numbers_that_differ_only_in_digits():
    bodies = [["alpha", "bravo"], ["charlie", "delta"], ["echo", "foxtrot"], ["golf", "hotel"]]
    pages = [[f"{n} / 4", *body] for n, body in enumerate(bodies, start=1)]
    cleaned = strip_repeating_lines(pages)
    assert cleaned == bodies


def test_strips_footer_exposed_after_first_pass():
    # A nav bar sits above a print footer; it only reaches the edge window once the footer is gone.
    footer = [
        "Book",
        "My flights",
        "Check-in",
        "10/25/26, 1:36 PM",
        "Title | Site",
        "https://x",
        "1/5",
    ]
    pages = [["Article text"] * 6 + footer for _ in range(5)]
    cleaned = strip_repeating_lines(pages)
    assert all("My flights" not in lines and "https://x" not in lines for lines in cleaned)


def test_keeps_paragraph_numbers_at_page_edges():
    # EU261 pages often start with a bare paragraph number; "2." and "3." must not
    # collapse into one shape and get stripped like a page number.
    bodies = ["alpha", "bravo", "charlie", "delta", "echo"]
    pages = [[f"{n}.", body] for n, body in enumerate(bodies, start=1)]
    assert strip_repeating_lines(pages) == pages


def test_keeps_lines_that_repeat_on_few_pages():
    pages = [["Article 7", "a"], ["b"], ["c"], ["d"]]
    assert strip_repeating_lines(pages)[0] == ["Article 7", "a"]


def test_dehyphenate_joins_lowercase_continuation_only():
    assert dehyphenate("trans-\nported") == "transported"
    assert dehyphenate("non-\nEU carrier") == "non-\nEU carrier"


def test_clean_line_maps_symbol_bullets_and_drops_icons():
    assert clean_line("\uf0b7 Item") == "• Item"
    assert clean_line("\ueaca\u200b Terms of use") == " Terms of use"
