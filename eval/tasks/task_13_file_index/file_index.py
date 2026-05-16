"""File indexer for searching and analyzing files in a directory."""

import os
import hashlib


class FileIndex:
    def __init__(self):
        self.files = {}  # path -> {name, size, content_hash, mtime}

    def index_dir(self, directory):
        """Index all files in a directory recursively."""
        if not os.path.isdir(directory):
            raise ValueError(f"Not a directory: {directory}")
        # Bug: doesn't skip hidden files (files/dirs starting with '.')
        for root, dirs, files in os.walk(directory):
            for fname in files:
                fpath = os.path.join(root, fname)
                stat = os.stat(fpath)
                with open(fpath, 'rb') as f:
                    content = f.read()
                self.files[fpath] = {
                    'name': fname,
                    'size': stat.st_size,
                    'content_hash': hashlib.md5(content).hexdigest(),
                    'mtime': stat.st_mtime,
                }

    def search(self, query):
        """Search indexed files by filename. Should be case-insensitive."""
        if not query:
            return []
        # Bug: comparison is case-sensitive, should be case-insensitive
        return [path for path, info in self.files.items()
                if query in info['name']]

    def get_stats(self, directory):
        """Get statistics about indexed files in a directory."""
        # Bug: only counts files directly in directory, not in subdirectories
        matching = {p: info for p, info in self.files.items()
                    if os.path.dirname(p) == directory}
        if not matching:
            return {'total_files': 0, 'total_size': 0, 'avg_size': 0}
        total_size = sum(info['size'] for info in matching.values())
        return {
            'total_files': len(matching),
            'total_size': total_size,
            'avg_size': total_size / len(matching),
        }

    def find_duplicates(self):
        """Find duplicate files based on content."""
        # Bug: groups by filename instead of content_hash
        seen = {}
        duplicates = []
        for path, info in self.files.items():
            key = info['name']  # should be info['content_hash']
            if key in seen:
                if seen[key] not in duplicates:
                    duplicates.append(seen[key])
                duplicates.append(path)
            else:
                seen[key] = path
        return duplicates
