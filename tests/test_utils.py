from utils import *

def test_create_code_is_six_digit_string():
    code = create_code()
    assert isinstance(code,str)
    assert len(code)==6
    assert code.isdigit()

def test_create_code_is_random():
    codes = {create_code() for _ in range(50)}
    assert len(codes) > 1

def test_get_welcome_message_contains_username():
    for _ in range(50):
        msg = get_welcome_message("John")
        assert "John" in msg

def test_md_to_html_converts_heading():
    result = md_to_html("# Hello World!")
    assert "<h1>Hello World!</h1>" in result


def test_md_to_html_converts_bold():
    result = md_to_html("This is **bold** text.")
    assert "<strong>bold</strong>" in result


def test_md_to_html_converts_fenced_code():
    md = "```python\nprint('hi')\n```"
    result = md_to_html(md)
    assert "print" in result
    assert "<code" in result or "<pre" in result


def test_md_to_html_wraps_plain_text_in_paragraph():
    result = md_to_html("Hello World")
    assert "<p>Hello World</p>" in result


def test_md_to_html_preserves_inline_and_display_latex():
    md = r"Inline $x_1 + x_2$ and \(a_1\) and $$\frac{a}{b}$$ and \[E = mc^2\]"
    result = md_to_html(md)
    assert "$x_1 + x_2$" in result
    assert r"\(a_1\)" in result
    assert r"$$\frac{a}{b}$$" in result
    assert r"\[E = mc^2\]" in result
    assert "<em>" not in result
    assert "arithmatex" not in result