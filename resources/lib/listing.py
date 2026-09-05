# -*- coding: utf-8 -*-
"""Turning Stream API nodes into Kodi list items."""

import html
import re
from datetime import datetime, timezone

import xbmcgui

from . import kodi

_HTML_TAG = re.compile(r"<[^>]+>")
# Kodi's bundled font carries no emoji, so every one of them draws as an
# empty box. They sit above the Basic Multilingual Plane, plus a few symbol
# blocks inside it; dashes, ellipses and Czech quotes live below those and
# are left alone.
_UNRENDERABLE = re.compile(
    "[\U00010000-\U0010FFFF←-⇿⬀-⯿☀-➿️]"
)
_HARD_SPACE = re.compile("[   ]")
_RUN_OF_SPACES = re.compile(r"[ \t]{2,}")


def clean_text(text):
    """Make a string from the API safe to show.

    Descriptions arrive with leftover markup and emoji, both of which Kodi
    renders as noise rather than text.
    """
    if not text:
        return ""
    text = html.unescape(text)
    text = _HTML_TAG.sub("", text)
    text = _UNRENDERABLE.sub("", text)
    text = _HARD_SPACE.sub(" ", text)
    return _RUN_OF_SPACES.sub(" ", text).strip()


# Image usages the API exposes, in the order we prefer them per art type.
_ART_SOURCES = {
    "poster": ("poster", "square", "top10"),
    "thumb": ("desktop", "header", "poster", "square"),
    "fanart": ("header", "desktop"),
}


def _absolute(url):
    """Make an image URL loadable.

    The API mixes three forms in the same response: absolute, protocol
    relative ("//host/...") and bare hosts. Prefixing a protocol-relative one
    with "https://" produced "https:////host/..." - four slashes, which Kodi
    quietly fails to load, leaving the item with no picture at all.
    """
    if url.startswith("//"):
        return "https:" + url
    if "://" in url:
        return url
    return "https://" + url


def _pick(images, usages):
    if not images:
        return None
    by_usage = {image.get("usage"): image.get("url") for image in images}
    for usage in usages:
        url = by_usage.get(usage)
        if url:
            return _absolute(url)
    return None


def art(images, *kinds):
    """Build a Kodi art dict, skipping art types the node has no image for.

    The previous implementation indexed the filtered list directly and raised
    IndexError for every node without a poster or square image.
    """
    result = {}
    for kind in kinds:
        url = _pick(images, _ART_SOURCES[kind])
        if url:
            result[kind] = url
    if "thumb" in result:
        result.setdefault("icon", result["thumb"])
    result.setdefault("icon", "DefaultVideo.png")
    return result


def tag_art(images):
    """Art for a show, channel or playlist.

    The square logo fills both the list thumbnail and the poster, so the row
    and the info panel never show two different pictures of the same thing.
    The wide header image is only used behind them, as fanart - putting it in
    the thumbnail is what made list rows look squashed.
    """
    result = art(images, "poster", "fanart")
    portrait = result.get("poster")
    if portrait:
        result["thumb"] = portrait
        result["icon"] = portrait
    else:
        result.update(art(images, "thumb"))
    return result


def _timestamp(node):
    publish = node.get("publishTime") or {}
    return publish.get("timestamp")


