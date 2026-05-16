from csv_parser import parse_csv, csv_to_dicts


def test_simple_csv():
    text = "a,b,c\n1,2,3"
    assert parse_csv(text) == [["a", "b", "c"], ["1", "2", "3"]]


def test_quoted_fields():
    text = 'name,desc\nAlice,"likes cats, dogs"'
    result = parse_csv(text)
    assert result[1] == ["Alice", "likes cats, dogs"]


def test_skip_empty_lines():
    text = "a,b\n\n1,2\n\n3,4"
    result = parse_csv(text)
    assert len(result) == 3  # header + 2 data rows, no empty


def test_strip_whitespace():
    text = " a , b \n 1 , 2 "
    result = parse_csv(text)
    assert result[0] == ["a", "b"]
    assert result[1] == ["1", "2"]


def test_csv_to_dicts():
    text = "name,age\nAlice,30\nBob,25"
    result = csv_to_dicts(text)
    assert result == [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]


def test_csv_to_dicts_missing_fields():
    text = "name,age,city\nAlice,30\nBob,25,NYC"
    result = csv_to_dicts(text)
    assert result[0] == {"name": "Alice", "age": "30", "city": ""}
    assert result[1] == {"name": "Bob", "age": "25", "city": "NYC"}
