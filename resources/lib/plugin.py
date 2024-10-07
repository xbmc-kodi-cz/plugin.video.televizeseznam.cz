# -*- coding: utf-8 -*-
import routing
import requests
import xbmc
import xbmcplugin
import xbmcgui
import xbmcaddon
import json
from datetime import datetime

_addon = xbmcaddon.Addon()
plugin = routing.Plugin()


@plugin.route("/list_categories")
def list_categories():
    xbmcplugin.addSortMethod(plugin.handle, sortMethod=xbmcplugin.SORT_METHOD_LABEL)
    listing = []
    client = GraphQLClient()
    data = client.execute(
        """query LoadTags($limit :Int){tags(inGuide:true,limit:$limit){...NavigationCategoryFragmentOnTag}tagsCount(inGuide:true)}fragment NavigationCategoryFragmentOnTag on Tag{id,name,category,urlName}""",
        {"limit": 20},
    )

    for item in data["data"]["tags"]:
        listitem = xbmcgui.ListItem(item["name"].strip())
        listing.append(
            (plugin.url_for(list_channels, item["id"], "none"), listitem, True)
        )

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@plugin.route("/list_channels/<id>/<type>")
def list_channels(id, type):
    xbmcplugin.addSortMethod(plugin.handle, sortMethod=xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(plugin.handle, sortMethod=xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.setContent(plugin.handle, "tvshows")
    listing = []
    client = GraphQLClient()

    if "none" in id and "none" in type:
        data = client.execute(
            """query LoadTags($limit :Int){tags(orderType:guide,category:[show],limit:$limit){...TagCardFragmentOnTag}tagsCount(category:[show])}fragment TagCardFragmentOnTag on Tag{id,dotId,name,category,perex,urlName,images{...DefaultFragmentOnImage},originTag{...DefaultOriginTagFragmentOnTag}}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}""",
            {"limit": 500},
        )
        items = data["data"]["tags"]
    elif type == "related":
        data = client.execute(
            """query LoadTags($urlName : String, $limit : Int){ tags(listing: similar, category: [show], urlName: $urlName, limit: $limit){ ...TagCardFragmentOnTag } tagsCount(listing: similar, category: [show], urlName: $urlName) } fragment TagCardFragmentOnTag on Tag { id dotId name category perex urlName images { ...DefaultFragmentOnImage }, originTag { ...DefaultOriginTagFragmentOnTag } } fragment DefaultFragmentOnImage on Image { usage, url } fragment DefaultOriginTagFragmentOnTag on Tag { id dotId name urlName category images { ...DefaultFragmentOnImage } } """,
            {"urlName": id, "limit": 10},
        )
        items = data["data"]["tags"]
    else:
        data = client.execute(
            """query LoadChildTags($id :ID,$childTagsConnectionFirst :Int,$childTagsConnectionCategories :[Category]){tag(id:$id){childTagsConnection(categories:$childTagsConnectionCategories,first :$childTagsConnectionFirst){...TagCardsFragmentOnTagConnection}}}fragment TagCardsFragmentOnTagConnection on TagConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...TagCardFragmentOnTag}}}fragment TagCardFragmentOnTag on Tag{id,dotId,name,category,perex,urlName,images{...DefaultFragmentOnImage},originTag{...DefaultOriginTagFragmentOnTag}}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}""",
            {
                "id": id,
                "childTagsConnectionFirst": 500,
                "childTagsConnectionCategories": ["show"],
            },
        )
        items = data["data"]["tag"]["childTagsConnection"]["edges"]

    for item in items:
        menuitems = []
        if "none" not in id and "none" in type:
            item = item["node"]
        name = item["name"].strip()
        listitem = xbmcgui.ListItem(name)
        listitem.setInfo(
            "video", {"mediatype": "tvshow", "title": name, "plot": item["perex"]}
        )
        listitem.setArt({"poster": _image(item["images"])})
        menuitems.append(
            (
                _addon.getLocalizedString(30007),
                "Container.Update("
                + plugin.url_for(list_channels, item["urlName"], "related")
                + ")",
            )
        )
        listitem.addContextMenuItems(menuitems)
        listing.append(
            (
                plugin.url_for(
                    list_episodes, item["id"], item["urlName"], "none", item["category"]
                ),
                listitem,
                True,
            )
        )

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@plugin.route("/list_episodes/<id>/<urlname>/<page>/<category>")
def list_episodes(id, urlname, page, category):
    xbmcplugin.setContent(plugin.handle, "episodes")
    listing = []
    client = GraphQLClient()
    if page == "none":
        query = (
            """query LoadTag($urlName :String,$episodesConnectionFirst :Int){tagData:tag(urlName:$urlName,category:"""
            + category
            + """){...ShowDetailFragmentOnTag episodesConnection(first :$episodesConnectionFirst){...SeasonEpisodeCardsFragmentOnEpisodeItemConnection}}}fragment ShowDetailFragmentOnTag on Tag{id dotId name category urlName favouritesCount perex images{...DefaultFragmentOnImage}bannerAdvert{...DefaultFragmentOnBannerAdvert},originServiceTag{...OriginServiceTagFragmentOnTag}}fragment SeasonEpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...SeasonEpisodeCardFragmentOnEpisode}}}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultFragmentOnBannerAdvert on BannerAdvert{section}fragment OriginServiceTagFragmentOnTag on Tag{id,dotId,name,urlName,category,invisible,images{...DefaultFragmentOnImage}}fragment SeasonEpisodeCardFragmentOnEpisode on Episode{id dotId name namePrefix perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}"""
        )
        params = {
            "urlName": urlname,
            "episodesConnectionFirst": _addon.getSetting("limit"),
        }
    else:
        query = """query LoadTag($id :ID,$episodesConnectionAfter :String,$episodesConnectionFirst :Int){tagData:tag(id:$id){episodesConnection(after:$episodesConnectionAfter,first :$episodesConnectionFirst){...SeasonEpisodeCardsFragmentOnEpisodeItemConnection}}}fragment SeasonEpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...SeasonEpisodeCardFragmentOnEpisode}}}fragment SeasonEpisodeCardFragmentOnEpisode on Episode{id dotId name namePrefix perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}"""
        params = {
            "id": id,
            "episodesConnectionAfter": page,
            "episodesConnectionFirst": _addon.getSetting("limit"),
        }
    data = client.execute(query, params)

    for item in data["data"]["tagData"]["episodesConnection"]["edges"]:
        item = item["node"]
        name = item["name"].strip()

        listitem = xbmcgui.ListItem(name)
        listitem.setInfo(
            "video",
            {
                "mediatype": "episode",
                "tvshowtitle": item["originTag"]["name"],
                "title": name,
                "plot": item["perex"],
                "duration": item["duration"],
                "premiered": datetime.fromtimestamp(item["publish"]).strftime(
                    "%Y-%m-%d"
                ),
            },
        )
        listitem.setArt({"thumb": _image(item["images"])})
        listitem.setProperty("IsPlayable", "true")
        listing.append((plugin.url_for(get_video, item["urlName"]), listitem, False))

    if data["data"]["tagData"]["episodesConnection"]["pageInfo"]["hasNextPage"] == True:
        listitem = xbmcgui.ListItem(_addon.getLocalizedString(30001))
        listing.append(
            (
                plugin.url_for(
                    list_episodes,
                    id,
                    urlname,
                    data["data"]["tagData"]["episodesConnection"]["pageInfo"][
                        "endCursor"
                    ],
                    category,
                ),
                listitem,
                True,
            )
        )

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@plugin.route("/list_episodes_recent/<id>/<urlname>/<page>/<category>")
def list_episodes_recent(id, urlname, page, category):

    xbmcplugin.setContent(plugin.handle, "episodes")
    listing = []
    client = GraphQLClient()
    if "none" in (id, page) and category == "episodes":
        query = """query LoadTags($limit :Int,$episodesConnectionFirst :Int){tags(listing:homepage,limit:$limit){...TimelineBoxFragmentOnTag episodesConnection(first :$episodesConnectionFirst){...EpisodeCardsFragmentOnEpisodeItemConnection}}tagsCount(listing:homepage)}fragment TimelineBoxFragmentOnTag on Tag{id,dotId,name,urlName,category,originTag{...DefaultOriginTagFragmentOnTag}}fragment EpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...EpisodeCardFragmentOnEpisode}}}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}fragment EpisodeCardFragmentOnEpisode on Episode{id dotId name perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultFragmentOnImage on Image{usage,url}"""

        params = {"limit": 1, "episodesConnectionFirst": _addon.getSetting("limit")}
        data = client.execute(query, params)
        items = data["data"]["tags"][0]["episodesConnection"]["edges"]
        pageinfo = data["data"]["tags"][0]["episodesConnection"]["pageInfo"]
        id = data["data"]["tags"][0]["id"]

    if not "none" in (page) and category == "episodes":
        query = """query LoadTag($id :ID,$episodesConnectionAfter :String,$episodesConnectionFirst :Int){tagData:tag(id:$id){episodesConnection(after:$episodesConnectionAfter,first :$episodesConnectionFirst){...SeasonEpisodeCardsFragmentOnEpisodeItemConnection}}}fragment SeasonEpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...SeasonEpisodeCardFragmentOnEpisode}}}fragment SeasonEpisodeCardFragmentOnEpisode on Episode{id dotId name namePrefix perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}"""

        params = {
            "id": id,
            "episodesConnectionAfter": page,
            "episodesConnectionFirst": _addon.getSetting("limit"),
        }
        data = client.execute(query, params)
        items = data["data"]["tagData"]["episodesConnection"]["edges"]
        pageinfo = data["data"]["tagData"]["episodesConnection"]["pageInfo"]

    if category == "tag":
        query = (
            """query LoadTag($urlName :String,$episodesConnectionFirst :Int){tagData:tag(urlName:$urlName,category:"""
            + category
            + """){...ShowDetailFragmentOnTag episodesConnection(first :$episodesConnectionFirst){...SeasonEpisodeCardsFragmentOnEpisodeItemConnection}}}fragment ShowDetailFragmentOnTag on Tag{id dotId name category urlName favouritesCount perex images{...DefaultFragmentOnImage}bannerAdvert{...DefaultFragmentOnBannerAdvert},originServiceTag{...OriginServiceTagFragmentOnTag}}fragment SeasonEpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...SeasonEpisodeCardFragmentOnEpisode}}}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultFragmentOnBannerAdvert on BannerAdvert{section}fragment OriginServiceTagFragmentOnTag on Tag{id,dotId,name,urlName,category,invisible,images{...DefaultFragmentOnImage}}fragment SeasonEpisodeCardFragmentOnEpisode on Episode{id dotId name namePrefix perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}"""
        )

        params = {
            "urlName": urlname,
            "episodesConnectionFirst": _addon.getSetting("limit"),
        }
        data = client.execute(query, params)
        items = data["data"]["tagData"]["episodesConnection"]["edges"]
        pageinfo = data["data"]["tagData"]["episodesConnection"]["pageInfo"]

    if "none" in (id, page) and category == "channel_episodes":
        query = """query LoadChildTags($urlName :String,$childTagsConnectionFirst :Int,$episodesConnectionFirst :Int){tag(urlName:$urlName,category:service){childTagsConnection(first :$childTagsConnectionFirst){...TimelineBoxFragmentOnTagConnection edges{node{episodesConnection(first :$episodesConnectionFirst){...EpisodeCardsFragmentOnEpisodeItemConnection}}}}}}fragment TimelineBoxFragmentOnTagConnection on TagConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...TimelineBoxFragmentOnTag}}}fragment EpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...EpisodeCardFragmentOnEpisode}}}fragment TimelineBoxFragmentOnTag on Tag{id,dotId,name,urlName,category,originTag{...DefaultOriginTagFragmentOnTag}}fragment EpisodeCardFragmentOnEpisode on Episode{id dotId name perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}fragment DefaultFragmentOnImage on Image{usage,url}"""

        params = {
            "urlName": urlname,
            "childTagsConnectionFirst": 1,
            "episodesConnectionFirst": _addon.getSetting("limit"),
        }
        data = client.execute(query, params)
        items = data["data"]["tag"]["childTagsConnection"]["edges"][0]["node"][
            "episodesConnection"
        ]["edges"]
        pageinfo = data["data"]["tag"]["childTagsConnection"]["edges"][0]["node"][
            "episodesConnection"
        ]["pageInfo"]

    if not "none" in (page) and category == "channel_episodes":
        query = """query LoadTag($id :ID,$episodesConnectionAfter :String,$episodesConnectionFirst :Int){tagData:tag(id:$id){episodesConnection(after:$episodesConnectionAfter,first :$episodesConnectionFirst){...SeasonEpisodeCardsFragmentOnEpisodeItemConnection}}}fragment SeasonEpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...SeasonEpisodeCardFragmentOnEpisode}}}fragment SeasonEpisodeCardFragmentOnEpisode on Episode{id dotId name namePrefix perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}"""

        params = {
            "id": id,
            "episodesConnectionAfter": page,
            "episodesConnectionFirst": _addon.getSetting("limit"),
        }
        data = client.execute(query, params)
        items = data["data"]["tagData"]["episodesConnection"]["edges"]
        pageinfo = data["data"]["tagData"]["episodesConnection"]["pageInfo"]

    for item in items:
        menuitems = []
        item = item["node"]
        show_title = item["originTag"]["name"]
        name = item["name"].strip()

        listitem = xbmcgui.ListItem(
            "[COLOR blue]{0}[/COLOR] · {1}".format(show_title, name)
        )
        listitem.setInfo(
            "video",
            {
                "mediatype": "episode",
                "tvshowtitle": show_title,
                "title": name,
                "plot": item["perex"],
                "duration": item["duration"],
                "premiered": datetime.fromtimestamp(item["publish"]).strftime(
                    "%Y-%m-%d"
                ),
            },
        )
        listitem.setArt({"thumb": _image(item["images"])})
        listitem.setProperty("IsPlayable", "true")
        menuitems.append(
            (
                _addon.getLocalizedString(30006),
                "Container.Update("
                + plugin.url_for(
                    list_episodes,
                    item["originTag"]["id"],
                    item["originTag"]["urlName"],
                    "none",
                    item["originTag"]["category"],
                )
                + ")",
            )
        )
        menuitems.append(
            (
                _addon.getLocalizedString(30007),
                "Container.Update("
                + plugin.url_for(list_channels, item["originTag"]["urlName"], "related")
                + ")",
            )
        )
        listitem.addContextMenuItems(menuitems)
        listing.append((plugin.url_for(get_video, item["urlName"]), listitem, False))

    if pageinfo["hasNextPage"] == True:
        listitem = xbmcgui.ListItem(_addon.getLocalizedString(30001))
        listing.append(
            (
                plugin.url_for(
                    list_episodes_recent, id, urlname, pageinfo["endCursor"], "episodes"
                ),
                listitem,
                True,
            )
        )

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


@plugin.route("/get_video/<url>")
def get_video(url):
    client = GraphQLClient()
    data = client.execute(
        """query LoadEpisode($urlName :String){episode(urlName:$urlName){...VideoDetailFragmentOnEpisode}}fragment VideoDetailFragmentOnEpisode on Episode{id dotId dotOriginalService originalId name perex duration images{...DefaultFragmentOnImage}spl commentsDisabled productPlacement urlName originUrl originTag{...OriginTagInfoFragmentOnTag}advertEnabled adverts{...DefaultFragmentOnAdvert}bannerAdvert{...DefaultFragmentOnBannerAdvert}views publish links{...DefaultFragmentOnLinks}recommendedAbVariant sklikRetargeting}fragment DefaultFragmentOnImage on Image{usage,url}fragment OriginTagInfoFragmentOnTag on Tag{id,dotId,name,urlName,category,invisible,images{...DefaultFragmentOnImage}}fragment DefaultFragmentOnAdvert on Advert{zoneId section collocation position rollType}fragment DefaultFragmentOnBannerAdvert on BannerAdvert{section}fragment DefaultFragmentOnLinks on Link{label,url}""",
        {"urlName": url},
    )

    item = data["data"]["episode"]
    stream_server = data["data"]["episode"]["spl"].split("/")
    stream_data = client._get(data["data"]["episode"]["spl"] + "spl2,3,VOD")

    if "Location" in stream_data:
        stream_server = stream_data["Location"].split("/")
        stream_data = client._get(stream_data["Location"])

    if "hls" in stream_data["pls"]:
        stream_source = stream_data["pls"]["hls"]["url"][2:].replace("|", "%7C")
    else:
        stream_source = stream_data["data"]["mp4"][
            sorted(stream_data["data"]["mp4"], key=lambda kv: kv[1], reverse=False)[0]
        ]["url"][2:]
    stream_url = "{0}{1}".format("/".join(stream_server[0:5]), stream_source)

    listitem = xbmcgui.ListItem(path=stream_url)
    listitem.setInfo(
        "video",
        {
            "title": item["name"],
            "plot": item["perex"],
        },
    )
    listitem.setArt({"thumb": _image(item["images"])})

    xbmcplugin.setResolvedUrl(plugin.handle, True, listitem)


@plugin.route("/search")
def show_search():
    input = xbmc.Keyboard("", _addon.getLocalizedString(30005))
    input.doModal()
    if not input.isConfirmed():
        return
    search_url = plugin.url_for(list_search, input.getText())
    xbmc.executebuiltin(f"Container.Update({search_url})")
    xbmcplugin.endOfDirectory(plugin.handle)
    list_search(input.getText())


@plugin.route("/list_search/<query>")
def list_search(query):
    xbmcplugin.setContent(plugin.handle, "episodes")
    if query:
        client = GraphQLClient()
        data = client.execute(
            """query Search($query : String) { searchEpisode(query : $query) { ...EpisodeCardFragmentOnEpisode } searchTag(query : $query) { ...TagCardFragmentOnTag } } fragment EpisodeCardFragmentOnEpisode on Episode { id dotId name duration images { ...DefaultFragmentOnImage } urlName originTag { ...DefaultOriginTagFragmentOnTag } publish views spl }  fragment TagCardFragmentOnTag on Tag { id dotId name category perex urlName images { ...DefaultFragmentOnImage }, originTag { ...DefaultOriginTagFragmentOnTag } }  fragment DefaultFragmentOnImage on Image { usage, url }  fragment DefaultOriginTagFragmentOnTag on Tag { id dotId name urlName category images { ...DefaultFragmentOnImage }}""",
            {"query": query},
        )
        listing = []

        if data["data"]["searchTag"] or data["data"]["searchEpisode"]:
            for item in data["data"]["searchTag"]:
                name = item["name"].strip()
                listitem = xbmcgui.ListItem(name)
                listitem.setInfo("video", {"tvshowtitle": name, "plot": item["perex"]})
                listitem.setArt({"poster": _image(item["images"])})
                listing.append(
                    (
                        plugin.url_for(
                            list_episodes,
                            item["id"],
                            item["urlName"],
                            "none",
                            item["category"],
                        ),
                        listitem,
                        True,
                    )
                )

            for item in data["data"]["searchEpisode"]:
                menuitems = []
                show_title = item["originTag"]["name"]
                name = item["name"].strip()
                title_label = "[COLOR blue]{0}[/COLOR] · {1}".format(show_title, name)
                listitem = xbmcgui.ListItem(title_label)
                listitem.setInfo(
                    "video",
                    {
                        "mediatype": "episode",
                        "tvshowtitle": show_title,
                        "title": name,
                        "plot": name,
                        "duration": item["duration"],
                        "premiered": datetime.fromtimestamp(item["publish"]).strftime(
                            "%Y-%m-%d"
                        ),
                    },
                )
                listitem.setArt({"thumb": _image(item["images"])})
                listitem.setProperty("IsPlayable", "true")
                menuitems.append(
                    (
                        _addon.getLocalizedString(30006),
                        "Container.Update("
                        + plugin.url_for(
                            list_episodes,
                            item["originTag"]["id"],
                            item["originTag"]["urlName"],
                            "none",
                            item["originTag"]["category"],
                        )
                        + ")",
                    )
                )
                listitem.addContextMenuItems(menuitems)
                listing.append(
                    (plugin.url_for(get_video, item["urlName"]), listitem, False)
                )

            xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
            xbmcplugin.endOfDirectory(plugin.handle)
        else:
            xbmcgui.Dialog().notification(
                _addon.getAddonInfo("name"),
                _addon.getLocalizedString(30009),
                xbmcgui.NOTIFICATION_INFO,
                5000,
            )


@plugin.route("/")
def root():
    listing = []

    listitem = xbmcgui.ListItem(
        "[COLOR blue]Stream originals[/COLOR] · {0}".format(
            _addon.getLocalizedString(30002)
        )
    )
    listitem.setArt({"icon": "DefaultRecentlyAddedEpisodes.png"})
    listing.append(
        (
            plugin.url_for(
                list_episodes_recent, "VGFnOjI", "stream", "none", "channel_episodes"
            ),
            listitem,
            True,
        )
    )

    listitem = xbmcgui.ListItem(
        "[COLOR blue]Stream originals[/COLOR] · {0}".format(
            _addon.getLocalizedString(30003)
        )
    )
    listitem.setArt({"icon": "DefaultTVShows.png"})
    listing.append((plugin.url_for(list_channels, "VGFnOjI", "none"), listitem, True))

    listitem = xbmcgui.ListItem(_addon.getLocalizedString(30002))
    listitem.setArt({"icon": "DefaultRecentlyAddedEpisodes.png"})
    listing.append(
        (
            plugin.url_for(list_episodes_recent, "none", "none", "none", "episodes"),
            listitem,
            True,
        )
    )

    listitem = xbmcgui.ListItem(_addon.getLocalizedString(30008))
    listitem.setArt({"icon": "DefaultTVShows.png"})
    listing.append(
        (
            plugin.url_for(
                list_episodes_recent,
                "VGFnOjEyNzQ0MzE",
                "trendujici-videa",
                "none",
                "tag",
            ),
            listitem,
            True,
        )
    )

    listitem = xbmcgui.ListItem(_addon.getLocalizedString(30003))
    listitem.setArt({"icon": "DefaultTVShows.png"})
    listing.append((plugin.url_for(list_channels, "none", "none"), listitem, True))

    listitem = xbmcgui.ListItem(_addon.getLocalizedString(30004))
    listitem.setArt({"icon": "DefaultMovieTitle.png"})
    listing.append((plugin.url_for(list_categories), listitem, True))

    listitem = xbmcgui.ListItem(_addon.getLocalizedString(30005))
    listitem.setArt({"icon": "DefaultAddonsSearch.png"})
    listing.append((plugin.url_for(show_search), listitem, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)


def _image(data):
    if data:
        image = list(
            filter(lambda x: x["usage"] == "poster" or x["usage"] == "square", data)
        )[0]["url"]
        return image if "://" in image else "https://" + image


class GraphQLClient:

    def __init__(self):
        self.endpoint = "https://api.stream.cz/graphql"
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        }

    def execute(self, query, variables=None):
        return self._send(query, variables)

    def _send(self, query, variables):
        data = {"query": query, "variables": json.dumps(variables)}
        r = requests.post(self.endpoint, data=json.dumps(data), headers=self.headers)
        return r.json()

    def _get(self, url):
        r = requests.get(url, self.headers)
        return r.json()


def run():
    plugin.run()
