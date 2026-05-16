"""INI-style configuration file parser."""


class ConfigParser:
    def __init__(self):
        self._sections = {}
        self._current_section = None

    def parse(self, text):
        """Parse INI-style configuration text."""
        self._sections = {}
        self._current_section = None
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # BUG: missing handling for comment lines (# or ;)
            # lines starting with # or ; should be skipped
            if line.startswith("[") and line.endswith("]"):
                section_name = line[1:-1].strip()
                self._sections[section_name] = {}
                self._current_section = section_name
            elif "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if self._current_section is None:
                    if "__default__" not in self._sections:
                        self._sections["__default__"] = {}
                    self._sections["__default__"][key] = value
                else:
                    self._sections[self._current_section][key] = value

    def get(self, section, key, fallback=None):
        """Get a value from a section. Returns fallback if not found."""
        if section not in self._sections:
            return fallback
        sect = self._sections[section]
        if key not in sect:
            return fallback
        value = sect[key]
        if value == "":
            return fallback  # BUG: empty string is a valid value, should not return fallback
        return value

    def set(self, section, key, value):
        """Set a value in a section."""
        if section not in self._sections:
            self._sections[section] = {}
        # BUG: uses _current_section instead of the given section parameter
        if self._current_section is not None:
            self._sections[self._current_section][key] = str(value)
        else:
            self._sections[section][key] = str(value)

    def sections(self):
        """Return a list of section names (excluding __default__)."""
        return [s for s in self._sections if s != "__default__"]

    def items(self, section):
        """Return all key-value pairs in a section."""
        if section not in self._sections:
            return []
        return list(self._sections[section].items())

    def to_string(self):
        """Serialize config back to INI format."""
        lines = []
        if "__default__" in self._sections:
            for key, value in self._sections["__default__"].items():
                lines.append(f"{key} = {value}")
            lines.append("")
        for section in self.sections():
            lines.append(f"[{section}]")
            for key, value in self._sections[section].items():
                lines.append(f"{key} = {value}")
            lines.append("")
        return "\n".join(lines)
