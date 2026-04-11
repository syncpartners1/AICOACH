from autogpt.coaching.utils import markdown_to_html

tests = [
    "Hello *bold* and **double bold**",
    "Italic with _underscore_ or __double__",
    "* List item 1\n* List item 2",
    "- Another list\n- item",
    "# Header 1\n## Header 2",
    "Mixed *bold* and [link](http://example.com)",
    "Code `inline` and\n```python\nprint('hello')\n```",
    "Special chars: < > &",
    "*Nested *bold?**"
]

for t in tests:
    print(f"INPUT:  {t!r}")
    print(f"OUTPUT: {markdown_to_html(t)!r}")
    print("-" * 20)
