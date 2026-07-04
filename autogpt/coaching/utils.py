import html
import re

def markdown_to_html(text: str) -> str:
    """
    Converts basic Markdown to Telegram-compatible HTML.
    
    Telegram supports:
    <b>bold</b>, <strong>bold</strong>
    <i>italic</i>, <em>italic</em>
    <u>underline</u>
    <s>strikethrough</s>
    <span class="tg-spoiler">spoiler</span>
    <a href="http://www.example.com/">inline URL</a>
    <code>inline fixed-width code</code>
    <pre><code class="language-python">pre-formatted fixed-width code block</code></pre>

    Steps:
    1. Escape literal <, >, & first.
    2. Convert headers to bold.
    3. Convert bold (** or *).
    4. Convert italic (__ or _).
    5. Convert inline code (`).
    6. Convert links [text](url).
    """
    if not text:
        return ""

    # 1. Escape HTML entities
    text = html.escape(text)

    # 2. Headers (# Header) -> Bold
    text = re.sub(r'^#+\s+(.*?)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # 3. Bullets (* Item) -> • Item
    # We do this BEFORE bold to avoid consuming the leading * as a bold start
    text = re.sub(r'^\*\s+', r'• ', text, flags=re.MULTILINE)
    text = re.sub(r'^\-\s+', r'• ', text, flags=re.MULTILINE)

    # 4. Bold (**text** or *text*)
    # We use patterns that try to avoid matching across lines or between unrelated bullets
    text = re.sub(r'\*\*(?=\S)(.+?)(?<=\S)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    text = re.sub(r'\*(?=\S)([^\*\n]+?)(?<=\S)\*', r'<b>\1</b>', text)

    # 5. Italic (__text__ or _text_)
    text = re.sub(r'__(?=\S)(.+?)(?<=\S)__', r'<i>\1</i>', text, flags=re.DOTALL)
    text = re.sub(r'_(?=\S)([^_\n]+?)(?<=\S)_', r'<i>\1</i>', text)

    # 6. Code blocks (```code```)
    text = re.sub(r'```(?:[\w\-\.]+)?\n?(.*?)\n?```', r'<pre><code>\1</code></pre>', text, flags=re.DOTALL)

    # 7. Inline code (`text`)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)

    # 8. Links ([text](url))
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)

    return text
