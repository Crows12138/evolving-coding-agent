"""Matrix operations library."""


def create_matrix(rows, cols, fill=0):
    """Create a matrix with given dimensions."""
    return [[fill] * cols for _ in range(rows)]


def add(a, b):
    """Add two matrices element-wise."""
    # Bug: no dimension check - will silently produce wrong results
    # if matrices have different dimensions
    rows = len(a)
    cols = len(a[0])
    result = create_matrix(rows, cols)
    for i in range(rows):
        for j in range(cols):
            result[i][j] = a[i][j] + b[i][j]
    return result


def multiply(a, b):
    """Multiply two matrices."""
    rows_a, cols_a = len(a), len(a[0])
    rows_b, cols_b = len(b), len(b[0])
    if cols_a != rows_b:
        raise ValueError("Incompatible dimensions for multiplication")
    # Bug: result dimensions are swapped - should be rows_a x cols_b
    result = create_matrix(cols_b, rows_a)
    for i in range(rows_a):
        for j in range(cols_b):
            result[i][j] = sum(a[i][k] * b[k][j] for k in range(cols_a))
    return result


def transpose(matrix):
    """Return the transpose of a matrix."""
    rows = len(matrix)
    cols = len(matrix[0])
    # Bug: modifies the original matrix in-place instead of creating a new one
    # This only works for square matrices, and corrupts the original
    for i in range(rows):
        for j in range(i + 1, cols):
            matrix[i][j], matrix[j][i] = matrix[j][i], matrix[i][j]
    return matrix


def determinant(matrix):
    """Calculate the determinant of a square matrix."""
    n = len(matrix)
    if n == 1:
        # Bug: should return matrix[0][0], not 0
        return 0
    if n == 2:
        return matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
    det = 0
    for j in range(n):
        minor = [row[:j] + row[j+1:] for row in matrix[1:]]
        det += ((-1) ** j) * matrix[0][j] * determinant(minor)
    return det
