from text_processor import word_count, sentence_split, extract_emails, slugify


# --- word_count tests ---

def test_word_count_simple():
    assert word_count("hello world") == 2


def test_word_count_with_punctuation():
    """Standalone punctuation tokens should not be counted as words."""
    # "hello - world" has 2 words, the dash is not a word
    assert word_count("hello - world") == 2


def test_word_count_empty():
    assert word_count("") == 0
    assert word_count(None) == 0


def test_word_count_only_words():
    """Should only count actual words, not punctuation or symbols."""
    assert word_count("one. two. three.") == 3


# --- sentence_split tests ---

def test_sentence_split_simple():
    text = "Hello world. How are you. Fine thanks."
    result = sentence_split(text)
    assert len(result) == 3


def test_sentence_split_with_abbreviations():
    """Should not split at abbreviations like Mr. or Dr."""
    text = "Mr. Smith went to Washington. He had a meeting."
    result = sentence_split(text)
    assert len(result) == 2
    assert "Mr. Smith" in result[0] or "Mr" in result[0]


def test_sentence_split_empty():
    assert sentence_split("") == []
    assert sentence_split(None) == []


# --- extract_emails tests ---

def test_extract_emails_valid():
    text = "Contact us at user@example.com or admin@test.org"
    result = extract_emails(text)
    assert "user@example.com" in result
    assert "admin@test.org" in result


def test_extract_emails_rejects_invalid():
    """Should not match emails with consecutive dots or leading dots."""
    text = "bad emails: user@.com, user@exam..ple.com, .user@example.com"
    result = extract_emails(text)
    # None of these should be matched
    assert len(result) == 0


def test_extract_emails_empty():
    assert extract_emails("") == []
    assert extract_emails("no emails here") == []


# --- slugify tests ---

def test_slugify_simple():
    assert slugify("Hello World") == "hello-world"


def test_slugify_consecutive_special_chars():
    """Consecutive special characters should produce a single hyphen."""
    assert slugify("hello---world") == "hello-world"
    assert slugify("hello   world") == "hello-world"
    assert slugify("hello!@#world") == "hello-world"


def test_slugify_leading_trailing():
    assert slugify("--hello--") == "hello"
    assert slugify("  hello  ") == "hello"


def test_slugify_empty():
    assert slugify("") == ""
    assert slugify(None) == ""
