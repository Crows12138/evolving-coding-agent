"""Simple CSV parser."""

def parse_csv(text):
    rows = []
    for line in text.strip().split("\n"):
        fields = line.split(",")
        rows.append(fields)
    return rows

def csv_to_dicts(text, headers=None):
    rows = parse_csv(text)
    if not rows:
        return []
    if headers is None:
        headers = rows[0]
        rows = rows[1:]
    result = []
    for row in rows:
        d = {headers[i]: row[i] for i in range(len(headers))}
        result.append(d)
    return result
