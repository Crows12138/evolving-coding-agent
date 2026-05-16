import copy
from matrix import create_matrix, add, multiply, transpose, determinant


# --- add tests ---

def test_add_basic():
    a = [[1, 2], [3, 4]]
    b = [[5, 6], [7, 8]]
    result = add(a, b)
    assert result == [[6, 8], [10, 12]]


def test_add_dimension_mismatch():
    """Adding matrices of different dimensions should raise an error."""
    a = [[1, 2], [3, 4]]
    b = [[1, 2, 3], [4, 5, 6]]
    try:
        add(a, b)
        assert False, "Should have raised an error"
    except (ValueError, IndexError):
        pass


def test_add_different_row_count():
    """Adding matrices with different row counts should raise an error."""
    a = [[1, 2]]
    b = [[1, 2], [3, 4]]
    try:
        add(a, b)
        assert False, "Should have raised an error"
    except (ValueError, IndexError):
        pass


# --- multiply tests ---

def test_multiply_square():
    a = [[1, 2], [3, 4]]
    b = [[5, 6], [7, 8]]
    result = multiply(a, b)
    assert result == [[19, 22], [43, 50]]


def test_multiply_non_square():
    """1x3 * 3x2 should give 1x2 result."""
    a = [[1, 2, 3]]
    b = [[4, 5], [6, 7], [8, 9]]
    result = multiply(a, b)
    assert len(result) == 1
    assert len(result[0]) == 2
    assert result == [[40, 46]]


def test_multiply_incompatible():
    a = [[1, 2], [3, 4]]
    b = [[1, 2, 3]]
    try:
        multiply(a, b)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


# --- transpose tests ---

def test_transpose_basic():
    m = [[1, 2, 3], [4, 5, 6]]
    result = transpose(m)
    assert result == [[1, 4], [2, 5], [3, 6]]


def test_transpose_does_not_modify_original():
    """Transpose should return a new matrix, not modify the original."""
    original = [[1, 2], [3, 4]]
    original_copy = copy.deepcopy(original)
    transpose(original)
    assert original == original_copy


# --- determinant tests ---

def test_determinant_1x1():
    assert determinant([[5]]) == 5


def test_determinant_2x2():
    m = [[1, 2], [3, 4]]
    assert determinant(m) == -2


def test_determinant_3x3():
    m = [[1, 2, 3], [4, 5, 6], [7, 8, 0]]
    assert determinant(m) == 27
