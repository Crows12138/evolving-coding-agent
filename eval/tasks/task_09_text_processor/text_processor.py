"""Text processing utilities."""

import re


def word_count(text):
    """Count the number of words in text."""
    if not text:
        return 0
    # Bug: split() without args would handle this correctly,
    # but splitting on spaces and counting all tokens includes punctuation-only tokens
    words = text.split(" ")
    return len([w for w in words if w])


def sentence_split(text):
    """Split text into sentences."""
    if not text:
        return []
    # Bug: splits on any period followed by space and uppercase letter,
    # incorrectly splitting at abbreviations like "Mr." or "Dr."
    sentences = re.split(r'\.(?=\s+[A-Z])', text)
    return [s.strip() for s in sentences if s.strip()]


def extract_emails(text):
    """Extract email addresses from text."""
    if not text:
        return []
    # Bug: regex is too loose - allows consecutive dots, leading dots,
    # and doesn't require proper TLD length
    pattern = r'[\w.+-]+@[\w.]+\.\w+'
    return re.findall(pattern, text)


def slugify(text):
    """Convert text to URL-friendly slug."""
    if not text:
        return ""
    text = text.lower()
    # Bug: replaces each special character individually, so consecutive
    # special chars like "hello---world" or "hello   world" produce "hello---world"
    text = re.sub(r'[^a-z0-9]', '-', text)
    # Missing: should collapse consecutive hyphens into one
    text = text.strip('-')
    return text
