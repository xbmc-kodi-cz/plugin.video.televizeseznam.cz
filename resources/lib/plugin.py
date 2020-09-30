# -*- coding: utf-8 -*-
import routing
import requests
import xbmc
import xbmcplugin
import xbmcgui
import xbmcaddon
import json
from datetime import datetime

_apiurl = 'https://api.televizeseznam.cz/graphql'

_addon = xbmcaddon.Addon()
_lang = _addon.getLocalizedString

plugin = routing.Plugin()

@plugin.route('/list_categories/')
def list_categories():
    xbmcplugin.addSortMethod( plugin.handle, sortMethod=xbmcplugin.SORT_METHOD_LABEL )
    listing = []
    client = GraphQLClient(_apiurl)
    data = client.execute('''query LoadTags($limit :Int){tags(inGuide:true,limit:$limit){...NavigationCategoryFragmentOnTag}tagsCount(inGuide:true)}fragment NavigationCategoryFragmentOnTag on Tag{id,name,category,urlName}''', { 'limit': 20 })

    for item in data['data']['tags']:
        list_item = xbmcgui.ListItem(item['name'].strip())
        listing.append((plugin.url_for(list_channels, item['id']), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)

@plugin.route('/list_channels/<id>/')
def list_channels(id):
    xbmcplugin.addSortMethod(plugin.handle, sortMethod=xbmcplugin.SORT_METHOD_UNSORTED )
    xbmcplugin.addSortMethod( plugin.handle, sortMethod=xbmcplugin.SORT_METHOD_LABEL )
    xbmcplugin.setContent(plugin.handle, 'tvshows')
    listing = []
    client = GraphQLClient(_apiurl)
    if id == 'none':
        data = client.execute('''query LoadTags($limit :Int){tags(orderType:guide,category:[show],limit:$limit){...TagCardFragmentOnTag}tagsCount(category:[show])}fragment TagCardFragmentOnTag on Tag{id,dotId,name,category,perex,urlName,images{...DefaultFragmentOnImage},originTag{...DefaultOriginTagFragmentOnTag}}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}''', { 'limit': 500 })
        items = data['data']['tags']
    else:
        data = client.execute('''query LoadChildTags($id :ID,$childTagsConnectionFirst :Int,$childTagsConnectionCategories :[Category]){tag(id:$id){childTagsConnection(categories:$childTagsConnectionCategories,first :$childTagsConnectionFirst){...TagCardsFragmentOnTagConnection}}}fragment TagCardsFragmentOnTagConnection on TagConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...TagCardFragmentOnTag}}}fragment TagCardFragmentOnTag on Tag{id,dotId,name,category,perex,urlName,images{...DefaultFragmentOnImage},originTag{...DefaultOriginTagFragmentOnTag}}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}''', { 'id': id, 'childTagsConnectionFirst': 500, 'childTagsConnectionCategories': ['show'] })
        items = data['data']['tag']['childTagsConnection']['edges']

    for item in items:
        if id != 'none':
            item = item['node']
        name = item['name'].strip()
        list_item = xbmcgui.ListItem(name)
        list_item.setInfo('video', {'mediatype': 'tvshow', 'title': name, 'plot': item['perex']})
        list_item.setArt({'poster': _image(item['images'])})
        listing.append((plugin.url_for(list_episodes, item['id'], item['urlName'], 'none',item['category']), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)

@plugin.route('/list_episodes/<id>/<urlname>/<page>/<category>')
def list_episodes(id, urlname, page, category):
    xbmcplugin.setContent(plugin.handle, 'episodes')
    listing = []
    client = GraphQLClient(_apiurl)
    if page == 'none':
        query = '''query LoadTag($urlName :String,$episodesConnectionFirst :Int){tagData:tag(urlName:$urlName,category:'''+category+'''){...ShowDetailFragmentOnTag episodesConnection(first :$episodesConnectionFirst){...SeasonEpisodeCardsFragmentOnEpisodeItemConnection}}}fragment ShowDetailFragmentOnTag on Tag{id dotId name category urlName favouritesCount perex images{...DefaultFragmentOnImage}bannerAdvert{...DefaultFragmentOnBannerAdvert},originServiceTag{...OriginServiceTagFragmentOnTag}}fragment SeasonEpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...SeasonEpisodeCardFragmentOnEpisode}}}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultFragmentOnBannerAdvert on BannerAdvert{section}fragment OriginServiceTagFragmentOnTag on Tag{id,dotId,name,urlName,category,invisible,images{...DefaultFragmentOnImage}}fragment SeasonEpisodeCardFragmentOnEpisode on Episode{id dotId name namePrefix perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}'''
        params = { 'urlName': urlname, 'episodesConnectionFirst': _addon.getSetting('limit') }
    else:
        query = '''query LoadTag($id :ID,$episodesConnectionAfter :String,$episodesConnectionFirst :Int){tagData:tag(id:$id){episodesConnection(after:$episodesConnectionAfter,first :$episodesConnectionFirst){...SeasonEpisodeCardsFragmentOnEpisodeItemConnection}}}fragment SeasonEpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...SeasonEpisodeCardFragmentOnEpisode}}}fragment SeasonEpisodeCardFragmentOnEpisode on Episode{id dotId name namePrefix perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}'''
        params = {'id': id, 'episodesConnectionAfter': page, 'episodesConnectionFirst': _addon.getSetting('limit') }
    data = client.execute(query, params)

    for item in data['data']['tagData']['episodesConnection']['edges']:
        item = item['node']            
        name = item['name'].strip()
        list_item = xbmcgui.ListItem(name)
        list_item.setInfo('video', {'mediatype': 'episode', 'tvshowtitle': item['originTag']['name'], 'title': name, 'plot': item['perex'], 'duration': item['duration'], 'premiered': datetime.utcfromtimestamp(item['publish']).strftime('%Y-%m-%d')})
        list_item.setArt({'icon': _image(item['images'])})
        list_item.setProperty('IsPlayable', 'true')
        listing.append((plugin.url_for(get_video, item['urlName']), list_item, False))
    if(data['data']['tagData']['episodesConnection']['pageInfo']['hasNextPage'] == True):
        list_item = xbmcgui.ListItem(_addon.getLocalizedString(30001))
        listing.append((plugin.url_for(list_episodes, id, urlname, data['data']['tagData']['episodesConnection']['pageInfo']['endCursor'], category), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)

@plugin.route('/list_episodes_recent/<id>/<urlname>/<page>/<category>/')
def list_episodes_recent(id, urlname, page, category):
    xbmcplugin.setContent(plugin.handle, 'episodes')
    listing = []
    client = GraphQLClient(_apiurl)
    if 'none' in (id, page) and category == 'episodes':
        query = '''query LoadTags($limit :Int,$episodesConnectionFirst :Int){tags(listing:homepage,limit:$limit){...TimelineBoxFragmentOnTag episodesConnection(first :$episodesConnectionFirst){...EpisodeCardsFragmentOnEpisodeItemConnection}}tagsCount(listing:homepage)}fragment TimelineBoxFragmentOnTag on Tag{id,dotId,name,urlName,category,originTag{...DefaultOriginTagFragmentOnTag}}fragment EpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...EpisodeCardFragmentOnEpisode}}}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}fragment EpisodeCardFragmentOnEpisode on Episode{id dotId name perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultFragmentOnImage on Image{usage,url}'''
        
        params = { 'limit': 1, 'episodesConnectionFirst': _addon.getSetting('limit') }
        data = client.execute(query, params)
        items = data['data']['tags'][0]['episodesConnection']['edges']
        pageinfo = data['data']['tags'][0]['episodesConnection']['pageInfo']
        id = data['data']['tags'][0]['id']

    if not 'none' in (page) and category == 'episodes':
        query = '''query LoadTag($id :ID,$episodesConnectionAfter :String,$episodesConnectionFirst :Int){tagData:tag(id:$id){episodesConnection(after:$episodesConnectionAfter,first :$episodesConnectionFirst){...SeasonEpisodeCardsFragmentOnEpisodeItemConnection}}}fragment SeasonEpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...SeasonEpisodeCardFragmentOnEpisode}}}fragment SeasonEpisodeCardFragmentOnEpisode on Episode{id dotId name namePrefix perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}'''
        
        params = {'id': id, 'episodesConnectionAfter': page, 'episodesConnectionFirst': _addon.getSetting('limit') }
        data = client.execute(query, params)
        items = data['data']['tagData']['episodesConnection']['edges']
        pageinfo = data['data']['tagData']['episodesConnection']['pageInfo']

    if 'none' in (id, page) and category == 'channel_episodes':
        query = '''query LoadChildTags($urlName :String,$childTagsConnectionFirst :Int,$episodesConnectionFirst :Int){tag(urlName:$urlName,category:service){childTagsConnection(first :$childTagsConnectionFirst){...TimelineBoxFragmentOnTagConnection edges{node{episodesConnection(first :$episodesConnectionFirst){...EpisodeCardsFragmentOnEpisodeItemConnection}}}}}}fragment TimelineBoxFragmentOnTagConnection on TagConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...TimelineBoxFragmentOnTag}}}fragment EpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...EpisodeCardFragmentOnEpisode}}}fragment TimelineBoxFragmentOnTag on Tag{id,dotId,name,urlName,category,originTag{...DefaultOriginTagFragmentOnTag}}fragment EpisodeCardFragmentOnEpisode on Episode{id dotId name perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}fragment DefaultFragmentOnImage on Image{usage,url}'''
        
        params = { 'urlName': urlname, 'childTagsConnectionFirst': 1, 'episodesConnectionFirst': _addon.getSetting('limit') }
        data = client.execute(query, params)
        items = data['data']['tag']['childTagsConnection']['edges'][0]['node']['episodesConnection']['edges']
        pageinfo = data['data']['tag']['childTagsConnection']['edges'][0]['node']['episodesConnection']['pageInfo']

    if not 'none' in (page) and category == 'channel_episodes':
        query = '''query LoadTag($id :ID,$episodesConnectionAfter :String,$episodesConnectionFirst :Int){tagData:tag(id:$id){episodesConnection(after:$episodesConnectionAfter,first :$episodesConnectionFirst){...SeasonEpisodeCardsFragmentOnEpisodeItemConnection}}}fragment SeasonEpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection{totalCount pageInfo{endCursor hasNextPage}edges{node{...SeasonEpisodeCardFragmentOnEpisode}}}fragment SeasonEpisodeCardFragmentOnEpisode on Episode{id dotId name namePrefix perex duration images{...DefaultFragmentOnImage}urlName originTag{...DefaultOriginTagFragmentOnTag}publish views}fragment DefaultFragmentOnImage on Image{usage,url}fragment DefaultOriginTagFragmentOnTag on Tag{id,dotId,name,urlName,category,images{...DefaultFragmentOnImage}}'''
        
        params = {'id': id, 'episodesConnectionAfter': page, 'episodesConnectionFirst': _addon.getSetting('limit')}
        data = client.execute(query, params)
        items = data['data']['tagData']['episodesConnection']['edges']
        pageinfo = data['data']['tagData']['episodesConnection']['pageInfo']

    for item in items:
        menuitems = []
        item = item['node']
        show_title = item['originTag']['name']
        name = item['name'].strip()
        list_item = xbmcgui.ListItem(u'[COLOR blue]{0}[/COLOR] · {1}'.format(show_title, name))
        list_item.setInfo('video', {'mediatype': 'episode', 'tvshowtitle': show_title, 'title': name, 'plot': item['perex'], 'duration': item['duration'], 'premiered': datetime.utcfromtimestamp(item['publish']).strftime('%Y-%m-%d')})
        list_item.setArt({'icon': _image(item['images'])})
        list_item.setProperty('IsPlayable', 'true')
        menuitems.append(( _addon.getLocalizedString(30006), 'XBMC.Container.Update('+plugin.url_for(list_episodes, item['originTag']['id'], item['originTag']['urlName'], 'none', item['originTag']['category'])+')' ))
        list_item.addContextMenuItems(menuitems)
        listing.append((plugin.url_for(get_video, item['urlName']), list_item, False))
    if(pageinfo['hasNextPage'] == True):
        list_item = xbmcgui.ListItem(_addon.getLocalizedString(30001))
        listing.append((plugin.url_for(list_episodes_recent, id, urlname, pageinfo['endCursor'], 'episodes'), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)

@plugin.route('/get_video/<url>')
def get_video(url):
    client = GraphQLClient(_apiurl)
    data = client.execute('''query LoadEpisode($urlName :String){episode(urlName:$urlName){...VideoDetailFragmentOnEpisode}}fragment VideoDetailFragmentOnEpisode on Episode{id dotId dotOriginalService originalId name perex duration images{...DefaultFragmentOnImage}spl commentsDisabled productPlacement urlName originUrl originTag{...OriginTagInfoFragmentOnTag}advertEnabled adverts{...DefaultFragmentOnAdvert}bannerAdvert{...DefaultFragmentOnBannerAdvert}views publish links{...DefaultFragmentOnLinks}recommendedAbVariant sklikRetargeting}fragment DefaultFragmentOnImage on Image{usage,url}fragment OriginTagInfoFragmentOnTag on Tag{id,dotId,name,urlName,category,invisible,images{...DefaultFragmentOnImage}}fragment DefaultFragmentOnAdvert on Advert{zoneId section collocation position rollType}fragment DefaultFragmentOnBannerAdvert on BannerAdvert{section}fragment DefaultFragmentOnLinks on Link{label,url}''', { 'urlName': url })
    
    stream = _page(data['data']['episode']['spl']+'spl2,3,VOD')
    stream_server = data['data']['episode']['spl'].split('/')
    if 'Location' in stream:
        stream_server = stream[u'Location'].split('/')
        stream = _page(stream[u'Location'])
    stream_quality = sorted(stream['data']['mp4'], key=lambda kv: kv[1], reverse=False)[0] if _addon.getSetting('auto_quality') == 'true' else _addon.getSetting('own_quality')
    stream_url = '{}/{}'.format('/'.join(stream_server[0:5]),stream['data']['mp4'][stream_quality]['url'][3:])
    list_item = xbmcgui.ListItem(path=stream_url)
    xbmcplugin.setResolvedUrl(plugin.handle, True, list_item)
    xbmcplugin.endOfDirectory(plugin.handle)

@plugin.route('/search/')
def search():
    xbmcplugin.setContent(plugin.handle, 'episodes')
    listing = []
    input = xbmc.Keyboard('', _addon.getLocalizedString(30005))
    input.doModal()
    if not input.isConfirmed():
        return
    query = input.getText()
    client = GraphQLClient(_apiurl)
    data = client.execute('''query Search($query : String) { searchEpisode(query : $query) { ...EpisodeCardFragmentOnEpisode } searchTag(query : $query) { ...TagCardFragmentOnTag } } fragment EpisodeCardFragmentOnEpisode on Episode { id dotId name duration images { ...DefaultFragmentOnImage } urlName originTag { ...DefaultOriginTagFragmentOnTag } publish views spl }  fragment TagCardFragmentOnTag on Tag { id dotId name category perex urlName images { ...DefaultFragmentOnImage }, originTag { ...DefaultOriginTagFragmentOnTag } }  fragment DefaultFragmentOnImage on Image { usage, url }  fragment DefaultOriginTagFragmentOnTag on Tag { id dotId name urlName category images { ...DefaultFragmentOnImage }}''', { 'query': query })

    for item in data['data']['searchTag']:
        name = item['name'].strip()
        list_item = xbmcgui.ListItem(name)
        list_item.setInfo('video', {'tvshowtitle': name, 'plot': item['perex']})
        list_item.setArt({'poster': _image(item['images'])})
        listing.append((plugin.url_for(list_episodes, item['id'], item['urlName'], 'none', item['category']), list_item, True))
        
    for item in data['data']['searchEpisode']:
        menuitems = []
        show_title = item['originTag']['name']
        name = item['name'].strip()
        title_label = u'[COLOR blue]{0}[/COLOR] · {1}'.format(show_title, name)
        list_item = xbmcgui.ListItem(title_label)
        list_item.setInfo('video', {'mediatype': 'episode', 'tvshowtitle': show_title, 'title': name, 'plot': name, 'duration': item['duration'], 'premiered': datetime.utcfromtimestamp(item['publish']).strftime('%Y-%m-%d')})
        list_item.setArt({'icon': _image(item['images'])})
        list_item.setProperty('IsPlayable', 'true')
        menuitems.append(( _addon.getLocalizedString(30006), 'XBMC.Container.Update('+plugin.url_for(list_episodes, item['originTag']['id'], item['originTag']['urlName'], 'none', item['originTag']['category'])+')' ))
        list_item.addContextMenuItems(menuitems)
        listing.append((plugin.url_for(get_video, item['urlName']), list_item, False))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)

@plugin.route('/')
def root():
    listing = []

    list_item = xbmcgui.ListItem('[COLOR blue]Stream[/COLOR] · {0}'.format(_addon.getLocalizedString(30002).encode('utf-8')))
    list_item.setArt({'icon': 'DefaultRecentlyAddedEpisodes.png'})
    listing.append((plugin.url_for(list_episodes_recent, 'VGFnOjI', 'stream', 'none', 'channel_episodes'), list_item, True))

    list_item = xbmcgui.ListItem('[COLOR blue]Stream[/COLOR] · {0}'.format(_addon.getLocalizedString(30003).encode('utf-8')))
    list_item.setArt({'icon': 'DefaultTVShows.png'})
    listing.append((plugin.url_for(list_channels, 'VGFnOjI'), list_item, True))

    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30002))
    list_item.setArt({'icon': 'DefaultRecentlyAddedEpisodes.png'})
    listing.append((plugin.url_for(list_episodes_recent, 'none', 'none', 'none', 'episodes'), list_item, True))

    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30003))
    list_item.setArt({'icon': 'DefaultTVShows.png'})
    listing.append((plugin.url_for(list_channels, 'none'), list_item, True))

    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30004))
    list_item.setArt({'icon': 'DefaultMovieTitle.png'})
    listing.append((plugin.url_for(list_categories), list_item, True))

    list_item = xbmcgui.ListItem(_addon.getLocalizedString(30005))
    list_item.setArt({'icon': 'DefaultAddonsSearch.png'})
    listing.append((plugin.url_for(search), list_item, True))

    xbmcplugin.addDirectoryItems(plugin.handle, listing, len(listing))
    xbmcplugin.endOfDirectory(plugin.handle)

def _image(data):
    if data:
        image = list(filter(lambda x:x['usage']=='poster' or x['usage'] == 'square', data))
        return 'https:{0}'.format(image[0]['url'])

def _page(url):
    r = requests.get(url, headers={'Content-type': 'application/json', 'Accept': 'application/json'})
    return r.json()

class GraphQLClient:
    def __init__(self, endpoint):
        self.endpoint = endpoint

    def execute(self, query, variables=None):
        return self._send(query, variables)

    def _send(self, query, variables):
        data = {'query': query,
                'variables': json.dumps(variables)}
        headers = {'Accept': 'application/json',
                'Content-Type': 'application/json'}
        r = requests.post(self.endpoint, data = json.dumps(data), headers = headers)
        return r.json()

def run():
    plugin.run()
    