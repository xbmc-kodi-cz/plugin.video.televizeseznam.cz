# -*- coding: utf-8 -*-
"""A small time-to-live cache for API responses that rarely change.

The navigation menus are rebuilt by editors roughly once a day, yet without
this every step into a menu paid for a fresh round trip.
"""

import hashlib
import json
import os
import time

import xbmcvfs

from . import kodi

DIRECTORY = "cache"
SUFFIX = ".json"

# reuselanguageinvoker keeps the interpreter alive between clicks, so this
# survives from one screen to the next and spares the disk read and the JSON
# parse of a large index. It follows the same setting as the files: turning
# caching off is how you watch the addon fetch fresh data, and a memo that
# ignored the switch would quietly defeat that.
_memory = {}


def _path(key):
    # Keys carry API ids, so hash them into something safe as a file name.
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return os.path.join(kodi.profile_dir(DIRECTORY), digest + SUFFIX)


def get(key, ttl):
    """The stored value for ``key``, or None when missing, stale or disabled."""
    if not kodi.cache_enabled():
        return None

    stored, value = _memory.get(key, (0, None))
    if stored and time.time() - stored <= ttl:
        return value

    try:
        with open(_path(key), "r", encoding="utf-8") as handle:
            entry = json.load(handle)
    except (IOError, OSError, ValueError):
        return None
    if not isinstance(entry, dict):
        return None

    stored = entry.get("stored", 0)
    if time.time() - stored > ttl:
        return None

    value = entry.get("value")
    _memory[key] = (stored, value)
    return value


def put(key, value):
    if not kodi.cache_enabled():
        return
    _memory[key] = (time.time(), value)
    try:
        with open(_path(key), "w", encoding="utf-8") as handle:
            json.dump({"stored": time.time(), "value": value}, handle)
    except (IOError, OSError, TypeError):
        # A response that cannot be cached is still a usable response.
        kodi.log("Could not cache {0}".format(key))


def clear():
    """Drop every cached response, in memory and on disk."""
    _memory.clear()
    directory = kodi.profile_dir(DIRECTORY)
    _, files = xbmcvfs.listdir(directory + os.sep)
    for name in files:
        if name.endswith(SUFFIX):
            xbmcvfs.delete(os.path.join(directory, name))
