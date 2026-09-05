# -*- coding: utf-8 -*-
"""Recently used search queries, kept in the addon's profile directory."""

import json
import os

from . import kodi

FILE_NAME = "searches.json"
LIMIT = 20


def _path():
    return os.path.join(kodi.profile_dir(), FILE_NAME)


def load():
    """The stored queries, newest first. Never raises."""
    try:
        with open(_path(), "r", encoding="utf-8") as handle:
            queries = json.load(handle)
    except (IOError, OSError, ValueError):
        return []
    return [q for q in queries if isinstance(q, str)][:LIMIT]


def _save(queries):
    try:
        with open(_path(), "w", encoding="utf-8") as handle:
            json.dump(queries[:LIMIT], handle, ensure_ascii=False)
    except (IOError, OSError):
        # A search that cannot be remembered is still a search worth running.
        kodi.log("Could not write the search history")


def add(query):
    query = (query or "").strip()
    if not query:
        return
    queries = [q for q in load() if q.casefold() != query.casefold()]
    _save([query] + queries)


def remove(query):
    _save([q for q in load() if q.casefold() != (query or "").casefold()])


def clear():
    _save([])
