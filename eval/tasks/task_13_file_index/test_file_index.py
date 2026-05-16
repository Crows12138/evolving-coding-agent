import os
import tempfile
import shutil
from file_index import FileIndex


def _create_test_tree():
    """Create a temporary directory tree for testing."""
    base = tempfile.mkdtemp()
    # Regular files
    _write(os.path.join(base, "readme.txt"), "hello world")
    _write(os.path.join(base, "README.md"), "# Title")
    _write(os.path.join(base, "data.csv"), "a,b,c")
    # Hidden file
    _write(os.path.join(base, ".hidden"), "secret")
    # Subdirectory with files
    sub = os.path.join(base, "sub")
    os.makedirs(sub)
    _write(os.path.join(sub, "nested.txt"), "nested content")
    _write(os.path.join(sub, "data.csv"), "different content")
    # Hidden directory
    hidden_dir = os.path.join(base, ".git")
    os.makedirs(hidden_dir)
    _write(os.path.join(hidden_dir, "config"), "git config")
    return base


def _write(path, content):
    with open(path, 'w') as f:
        f.write(content)


# --- index_dir tests ---

def test_index_dir_basic():
    base = _create_test_tree()
    try:
        idx = FileIndex()
        idx.index_dir(base)
        # Should have indexed files (exact count depends on hidden file handling)
        assert len(idx.files) > 0
    finally:
        shutil.rmtree(base)


def test_index_dir_skips_hidden():
    """Hidden files and directories (starting with '.') should be skipped."""
    base = _create_test_tree()
    try:
        idx = FileIndex()
        idx.index_dir(base)
        names = [info['name'] for info in idx.files.values()]
        assert ".hidden" not in names
        assert "config" not in names  # file inside .git/
    finally:
        shutil.rmtree(base)


def test_index_dir_invalid():
    idx = FileIndex()
    try:
        idx.index_dir("/nonexistent/path")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


# --- search tests ---

def test_search_case_insensitive():
    """Search should be case-insensitive."""
    base = _create_test_tree()
    try:
        idx = FileIndex()
        idx.index_dir(base)
        results = idx.search("readme")
        names = [os.path.basename(p) for p in results]
        # Searching "readme" should find both "readme.txt" and "README.md"
        assert len(names) >= 2
        assert any("README" in n for n in names)
    finally:
        shutil.rmtree(base)


def test_search_empty_query():
    idx = FileIndex()
    assert idx.search("") == []


def test_search_no_match():
    base = _create_test_tree()
    try:
        idx = FileIndex()
        idx.index_dir(base)
        assert idx.search("nonexistent_xyz") == []
    finally:
        shutil.rmtree(base)


# --- get_stats tests ---

def test_get_stats_includes_subdirs():
    """Stats should include files in subdirectories."""
    base = _create_test_tree()
    try:
        idx = FileIndex()
        idx.index_dir(base)
        stats = idx.get_stats(base)
        # Should count all non-hidden files including those in sub/
        assert stats['total_files'] >= 5  # readme.txt, README.md, data.csv, sub/nested.txt, sub/data.csv
    finally:
        shutil.rmtree(base)


def test_get_stats_empty():
    idx = FileIndex()
    stats = idx.get_stats("/some/empty/dir")
    assert stats['total_files'] == 0


# --- find_duplicates tests ---

def test_find_duplicates_by_content():
    """Duplicates should be identified by content hash, not filename."""
    base = tempfile.mkdtemp()
    try:
        # Two files with same content but different names
        _write(os.path.join(base, "file_a.txt"), "same content")
        _write(os.path.join(base, "file_b.txt"), "same content")
        # One file with different content
        _write(os.path.join(base, "file_c.txt"), "different content")
        idx = FileIndex()
        idx.index_dir(base)
        dupes = idx.find_duplicates()
        assert len(dupes) == 2
        dupe_names = [os.path.basename(p) for p in dupes]
        assert "file_a.txt" in dupe_names
        assert "file_b.txt" in dupe_names
    finally:
        shutil.rmtree(base)


def test_find_duplicates_same_name_different_content():
    """Files with same name but different content are NOT duplicates."""
    base = _create_test_tree()
    try:
        idx = FileIndex()
        idx.index_dir(base)
        dupes = idx.find_duplicates()
        # data.csv exists in both base and sub/ but with different content
        dupe_names = [os.path.basename(p) for p in dupes]
        # They should NOT be considered duplicates (different content)
        assert not ("data.csv" in dupe_names and dupe_names.count("data.csv") == 2)
    finally:
        shutil.rmtree(base)
