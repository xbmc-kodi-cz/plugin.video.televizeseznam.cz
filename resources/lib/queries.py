# -*- coding: utf-8 -*-
"""GraphQL documents for the api.stream.cz endpoint.

Fragments are kept as separate constants and composed into the queries that
need them, so a schema change is fixed in exactly one place.
"""

F_IMAGE = "fragment F_Image on Image{usage url}"

# Two episodes, because a film is a show holding the film and usually its
# trailer, in either order. Their names tell them apart, and the runtime and
# the playable urls live down there.
F_TAG = (
    "fragment F_Tag on Tag{id name category urlName perex ageRestriction"
    " originServiceTag{id name urlName}"
    " images{...F_Image}"
    " allEpisodesConnection(first:2){edges{node{name urlName duration}}}}"
)

# Deliberately without allParentTags: resolving the parent tags of twenty
# episodes costs the server about half a second, which tripled the time of
# every single listing (0.26s -> 0.78s measured). Genres are fetched only for
# the episode actually being played, in EPISODE_DETAIL below.
F_EPISODE = (
    "fragment F_Episode on Episode{id name namePrefix perex duration urlName views"
    " ageRestriction publishTime{timestamp} images{...F_Image}"
    " originTag{id name urlName category}"
    " originServiceTag{id name urlName}}"
)

_PAGE_INFO = "totalCount pageInfo{hasNextPage endCursor}"


def _doc(body, *fragments):
    return body + "".join(fragments)


# -- navigation ---------------------------------------------------------------

TV_MENU = "{tvMenu{tvMenuItemsConnection{edges{node{id name main}}}}}"

# The three episodes are there for their originTag: an editorial row like
# "Lajna 1" names no channel, so the only way to describe and illustrate it
# is to notice that all its episodes come from one show and borrow that
# show's own logo and synopsis - the same pair its detail screen shows.
MENU_ITEM = _doc(
    "query MenuItem($id:ID!){tvMenuItem(id:$id){id name"
    " tvSubmenusConnection{edges{node{id name representation"
    " episodesConnection(first:3){totalCount"
    " edges{node{originTag{id name perex images{...F_Image}}}}}"
    " tagsConnection{totalCount}}}}}}",
    F_IMAGE,
)

# -- submenu content ----------------------------------------------------------

SUBMENU_EPISODES = _doc(
    "query SubmenuEpisodes($id:ID!,$first:Int,$after:String){"
    "tvSubmenu(id:$id){id name"
    " episodesConnection(first:$first,after:$after){" + _PAGE_INFO +
    " edges{node{...F_Episode}}}}}",
    F_EPISODE, F_IMAGE,
)

SUBMENU_TAGS = _doc(
    "query SubmenuTags($id:ID!,$first:Int,$after:String){"
    "tvSubmenu(id:$id){id name"
    " tagsConnection(first:$first,after:$after){" + _PAGE_INFO +
    " edges{node{...F_Tag}}}}}",
    F_TAG, F_IMAGE,
)

# -- tag browsing -------------------------------------------------------------

# One round trip that answers "does this tag hold sub-tags or episodes?" and
# already carries the first page of whichever it turns out to be.
TAG_PROBE = _doc(
    "query TagProbe($id:ID,$first:Int){"
    "tag(id:$id){id name category perex images{...F_Image}"
    " directTagsConnection(first:$first){" + _PAGE_INFO +
    " edges{node{...F_Tag}}}"
    " allEpisodesConnection(first:$first){" + _PAGE_INFO +
    " edges{node{...F_Episode}}}}}",
    F_TAG, F_EPISODE, F_IMAGE,
)

TAG_EPISODES = _doc(
    "query TagEpisodes($id:ID,$first:Int,$after:String){"
    "tag(id:$id){id name category"
    " allEpisodesConnection(first:$first,after:$after){" + _PAGE_INFO +
    " edges{node{...F_Episode}}}}}",
    F_EPISODE, F_IMAGE,
)

TAG_CHILDREN = _doc(
    "query TagChildren($id:ID,$first:Int,$after:String){"
    "tag(id:$id){id name category"
    " directTagsConnection(first:$first,after:$after){" + _PAGE_INFO +
    " edges{node{...F_Tag}}}}}",
    F_TAG, F_IMAGE,
)

# A menu row is named after a channel or after a service - "Stream originals"
# is a service, which is why indexing channels alone left the one row that
# matters most without a logo. Both page at 100, about 700 together.
ROW_TAGS = _doc(
    "query RowTags($first:Int,$after:String){"
    "allTags(categories:[channel,service],first:$first,after:$after){"
    "pageInfo{hasNextPage endCursor}"
    " edges{node{id name perex images{...F_Image}}}}}",
    F_IMAGE,
)

# Playlists are a third collection a row can be named after, and the only
# source for rows like "Sci-fi filmy" or "Fantasy filmy". It is slow - five
# to seven seconds - which is why it is fetched once and kept for a week.
PLAYLISTS = _doc(
    "query Playlists($limit:Int,$offset:Int){"
    "playlists(limit:$limit,offset:$offset){"
    "id name perex images{...F_Image}}}",
    F_IMAGE,
)

RECOMMENDED = _doc(
    "query Recommended($urlName:String,$limit:Int){"
    "episode(urlName:$urlName){recommended(limit:$limit){...F_Episode}}}",
    F_EPISODE, F_IMAGE,
)

SIMILAR_TAGS = _doc(
    "query Similar($urlName:String,$limit:Int){"
    "tags(listing:similar,category:[show],urlName:$urlName,limit:$limit){...F_Tag}}",
    F_TAG, F_IMAGE,
)

# -- search -------------------------------------------------------------------

# `search` supersedes the older searchTag/searchEpisode pair and is the only
# variant that accepts the ordering and filter arguments the website exposes.
SEARCH = _doc(
    "query Search($query:String!,$order:SearchOrderEnum,"
    "$published:SearchPublishedEnum,$duration:SearchDurationEnum){"
    "search(query:$query,order:$order,published:$published,duration:$duration){"
    " topTag{...F_Tag} tags{...F_Tag} episodes{...F_Episode}}}",
    F_TAG, F_EPISODE, F_IMAGE,
)

# -- playback -----------------------------------------------------------------

EPISODE_DETAIL = _doc(
    "query Episode($urlName:String){episode(urlName:$urlName){"
    "id name namePrefix perex duration urlName views ageRestriction spl"
    " publishTime{timestamp} images{...F_Image}"
    " originTag{id name urlName category}"
    " originServiceTag{id name urlName}"
    " allParentTags(category:[channel]){name}}}",
    F_IMAGE,
)