def _dates(node):
    stamp = _timestamp(node)
    if not stamp:
        return {}
    try:
        moment = datetime.fromtimestamp(stamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return {}
    return {
        "premiered": moment.strftime("%Y-%m-%d"),
        "dateadded": moment.strftime("%Y-%m-%d %H:%M:%S"),
        "year": moment.year,
    }


def _thousands(number):
    """1234567 -> '1 234 567', the Czech grouping."""
    return "{0:,}".format(number).replace(",", " ")


def _plot(node):
    """The synopsis, with the view count appended.

    Kodi has no field for view counts, and the info dialog is the only place
    with room for it.
    """
    plot = clean_text(node.get("perex"))
    views = node.get("views")
    if not views:
        return plot
    line = "{0}: {1}".format(kodi.L(30015), _thousands(views))
    return "{0}\n\n{1}".format(plot, line) if plot else line


def _genres(node):
    return [
        tag["name"].strip()
        for tag in (node.get("allParentTags") or [])
        if tag.get("name")
    ]


# The API has no field saying what kind of thing a video is - mediaType only
# distinguishes video from audio. Its channel tags do though: everything
# feature-length sits under "Filmy", while series carry "Seriály" and the rest
# "Magazín", "Pohádky" and so on.
_FILM_CHANNEL = "filmy"


def _is_film(node):
    """Whether this is a feature film rather than an episode of something.

    Channel tags answer it outright, but resolving them costs the server half
    a second per listing, so they are only fetched for the episode being
    played. Everywhere else the tell is that a film is a show with a single
    episode carrying the show's own name.
    """
    genres = _genres(node)
    if genres:
        return any(genre.casefold() == _FILM_CHANNEL for genre in genres)

    show = clean_text((node.get("originTag") or {}).get("name"))
    name = clean_text(node.get("name"))
    return bool(show) and show.casefold() == name.casefold()


def _studio(node):
    name = (node.get("originServiceTag") or {}).get("name")
    return [name] if name else []


def _mpaa(node):
    """Stream states a minimum age; Kodi shows it as the certification."""
    age = node.get("ageRestriction")
    return "{0}+".format(age) if age else None


def _episode_number(node):
    """'644.' -> 644. Stream keeps the episode number in namePrefix."""
    prefix = (node.get("namePrefix") or "").strip().rstrip(".")
    return int(prefix) if prefix.isdigit() else None


def _episode_title(node):
    prefix = clean_text(node.get("namePrefix"))
    name = clean_text(node.get("name"))
    return "{0} {1}".format(prefix, name).strip() if prefix else name


# The service tag every piece of Stream's own production hangs off.
ORIGINALS_URL_NAME = "stream"
ORIGINALS_BADGE = "Stream originals"


def is_original(node):
    return (node.get("originServiceTag") or {}).get("urlName") == ORIGINALS_URL_NAME


def _highlight(text):
    return "[COLOR blue]{0}[/COLOR]".format(text)


def _decorate(node, parts, badge=True):
    """Build the display string, badging Stream's own production.

    Kodi renders the InfoTag title rather than the list item label for items
    that carry video metadata, so this one string has to go into both - a show
    name kept only in the label would never appear on screen.

    Only the leading part is coloured, so the badge and a show name never end
    up fighting each other for the same blue.
    """
    parts = [part for part in parts if part]
    if badge and is_original(node):
        parts.insert(0, ORIGINALS_BADGE)

    # A film is a one-episode show, so its show name and episode title are the
    # same string; repeating it would just read as "Lola · Lola".
    seen = set()
    unique = []
    for part in parts:
        key = part.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(part)

    if len(unique) < 2:
        return unique[0] if unique else ""
    return " · ".join([_highlight(unique[0])] + unique[1:])


def episode_listitem(node, with_show=False, badge=True):
    """A playable list item for an Episode node.

    ``with_show`` prefixes the label with the originating show, which is what
    makes a mixed listing (search results, "new videos") readable.
    """
    title = _episode_title(node)
    show = clean_text((node.get("originTag") or {}).get("name"))
    display = _decorate(
        node, [show, title] if with_show and show else [title], badge=badge
    )

    film = _is_film(node)

    listitem = xbmcgui.ListItem(display)
    info = {
        "mediatype": "movie" if film else "episode",
        "title": display,
        "plot": _plot(node),
        "duration": node.get("duration"),
        "genre": _genres(node),
        "studio": _studio(node),
        "mpaa": _mpaa(node),
    }
    if not film:
        info["episode"] = _episode_number(node)
        if show:
            # Kept unmarked so skins that show it on its own stay clean.
            info["tvshowtitle"] = show
    info.update(_dates(node))
    kodi.set_video_info(listitem, info)
    listitem.setArt(art(node.get("images"), "thumb", "poster", "fanart"))
    listitem.setProperty("IsPlayable", "true")
    return listitem


def _episodes(node):
    edges = (node.get("allEpisodesConnection") or {}).get("edges") or []
    return [edge.get("node") or {} for edge in edges]


def film_episode(node):
    """The episode a film consists of, or None for a show with real episodes.

    A film is a show whose first episode carries the show's own name, and the
    runtime and the url that plays it live down there. Counting episodes does
    not work: most films ship a trailer as a second one, so "Lola" and "Dokud
    se tanci" both hold two. A series names its episodes individually.
    """
    name = clean_text(node.get("name")).casefold()
    if not name:
        return None

    # Not by position: "Zakazane uvolneni" lists its trailer first and the
    # film second, so the name is the only thing to go by.
    for episode in _episodes(node):
        if clean_text(episode.get("name")).casefold() == name:
            return episode
    return None


# A trailer runs a couple of minutes against a feature's ninety, so anything
# near the film's own length is a second part, not an extra.
_TRAILER_SHARE = 0.25


def trailer_episode(node):
    """The trailer shipped alongside a film, if there is one.

    Whichever of the film's episodes is not the film itself and runs a small
    fraction of its length. The length check keeps a two-part film from
    having its own second half attached as an extra.
    """
    film = film_episode(node)
    feature = film.get("duration") or 0 if film else 0
    if not feature:
        return None

    for episode in _episodes(node):
        if episode.get("urlName") == film.get("urlName"):
            continue
        length = episode.get("duration") or 0
        if length and length <= feature * _TRAILER_SHARE:
            return episode
    return None


def tag_listitem(node, badge=True, trailer=None):
    """A list item for a Tag node (show, channel, film or curated list).

    ``trailer`` is the url that plays the film's trailer; building it needs
    the plugin's routes, which live a layer up.
    """
    name = clean_text(node.get("name"))
    display = _decorate(node, [name], badge=badge)
    episode = film_episode(node)

    listitem = xbmcgui.ListItem(display)
    info = {
        "mediatype": "movie" if episode else "tvshow",
        "title": display,
        "plot": clean_text(node.get("perex")),
        "studio": _studio(node),
        "mpaa": _mpaa(node),
    }
    if episode:
        # A film's runtime, which the show itself does not carry.
        info["duration"] = episode.get("duration")
        if trailer:
            info["trailer"] = trailer
    kodi.set_video_info(listitem, info)

    listitem.setArt(tag_art(node.get("images")))
    if episode:
        listitem.setProperty("IsPlayable", "true")
    return listitem


def folder_listitem(label, icon=None, plot=None, artwork=None, mediatype=None):
    """A folder entry. ``artwork`` wins over ``icon`` where both cover a slot.

    ``icon`` is one of Kodi's own skin textures and goes in the icon slot
    only. Copying it into thumb or poster puts it behind the item as
    background artwork too, where it does not belong.

    ``mediatype`` says what the folder holds. Skins read it: Estuary draws
    its generic folder overlay over every folder whose media type is empty,
    which is why rows leading to shows wore a folder glyph instead of the
    marker a show gets in the library.
    """
    listitem = xbmcgui.ListItem(label)
    info = {"title": label, "plot": plot, "mediatype": mediatype}
    if plot or mediatype:
        kodi.set_video_info(listitem, info)

    art_map = dict(artwork or {})
    if icon:
        art_map.setdefault("icon", icon)
    if art_map:
        listitem.setArt(art_map)
    return listitem


def next_page_listitem():
    return folder_listitem(kodi.L(30001), "DefaultInProgressShows.png")
