import html
import re

def markdown_to_html(text: str) -> str:
    if not text:
        return ""
    text = html.escape(text)
    text = re.sub(r'^#+\s+(.*?)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    text = re.sub(r'^\*\s+', r'• ', text, flags=re.MULTILINE)
    text = re.sub(r'^\-\s+', r'• ', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(?=\S)(.+?)(?<=\S)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    text = re.sub(r'\*(?=\S)([^\*\n]+?)(?<=\S)\*', r'<b>\1</b>', text)
    text = re.sub(r'__(?=\S)(.+?)(?<=\S)__', r'<i>\1</i>', text, flags=re.DOTALL)
    text = re.sub(r'_(?=\S)([^_\n]+?)(?<=\S)_', r'<i>\1</i>', text)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    text = re.sub(r'```(?:[\w\-\.]+)?\n?(.*?)\n?```', r'<pre><code>\1</code></pre>', text, flags=re.DOTALL)
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
    return text

tests = [
    ("Hello *bold*", "Hello <b>bold</b>"),
    ("**double**", "<b>double</b>"),
    ("_italic_", "<i>italic</i>"),
    ("__double italic__", "<i>double italic</i>"),
    ("* List item 1\n* List item 2", "• List item 1\n• List item 2"),
    ("# Header\nContent", "<b>Header</b>\nContent"),
    ("[Google](https://google.com)", '<a href="https://google.com">Google</a>'),
    ("`code`", "<code>code</code>"),
    ("```\nblock\n```", "<pre><code>\nblock\n</code></pre>"),
    ("Special: < > &", "Special: &lt; &gt; &amp;"),
]

for t, expected in tests:
    result = markdown_to_html(t)
    if result == expected:
        print(f"PASS: {t!r}")
    else:
        print(f"FAIL: {t!r}\n  Expected: {expected!r}\n  Got:      {result!r}")
