# -*- coding: utf-8 -*-
"""Kodi-facing helpers: settings, localisation and metadata.

Targets Kodi 21 (Omega) and newer, so the modern InfoTag API is used directly.
"""

import os

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

_addon = None


def refresh():
    """Rebuild the addon handle.

    Called once per plugin run so a settings change is picked up even when
    reuselanguageinvoker keeps the interpreter alive between invocations.
    """
    global _addon
    _addon = xbmcaddon.Addon()


def L(string_id):
    return _addon.getLocalizedString(string_id)


def log(message, level=xbmc.LOGDEBUG):
    xbmc.log("[plugin.video.televizeseznam.cz] {0}".format(message), level)


def profile_dir(*parts):
    """An existing directory inside the addon's profile.

    The trailing separator matters: xbmcvfs.exists() only recognises a path as
    a directory when it ends with one, and reports every folder as missing
    otherwise.
    """
    directory = os.path.join(
        xbmcvfs.translatePath(_addon.getAddonInfo("profile")), *parts
    )
    if not xbmcvfs.exists(directory + os.sep):
        xbmcvfs.mkdirs(directory)
    return directory


# -- settings -----------------------------------------------------------------


def setting_int(key, default=0):
    try:
        return _addon.getSettingInt(key)
    except (ValueError, TypeError):
        return default


def setting_bool(key, default=True):
    try:
        return _addon.getSettingBool(key)
    except (ValueError, TypeError):
        return default


def cache_enabled():
    return setting_bool("cache", True)


def page_size():
    return max(1, min(100, setting_int("limit", 20)))


# Index in settings.xml -> (protocol, maximum vertical resolution).
#
# Progressive mp4 is the default because it starts far faster: its moov atom
# is at the front of the file and it needs no master playlist, no variant
# playlist and no MPEG-TS probing before the first frame. HLS is kept as an
# explicit choice for connections that need the bitrate to adapt.
_QUALITY_CHOICES = (
    ("mp4", 0),
    ("mp4", 1080),
    ("mp4", 720),
    ("mp4", 480),
    ("mp4", 360),
    ("mp4", 240),
    ("hls", 0),
)


def stream_choice():
    """Return ``(protocol, max_height)`` for the configured quality."""
    choice = setting_int("quality", 0)
    if 0 <= choice < len(_QUALITY_CHOICES):
        return _QUALITY_CHOICES[choice]
    return _QUALITY_CHOICES[0]



# -- notifications ------------------------------------------------------------


def notify(message, icon=xbmcgui.NOTIFICATION_INFO, millis=5000):
    xbmcgui.Dialog().notification(
        _addon.getAddonInfo("name"), message, icon, millis
    )


def error(message):
    log(message, xbmc.LOGERROR)
    notify(message, xbmcgui.NOTIFICATION_ERROR)


# -- metadata -----------------------------------------------------------------

_TAG_SETTERS = (
    ("mediatype", "setMediaType"),
    ("title", "setTitle"),
    ("tvshowtitle", "setTvShowTitle"),
    ("plot", "setPlot"),
    ("duration", "setDuration"),
    ("premiered", "setPremiered"),
    ("dateadded", "setDateAdded"),
    ("mpaa", "setMpaa"),
    ("year", "setYear"),
    ("episode", "setEpisode"),
    ("trailer", "setTrailer"),
    ("season", "setSeason"),
)

_TAG_LIST_SETTERS = (
    ("genre", "setGenres"),
    ("studio", "setStudios"),
)


def set_video_info(listitem, info):
    """Populate video metadata through the InfoTag API (Kodi 20+)."""
    tag = listitem.getVideoInfoTag()
    for key, setter in _TAG_SETTERS:
        value = info.get(key)
        if value is not None:
            getattr(tag, setter)(value)
    for key, setter in _TAG_LIST_SETTERS:
        values = info.get(key)
        if values:
            getattr(tag, setter)(list(values))
