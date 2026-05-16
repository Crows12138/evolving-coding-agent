from config_parser import ConfigParser


SAMPLE_CONFIG = """
# mode = production
[server]
host = localhost
port = 8080
debug = true

[database]
; retry = 3
host = db.example.com
port = 5432
name = mydb
password =
"""


def test_parse_sections():
    cp = ConfigParser()
    cp.parse(SAMPLE_CONFIG)
    assert "server" in cp.sections()
    assert "database" in cp.sections()


def test_get_value():
    cp = ConfigParser()
    cp.parse(SAMPLE_CONFIG)
    assert cp.get("server", "host") == "localhost"
    assert cp.get("server", "port") == "8080"


def test_get_from_another_section():
    cp = ConfigParser()
    cp.parse(SAMPLE_CONFIG)
    assert cp.get("database", "host") == "db.example.com"
    assert cp.get("database", "name") == "mydb"


def test_get_fallback():
    cp = ConfigParser()
    cp.parse(SAMPLE_CONFIG)
    assert cp.get("server", "nonexistent", fallback="default") == "default"


def test_comment_lines_ignored():
    cp = ConfigParser()
    cp.parse(SAMPLE_CONFIG)
    # "# mode = production" should be treated as comment, not as a key-value pair
    default_items = dict(cp.items("__default__")) if "__default__" in cp.sections() or "__default__" in cp._sections else {}
    assert "# mode" not in default_items
    items_server = dict(cp.items("server"))
    assert len(items_server) == 3  # host, port, debug only


def test_semicolon_comment_ignored():
    cp = ConfigParser()
    cp.parse(SAMPLE_CONFIG)
    items = dict(cp.items("database"))
    # "; retry = 3" should be ignored
    assert "; retry" not in items
    assert len(items) == 4  # host, port, name, password


def test_empty_value():
    cp = ConfigParser()
    cp.parse(SAMPLE_CONFIG)
    # password is set to empty string, should return "" not fallback
    assert cp.get("database", "password") == ""


def test_set_new_value():
    cp = ConfigParser()
    cp.parse(SAMPLE_CONFIG)
    # After parse, _current_section is "database", so setting "server" should still work
    cp.set("server", "host", "0.0.0.0")
    assert cp.get("server", "host") == "0.0.0.0"


def test_set_new_key():
    cp = ConfigParser()
    cp.parse(SAMPLE_CONFIG)
    cp.set("server", "timeout", "30")
    assert cp.get("server", "timeout") == "30"


def test_set_new_section():
    cp = ConfigParser()
    cp.parse("")
    cp.set("logging", "level", "INFO")
    assert cp.get("logging", "level") == "INFO"
    assert "logging" in cp.sections()


def test_items():
    cp = ConfigParser()
    cp.parse("[test]\na = 1\nb = 2")
    items = cp.items("test")
    assert ("a", "1") in items
    assert ("b", "2") in items


def test_default_section():
    cp = ConfigParser()
    cp.parse("global_key = global_value\n[section]\nkey = val")
    assert cp.get("__default__", "global_key") == "global_value"
