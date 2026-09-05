# -*- coding: utf-8 -*-
"""Route definitions for the Stream video addon."""

import functools
import hashlib
import sys
import time
import traceback

import routing
import xbmc
import xbmcgui
import xbmcplugin

from . import api, cache, history, kodi, listing, queries

plugin = routing.Plugin()

_client = None


def client():
    global _client
    if _client is None:
        _client = api.StreamApi()
    return _client


def arg(name, default=None):
    """Read a query-string argument.

    routing only passes path placeholders to the view function; everything
    else lands in ``plugin.args`` as a list.
    """
    values = plugin.args.get(name)
    return values[0] if values else default


def guarded(func):
    """Never let an exception leave a directory half-built.

    Without this a network blip or a schema change shows up as "Script failed"
    over an empty window, and the missing endOfDirectory leaves Kodi spinning.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except api.ApiError as exc:
            kodi.error(str(exc))
        except Exception:
            kodi.log(traceback.format_exc(), xbmc.LOGERROR)
            kodi.error(kodi.L(30010))
        xbmcplugin.endOfDirectory(plugin.handle, succeeded=False)

    return wrapper


def finish(items, content=None, title=None, sort_methods=(), cache_to_disc=True):
    if content:
        xbmcplugin.setContent(plugin.handle, content)
    if title:
        xbmcplugin.setPluginCategory(plugin.handle, title)
    for method in sort_methods:
        xbmcplugin.addSortMethod(plugin.handle, method)
    xbmcplugin.addDirectoryItems(plugin.handle, items, len(items))
    xbmcplugin.endOfDirectory(plugin.handle, cacheToDisc=cache_to_disc)


EPISODE_SORTS = (
    xbmcplugin.SORT_METHOD_UNSORTED,
    xbmcplugin.SORT_METHOD_LABEL,
    xbmcplugin.SORT_METHOD_DATE,
    xbmcplugin.SORT_METHOD_DURATION,
)

TAG_SORTS = (
    xbmcplugin.SORT_METHOD_UNSORTED,
    xbmcplugin.SORT_METHOD_LABEL,
)


# -- shared builders ----------------------------------------------------------


def episode_context(node):
    """Context menu entries that jump from an episode to its show."""
    origin = node.get("originTag") or {}
    entries = []
    if node.get("urlName"):
        entries.append(
            (
                kodi.L(30019),
                "Container.Update({0})".format(
                    plugin.url_for(recommended, url_name=node["urlName"])
                ),
            )
        )
    if origin.get("id"):
        entries.append(
            (
                kodi.L(30006),
                "Container.Update({0})".format(
                    plugin.url_for(browse_tag, tag_id=origin["id"])
                ),
            )
        )
    if origin.get("urlName"):
        entries.append(
            (
                kodi.L(30007),
                "Container.Update({0})".format(
                    plugin.url_for(similar_shows, url_name=origin["urlName"])
                ),
            )
        )
    return entries


def tag_context(node):
    if not node.get("urlName"):
        return []
    return [
        (
            kodi.L(30007),
            "Container.Update({0})".format(
                plugin.url_for(similar_shows, url_name=node["urlName"])
            ),
        )
    ]


def badge_worth_showing(nodes):
    """Whether the "Stream originals" badge tells the viewer anything here.

    Inside the Stream originals section every row carries it, which only
    makes a list of shows read like a list of episodes.
    """
    return not all(listing.is_original(node) for node in nodes)


def show_worth_showing(nodes):
    """Whether naming the show on every row adds anything.

    Inside a single show every episode repeats its name, which reads as
    noise; in a mixed listing that name is what makes the row make sense.
    Deciding from the rows themselves keeps a channel or a curated list -
    where the episodes come from different shows - correct too.
    """
    shows = {(node.get("originTag") or {}).get("id") for node in nodes}
    return len(shows) > 1


def episode_items(nodes, with_show=True, badge=True):
    name_show = with_show and show_worth_showing(nodes)
    show_badge = badge and badge_worth_showing(nodes)
    items = []
    for node in nodes:
        listitem = listing.episode_listitem(
            node, with_show=name_show, badge=show_badge
        )
        listitem.addContextMenuItems(episode_context(node))
        items.append(
            (plugin.url_for(play, url_name=node["urlName"]), listitem, False)
        )
    return items


def tag_items(nodes):
    badge = badge_worth_showing(nodes)
    items = []
    for node in nodes:
        trailer = listing.trailer_episode(node)
        listitem = listing.tag_listitem(
            node,
            badge=badge,
            trailer=(
                plugin.url_for(play, url_name=trailer["urlName"])
                if trailer and trailer.get("urlName")
                else None
            ),
        )
        listitem.addContextMenuItems(tag_context(node))

        # A film plays straight from the list rather than opening a folder
        # that holds the film and its trailer.
        episode = listing.film_episode(node)
        if episode and episode.get("urlName"):
            items.append(
                (
                    plugin.url_for(play, url_name=episode["urlName"]),
                    listitem,
                    False,
                )
            )
            continue

        items.append((plugin.url_for(browse_tag, tag_id=node["id"]), listitem, True))
    return items


def paged(connection, url_builder):
    """Append a "next page" entry when the connection has one."""
    info = connection.get("pageInfo") or {}
    if not info.get("hasNextPage") or not info.get("endCursor"):
        return []
    return [(url_builder(info["endCursor"]), listing.next_page_listitem(), True)]


def nodes_of(connection):
    return [edge["node"] for edge in (connection.get("edges") or [])]


# Editors rebuild the navigation roughly once a day, so re-fetching it on
# every step into a menu bought nothing but latency.
MENU_TTL = 6 * 3600


def cached_query(key, document, variables=None, ttl=MENU_TTL):
    """Run a GraphQL document, reusing a recent response when there is one.

    The stored entry is keyed on the document as well as on the caller's key.
    A query that gains a field would otherwise keep reading back a response
    saved before the field existed, for as long as the entry lives - which is
    exactly what left the menu rows with no logo and no synopsis after
    ``perex`` was added to them.
    """
    fingerprint = hashlib.sha1(document.encode("utf-8")).hexdigest()[:8]
    key = "{0}@{1}".format(key, fingerprint)

    data = cache.get(key, ttl)
    if data is None:
        data = client().query(document, variables)
        cache.put(key, data)
    return data


# Descriptions are editorial copy that barely changes and the queries behind
# them are slow, so the whole index is kept for a week.
ROW_INDEX_TTL = 7 * 24 * 3600

# Kodi gives up on a directory that takes too long: building the whole index
# in one go cost about thirteen seconds and the log showed it abandoning the
# menu. So each visit spends at most a few seconds on it and remembers where
# it stopped; a handful of screens later the index is complete.
_INDEX_BUDGET = 3.0
_TAG_PAGE = 100
_PLAYLIST_PAGE = 200


def _merge_rows(index, nodes):
    """Add nodes to the index, leaving names already claimed alone."""
    for node in nodes:
        name = listing.clean_text(node.get("name"))
        if not name:
            continue
        index.setdefault(
            name.casefold(),
            {
                "id": node.get("id"),
                "name": name,
                "plot": listing.clean_text(node.get("perex")),
                "art": listing.tag_art(node.get("images")),
            },
        )


def row_index():
    """Map a menu row's name to its description, logo and source tag.

    A row carries no link to whatever it was built from, and its urlName
    cannot be derived from its name - "Legendarni auto-moto porad" lives at
    "autosalon-tv-prima" - so matching the exact name is the only join there
    is. All three collections a row can be named after are indexed: channels,
    services and playlists. The last is slow on its own, which is the price
    of the rows only it covers.

    Built a few seconds at a time. Each visit picks up where the last one
    stopped and stores its progress, so no single screen waits for the whole
    thing and the index fills in over the first handful of screens. Once it
    is complete it is kept for a week.

    This is a bonus on top of the row, so a failure part way through keeps
    whatever was collected before it.
    """
    state = cache.get("rowtags", ROW_INDEX_TTL) or {}
    if state.get("stage") == "done":
        return state.get("index") or {}

    index = state.get("index") or {}
    stage = state.get("stage") or "tags"
    cursor = state.get("cursor")
    offset = state.get("offset") or 0
    deadline = time.monotonic() + _INDEX_BUDGET

    try:
        while stage != "done" and time.monotonic() < deadline:
            if stage == "tags":
                connection = client().query(
                    queries.ROW_TAGS, {"first": _TAG_PAGE, "after": cursor}
                )["allTags"]
                _merge_rows(index, nodes_of(connection))
                info = connection.get("pageInfo") or {}
                cursor = info.get("endCursor")
                if not info.get("hasNextPage"):
                    # Playlists come last so a channel or service keeps a
                    # name the two of them share.
                    stage, cursor = "playlists", None
            else:
                nodes = (
                    client().query(
                        queries.PLAYLISTS,
                        {"limit": _PLAYLIST_PAGE, "offset": offset},
                    ).get("playlists")
                    or []
                )
                _merge_rows(index, nodes)
                offset += _PLAYLIST_PAGE
                if len(nodes) < _PLAYLIST_PAGE:
                    stage = "done"
    except api.ApiError as exc:
        kodi.log("Row index incomplete: {0}".format(exc))

    cache.put(
        "rowtags",
        {"index": index, "stage": stage, "cursor": cursor, "offset": offset},
    )
    return index


# -- root ---------------------------------------------------------------------


def submenu_target(submenu):
    """``(kind, count)`` for a menu row.

    Exactly one of the two connections is populated per row, and the count
    only decides whether the row is worth showing at all.
    """
    episodes = (submenu.get("episodesConnection") or {}).get("totalCount")
    if episodes is not None:
        return "episodes", episodes
    return "tags", (submenu.get("tagsConnection") or {}).get("totalCount")


def _one_edit_apart(first, second):
    """Whether two names differ by a single letter.

    Stream's own menu labels sometimes disagree with the tag they point at by
    one letter of Czech agreement - the Filmy menu says "Ceska filmy" where
    the channel, and the website, say "Ceske filmy".

    A digit is never such a variant, it numbers a part: "Lajna 1", "Lajna 2"
    and "Lajna 3" are three separate rows, and accepting a digit difference
    collapsed all three onto the one playlist that happened to be indexed.
    """
    if abs(len(first) - len(second)) > 1:
        return False
    if len(first) > len(second):
        first, second = second, first

    for index, (left, right) in enumerate(zip(first, second)):
        if left == right:
            continue
        if left.isdigit() or right.isdigit():
            return False
        if len(first) == len(second):
            return first[index + 1:] == second[index + 1:]
        return first[index:] == second[index + 1:]

    # Equal as far as the shorter name goes; the one extra character at the
    # end counts only under the same rule.
    if len(first) != len(second):
        return not second[-1].isdigit()
    return True


def row_lookup(index, name):
    """Find a row's tag, tolerating a one-letter difference in the name.

    A row carries no reference to its tag, so its name is the only thing to
    search on. A near match is accepted only when exactly one candidate is
    that close, so an ambiguous name is left alone rather than given someone
    else's logo.
    """
    key = name.casefold()
    entry = index.get(key)
    if entry is not None:
        return entry

    near = [value for other, value in index.items() if _one_edit_apart(key, other)]
    return near[0] if len(near) == 1 else {}


def usable_art(artwork):
    """The artwork, or None when it holds no actual picture.

    tag_art always returns a default icon, so a tag with an empty image list
    still yields a non-empty dict. Treating that as artwork hid the fallbacks
    below it - the "Lajna 2" playlist has no images at all, and matching it
    was enough to lose the logo the row would otherwise have got.
    """
    if not artwork:
        return None
    return artwork if artwork.get("poster") or artwork.get("thumb") else None


def row_show(submenu):
    """The show a row is about, when it is about just one.

    Editorial rows - "Lajna 1", "Dejte si Ctvrtnicka v Autobazaru" - name no
    channel, so the index cannot place them, and almost every row under
    Serialy is one of these. Their episodes all come from the same show, and
    that show carries the logo and the synopsis the row should be wearing.
    Rows drawn from several shows are left alone: picking one of them would
    be arbitrary.
    """
    episodes = nodes_of(submenu.get("episodesConnection") or {})
    shows = {(episode.get("originTag") or {}).get("id") for episode in episodes}
    if len(shows) != 1 or None in shows:
        return {}

    return (episodes[0].get("originTag") or {})


def category_item(submenu, rows, icon, seen=None):
    """A menu row dressed with its channel's name, logo and description.

    A row names no tag of its own, so matching its name against the channel
    index is the only way to reach the artwork the website shows. When that
    finds one the row browses the channel itself rather than its raw episode
    list, which mixes films with their trailers. Returns None for an empty
    row, which is not worth a line on screen.
    """
    kind, count = submenu_target(submenu)
    if not count:
        return None

    name = listing.clean_text(submenu["name"])
    # The API repeats itself: the main menu lists "Auto-moto porady" twice.
    if seen is not None:
        if name.casefold() in seen:
            return None
        seen.add(name.casefold())

    row = row_lookup(rows, name)
    show = row_show(submenu)

    # The show's own logo and synopsis come first, so a row about one show
    # looks the same here as it does on that show's own screen. The index
    # covers the rest: rows that lead to a grid of shows rather than to the
    # episodes of a single one.
    artwork = usable_art(listing.tag_art(show.get("images"))) or usable_art(
        row.get("art")
    )
    plot = listing.clean_text(show.get("perex")) or row.get("plot")

    listitem = listing.folder_listitem(
        # The TV menu label is Stream's own and is not always the name of the
        # thing it points at, so a matched channel wins. Its editorial title
        # is kept when only the show behind it could be identified - the row
        # is about that show, but the wording is the point of the row.
        row.get("name") or name,
        icon,
        plot=plot,
        artwork=artwork,
        # Every one of these rows leads to shows, and saying so is what stops
        # the skin drawing its own folder glyph over the row.
        mediatype="xtvshow",
    )

    # Only a row that would otherwise list raw episodes is worth redirecting
    # to its channel: that list mixes films with their trailers, while the
    # channel holds them as shows. A row that already offers tags is the
    # better of the two - the channel's own children are a mixed bag of
    # sub-channels, itself included.
    target = row.get("id")
    url = (
        plugin.url_for(browse_tag, tag_id=target)
        if target and kind == "episodes"
        else plugin.url_for(submenu_view, submenu_id=submenu["id"], kind=kind)
    )
    return url, listitem, True


@plugin.route("/")
@guarded
def root():
    """Mirror the category bar of stream.cz.

    The website shows one row of categories, but the API splits them across
    two levels: Pohadky, Filmy, Serialy and Zabava are top-level menu items,
    while Stream originals, Premiery, Zpravy, Magazin and the rest are grid
    rows buried inside the main menu. Both are pulled up here, otherwise
    Stream originals - the thing the service is named for - is two clicks
    away and invisible from the root.
    """
    data = cached_query("tvmenu", queries.TV_MENU)
    menu = nodes_of(data["tvMenu"]["tvMenuItemsConnection"])

    main = next((node for node in menu if node.get("main")), None)
    # The API's own search entry is a UI descriptor, not a browsable list.
    sections = [
        node
        for node in menu
        if not node.get("main") and node["name"].strip().casefold() != "hledat"
    ]
    section_names = {node["name"].strip().casefold() for node in sections}

    rows = row_index()

    # Search leads, because it is the one entry reached by typing rather than
    # by browsing, and a dozen categories below it is a long way on a remote.
    items = [
        (
            plugin.url_for(search),
            listing.folder_listitem(kodi.L(30005), "DefaultAddonsSearch.png"),
            True,
        )
    ]

    if main:
        items.append(
            (
                plugin.url_for(menu_item, menu_id=main["id"]),
                # The API calls this "Hlavni nabidka", which reads like a
                # settings screen; it is the homepage of the service.
                listing.folder_listitem(kodi.L(30023), "DefaultVideoPlaylists.png"),
                True,
            )
        )
        detail = cached_query(
            "menu:" + main["id"], queries.MENU_ITEM, {"id": main["id"]}
        )
        submenus = (detail.get("tvMenuItem") or {}).get("tvSubmenusConnection") or {}
        seen = set()
        for submenu in nodes_of(submenus):
            # Only the grid rows are categories; carousels and promos are
            # editorial and stay inside the main menu.
            if submenu.get("representation") != "simple_grid":
                continue
            if listing.clean_text(submenu["name"]).casefold() in section_names:
                # Also a top-level item, which carries more than a flat grid.
                continue
            item = category_item(submenu, rows, "DefaultTVShows.png", seen)
            if item:
                items.append(item)

    for node in sections:
        # Pohadky, Filmy, Serialy and Zabava are channels as well as menu
        # items, so they carry the same logo the website shows. They still
        # open the menu item rather than the channel, because the menu has
        # the editorial rows the bare channel does not.
        name = listing.clean_text(node["name"])
        row = row_lookup(rows, name)
        items.append(
            (
                plugin.url_for(menu_item, menu_id=node["id"]),
                listing.folder_listitem(
                    row.get("name") or name,
                    "DefaultTVShows.png",
                    plot=row.get("plot"),
                    artwork=usable_art(row.get("art")),
                ),
                True,
            )
        )

    # Kodi caches a directory on disc independently of our own cache, which
    # keeps serving an old menu after the addon changes. Menus are small and
    # their API responses are cached anyway, so let them rebuild every time.
    # No setContent here on purpose: a video content type puts Kodi into a
    # library view that draws poster placeholders instead of ListItem.Icon,
    # so a navigation menu would lose its icons.
    finish(items, cache_to_disc=False)


# -- menus --------------------------------------------------------------------

# A "search" row describes a UI control rather than a list of content. Every
# other representation ("single", "carousel", "simple_grid") only says how the
# website draws the row - they all hold real videos.
_SKIPPED_REPRESENTATIONS = {"search"}


@plugin.route("/menu/<menu_id>")
@guarded
def menu_item(menu_id):
    """The rows that stream.cz shows under one top-level menu entry."""
    data = cached_query("menu:" + menu_id, queries.MENU_ITEM, {"id": menu_id})
    node = data.get("tvMenuItem")
    if not node:
        raise api.ApiError(kodi.L(30012))

    rows = row_index()
    seen = set()

    # The main menu's grid rows are the categories, and root() already lists
    # them; showing them again in here would just duplicate the root.
    main = next(
        (
            item
            for item in nodes_of(
                cached_query("tvmenu", queries.TV_MENU)["tvMenu"][
                    "tvMenuItemsConnection"
                ]
            )
            if item.get("main")
        ),
        None,
    )
    drop_categories = bool(main) and main["id"] == menu_id

    items = []
    for submenu in nodes_of(node["tvSubmenusConnection"]):
        if submenu.get("representation") in _SKIPPED_REPRESENTATIONS:
            continue
        if drop_categories and submenu.get("representation") == "simple_grid":
            continue

        item = category_item(submenu, rows, "DefaultVideoPlaylists.png", seen)
        if item:
            items.append(item)

    # These rows carry the logo of the channel or the show they are about, so
    # they earn the same poster views as the listings they lead to. The root
    # stays without a content type: Search and Featured have no artwork, and
    # a library view would draw placeholders for them.
    finish(
        items,
        content="tvshows",
        title=node["name"].strip(),
        cache_to_disc=False,
    )


@plugin.route("/submenu/<submenu_id>")
@guarded
def submenu_view(submenu_id):
    kind = arg("kind", "episodes")
    page = arg("page")
    variables = {"id": submenu_id, "first": kodi.page_size(), "after": page}

    if kind == "tags":
        data = client().query(queries.SUBMENU_TAGS, variables)
        node = data["tvSubmenu"]
        connection = node["tagsConnection"]
        items = tag_items(nodes_of(connection))
        # "tvshows" is what puts Kodi's poster views on offer - the layout
        # with the artwork beside the description. The list mixes films with
        # series, but the views that matter here are the same for both.
        content, sorts = "tvshows", TAG_SORTS
    else:
        data = client().query(queries.SUBMENU_EPISODES, variables)
        node = data["tvSubmenu"]
        connection = node["episodesConnection"]
        items = episode_items(nodes_of(connection))
        content, sorts = "episodes", EPISODE_SORTS

    items += paged(
        connection,
        lambda cursor: plugin.url_for(
            submenu_view, submenu_id=submenu_id, kind=kind, page=cursor
        ),
    )
    finish(items, content=content, title=node["name"].strip(), sort_methods=sorts)


# -- tags ---------------------------------------------------------------------


@plugin.route("/tag/<tag_id>")
@guarded
def browse_tag(tag_id):
    """Browse any tag: a show, a season, a channel or a curated list.

    A single probe decides whether the tag holds sub-tags (a show with
    seasons, a channel of shows) or a flat list of episodes, so one route
    covers every shape the API returns.
    """
    kind = arg("kind")
    page = arg("page")
    size = kodi.page_size()

    if kind == "episodes":
        data = client().query(
            queries.TAG_EPISODES, {"id": tag_id, "first": size, "after": page}
        )
        node = data["tag"]
        connection = node["allEpisodesConnection"]
        items = episode_items(nodes_of(connection))
        items += paged(
            connection,
            lambda cursor: plugin.url_for(
                browse_tag, tag_id=tag_id, kind="episodes", page=cursor
            ),
        )
        finish(
            items,
            content="episodes",
            title=node["name"].strip(),
            sort_methods=EPISODE_SORTS,
        )
        return

    if kind == "shows":
        data = client().query(
            queries.TAG_CHILDREN, {"id": tag_id, "first": size, "after": page}
        )
        node = data["tag"]
        connection = node["directTagsConnection"]
        items = tag_items([n for n in nodes_of(connection) if n["id"] != tag_id])
        items += paged(
            connection,
            lambda cursor: plugin.url_for(
                browse_tag, tag_id=tag_id, kind="shows", page=cursor
            ),
        )
        finish(
            items,
            content="tvshows",
            title=node["name"].strip(),
            sort_methods=TAG_SORTS,
        )
        return

    data = client().query(queries.TAG_PROBE, {"id": tag_id, "first": size})
    node = data.get("tag")
    if not node:
        raise api.ApiError(kodi.L(30012))

    children_connection = node["directTagsConnection"]
    episodes_connection = node["allEpisodesConnection"]
    # A channel lists itself among its own children; drop it.
    children = [n for n in nodes_of(children_connection) if n["id"] != tag_id]
    episodes = nodes_of(episodes_connection)
    episode_count = episodes_connection.get("totalCount") or 0

    # Counting episodes would miss most films: they ship a trailer as a
    # second one. The tell is the first episode carrying the show's own name.
    film = listing.film_episode(node)
    if not children and film and film.get("urlName"):
        # The folder in between would hold the film and its trailer, so go
        # straight to the film. The probe already carries it, at no cost.
        xbmcplugin.endOfDirectory(plugin.handle, succeeded=False)
        xbmc.executebuiltin(
            "PlayMedia({0})".format(plugin.url_for(play, url_name=film["urlName"]))
        )
        return

    if children:
        items = []
        if episode_count:
            items.append(
                (
                    plugin.url_for(browse_tag, tag_id=tag_id, kind="episodes"),
                    listing.folder_listitem(
                        kodi.L(30013), "DefaultRecentlyAddedEpisodes.png"
                    ),
                    True,
                )
            )
        items += tag_items(children)
        items += paged(
            children_connection,
            lambda cursor: plugin.url_for(
                browse_tag, tag_id=tag_id, kind="shows", page=cursor
            ),
        )
        finish(
            items,
            content="tvshows",
            title=node["name"].strip(),
            sort_methods=TAG_SORTS,
        )
        return

    items = episode_items(episodes)
    items += paged(
        episodes_connection,
        lambda cursor: plugin.url_for(
            browse_tag, tag_id=tag_id, kind="episodes", page=cursor
        ),
    )
    finish(
        items,
        content="episodes",
        title=node["name"].strip(),
        sort_methods=EPISODE_SORTS,
    )


@plugin.route("/recommended/<url_name>")
@guarded
def recommended(url_name):
    """Videos the API suggests alongside one episode."""
    data = client().query(queries.RECOMMENDED, {"urlName": url_name, "limit": 20})
    episodes = (data.get("episode") or {}).get("recommended") or []
    if not episodes:
        kodi.notify(kodi.L(30009))
        xbmcplugin.endOfDirectory(plugin.handle, succeeded=False)
        return
    finish(
        episode_items(episodes),
        content="episodes",
        title=kodi.L(30019),
        sort_methods=EPISODE_SORTS,
        cache_to_disc=False,
    )


@plugin.route("/similar/<url_name>")
@guarded
def similar_shows(url_name):
    data = client().query(queries.SIMILAR_TAGS, {"urlName": url_name, "limit": 20})
    finish(
        tag_items(data.get("tags") or []),
        content="tvshows",
        title=kodi.L(30007),
        sort_methods=TAG_SORTS,
    )


# -- search -------------------------------------------------------------------

_SEARCH_ORDERS = (None, "NEWEST", "MOST_WATCHED", "OLDEST")


@plugin.route("/search")
@guarded
def search():
    """A new search plus the queries used before it."""
    items = [
        (
            plugin.url_for(search_run),
            listing.folder_listitem(kodi.L(30016), "DefaultAddonsSearch.png"),
            True,
        )
    ]

    queries = history.load()
    for query in queries:
        listitem = listing.folder_listitem(query, "DefaultInProgressShows.png")
        listitem.addContextMenuItems(
            [
                (
                    kodi.L(30017),
                    "RunPlugin({0})".format(
                        plugin.url_for(search_forget, query=query)
                    ),
                )
            ]
        )
        items.append((plugin.url_for(search_run, query=query), listitem, True))

    if queries:
        items.append(
            (
                plugin.url_for(search_clear),
                listing.folder_listitem(kodi.L(30018), "DefaultAddonNone.png"),
                True,
            )
        )

    finish(items, title=kodi.L(30005), cache_to_disc=False)


# Both of these change stored data and redraw the list; they render no
# directory of their own. Reaching them with Container.Update made Kodi ask
# for a listing, get none, and log "GetDirectory ... failed" every time, so
# the context menu runs them with RunPlugin instead.
@plugin.route("/search/forget")
def search_forget():
    history.remove(arg("query"))
    xbmc.executebuiltin("Container.Refresh")


@plugin.route("/search/clear")
def search_clear():
    history.clear()
    xbmc.executebuiltin("Container.Refresh")


@plugin.route("/search/run")
@guarded
def search_run():
    """Run a query and render the results in the same directory.

    Handing the results to Container.Update from here instead would leave this
    directory unfinished, which Kodi treats as a failed plugin call - the
    window just flashes and returns.
    """
    query = arg("query") or xbmcgui.Dialog().input(
        kodi.L(30005), type=xbmcgui.INPUT_ALPHANUM
    )
    if not query:
        xbmcplugin.endOfDirectory(plugin.handle, succeeded=False)
        return
    history.add(query)

    choice = kodi.setting_int("search_order", 0)
    order = _SEARCH_ORDERS[choice] if 0 <= choice < len(_SEARCH_ORDERS) else None

    data = client().query(queries.SEARCH, {"query": query, "order": order})
    result = data["search"]

    tags = list(result.get("tags") or [])
    top = result.get("topTag")
    if top and all(top["id"] != tag["id"] for tag in tags):
        tags.insert(0, top)
    episodes = result.get("episodes") or []

    if not tags and not episodes:
        kodi.notify(kodi.L(30009))
        xbmcplugin.endOfDirectory(plugin.handle, succeeded=False)
        return

    items = tag_items(tags) + episode_items(episodes)
    finish(
        items,
        content="videos",
        title="{0}: {1}".format(kodi.L(30005), query),
        cache_to_disc=False,
    )


# -- playback -----------------------------------------------------------------


@plugin.route("/play/<url_name>")
def play(url_name):
    try:
        data = client().query(queries.EPISODE_DETAIL, {"urlName": url_name})
        episode = data.get("episode")
        if not episode or not episode.get("spl"):
            raise api.ApiError(kodi.L(30014))

        playlist, base_url = client().playlist(episode["spl"])
        protocol, max_height = kodi.stream_choice()
        stream = api.select_stream(
            playlist, base_url, protocol=protocol, max_height=max_height
        )
    except api.ApiError as exc:
        kodi.error(str(exc))
        xbmcplugin.setResolvedUrl(
            plugin.handle, False, xbmcgui.ListItem(offscreen=True)
        )
        return
    except Exception:
        kodi.log(traceback.format_exc(), xbmc.LOGERROR)
        kodi.error(kodi.L(30010))
        xbmcplugin.setResolvedUrl(
            plugin.handle, False, xbmcgui.ListItem(offscreen=True)
        )
        return

    listitem = listing.episode_listitem(episode)
    listitem.setPath(stream["url"])
    listitem.setMimeType(stream["mime"])
    # We hand Kodi an exact mime type, so it can skip the probing HEAD request.
    listitem.setContentLookup(False)

    subtitles = api.subtitle_urls(playlist, base_url)
    if subtitles:
        listitem.setSubtitles(subtitles)

    xbmcplugin.setResolvedUrl(plugin.handle, True, listitem)


# -- maintenance --------------------------------------------------------------


@plugin.route("/cache/clear")
def clear_cache():
    """Invoked by the settings button, so it renders no directory."""
    try:
        cache.clear()
    except Exception:
        kodi.log(traceback.format_exc(), xbmc.LOGERROR)
        kodi.error(kodi.L(30010))
        return
    kodi.notify(kodi.L(30022))


def run():
    # routing.Plugin reads the handle once, in its constructor. With
    # reuselanguageinvoker the module stays imported between invocations, so
    # the handle and the parsed arguments have to be re-read every run.
    kodi.refresh()
    plugin.handle = (
        int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else -1
    )
    plugin.args = {}
    plugin.run()
