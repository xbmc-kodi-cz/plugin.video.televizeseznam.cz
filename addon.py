# -*- coding: utf-8 -*-
import os
import urllib
import urllib2
import xbmcplugin
import xbmcgui
import xbmcaddon
import json
from datetime import datetime
from client import GraphQLClient

_apiurl = 'https://api.televizeseznam.cz/graphql'

_addon = xbmcaddon.Addon('plugin.video.televizeseznam.cz')
_lang = _addon.getLocalizedString

MODE_LIST_SHOWS = 1
MODE_LIST_CHANNELS = 2
MODE_LIST_CATEGORIES = 3
MODE_LIST_EPISODES = 4
MODE_LIST_PLAYLIST_EPISODES = 5
MODE_LIST_CHANNEL_EPISODES_LATEST = 6
MODE_LIST_EPISODES_LATEST = 7
MODE_VIDEOLINK = 10

def log(msg, level=xbmc.LOGDEBUG):
    if type(msg).__name__ == 'unicode':
        msg = msg.encode('utf-8')
    xbmc.log("[%s] %s" % (_addon.getAddonInfo('name'), msg.__str__()), level)

def logDbg(msg):
    log(msg,level=xbmc.LOGDEBUG)

def logErr(msg):
    log(msg,level=xbmc.LOGERROR)

def listContent():
    addDir(_lang(30003)+" "+"Stream", { "urlid": "stream", "url": "stream", "category": "service" }, MODE_LIST_SHOWS, '')
    addDir(_lang(30002)+" "+"Stream", { "urlid": "stream", "url": "stream", "category": "service" }, MODE_LIST_CHANNEL_EPISODES_LATEST, '')
    addDir(_lang(30002), { "urlid": "ListShowLatest", "url": "ListShowLatest", "category": "show" }, MODE_LIST_EPISODES_LATEST, '')
    addDir(_lang(30003), { "urlid": "ListShowLatest", "url": "ListShowLatest", "category": "show" }, MODE_LIST_SHOWS, '')
    addDir(_lang(30004), { "urlid": "ListShowLatest", "url": "listCategories", "category": "show" }, MODE_LIST_CATEGORIES, '')

def listCategories():    
    client = GraphQLClient(_apiurl)
    params = { "limit": 20 }

    data = client.execute('''query LoadTags($limit : Int){ tags(inGuide: true, limit: $limit){ ...NavigationCategoryFragmentOnTag  } tagsCount(inGuide: true) }
		fragment NavigationCategoryFragmentOnTag on Tag {
			id,
			name,
			category,
			urlName
		}
	''', params)
        
    for item in data[u'data'][u'tags']:
        link = { "urlid": item[u'id'], "url": item[u'urlName'], "category": "channel" }
        name = item[u'name']
        addDir(name, link, MODE_LIST_CHANNELS, '')
        
def listShows():    
    client = GraphQLClient(_apiurl)
    params = { "limit": 500 }

    data = client.execute('''query LoadTags($limit : Int){ tags(listing: navigation, limit: $limit){ ...NavigationFragmentOnTag  } tagsCount(listing: navigation) }
		fragment NavigationFragmentOnTag on Tag {
			id,
			name,
			images {
				...DefaultFragmentOnImage
			},
			category,
			urlName,
			originTag {
				...DefaultOriginTagFragmentOnTag
			}
		}
	
		fragment DefaultFragmentOnImage on Image {
			usage,
			url
		}
	
		fragment DefaultOriginTagFragmentOnTag on Tag {
			id,
			dotId,
			name,
			urlName,
			category,
			images {
				...DefaultFragmentOnImage
			}
		}
	''', params)

    for item in data[u'data'][u'tags']:
        link = { "urlid": item[u'id'], "url": item[u'urlName'], "category": item[u'category'] }
        name = item[u'name']
        for images in item[u'images']:
            image = 'https:'+images[u'url'] 
        if item[u'category'] == 'service':
            addDir(name, link, MODE_LIST_CHANNELS, image)
        else:
            addDir(name, link, MODE_LIST_EPISODES, image)

def listChannels(urlid, url, category):
    client = GraphQLClient(_apiurl)
    params = { "id": urlid, "childTagsConnectionFirst": 500, "childTagsConnectionCategories": ["show","tag"] }

    data = client.execute('''query LoadChildTags($id : ID, $childTagsConnectionFirst : Int, $childTagsConnectionCategories : [Category]){ tag(id: $id){ childTagsConnection(categories: $childTagsConnectionCategories,first : $childTagsConnectionFirst) { ...TagCardsFragmentOnTagConnection  } } }
		fragment TagCardsFragmentOnTagConnection on TagConnection {
			totalCount
			pageInfo {
				endCursor
				hasNextPage
			}
			edges {
				node {
					...TagCardFragmentOnTag
				}
			}
		}
	
		fragment TagCardFragmentOnTag on Tag {
			id,
			dotId,
			name,
			category,
			perex,
			urlName,
			images {
				...DefaultFragmentOnImage
			},
			originTag {
				...DefaultOriginTagFragmentOnTag
			}
		}
	
		fragment DefaultFragmentOnImage on Image {
			usage,
			url
		}
	
		fragment DefaultOriginTagFragmentOnTag on Tag {
			id,
			dotId,
			name,
			urlName,
			category,
			images {
				...DefaultFragmentOnImage
			}
		}
	''', params)
    
    addDir("#"+_lang(30002), { "urlid": urlid, "url": url, "category": category }, MODE_LIST_CHANNEL_EPISODES_LATEST, '') 
    
    for item in data[u'data'][u'tag'][u'childTagsConnection'][u'edges']:
        link = { "urlid": item[u'node'][u'id'], "url": item[u'node'][u'urlName'], "category": "show" }
        for images in item[u'node'][u'images']:
            image = 'https:'+images[u'url'] 
        name = item[u'node'][u'name']
        if item[u'node'][u'category'] == 'tag':
            addDir(name, link, MODE_LIST_PLAYLIST_EPISODES, image)
        else:
            addDir(name, link, MODE_LIST_EPISODES, image)
        
def listPlaylistEpisodes(url):
    client = GraphQLClient(_apiurl)
    params = { "urlName": url, "episodesConnectionFirst": 100 }

    data = client.execute('''query LoadTag($urlName : String, $episodesConnectionFirst : Int){ tagData:tag(urlName: $urlName, category: tag){ ...PlaylistDetailFragmentOnTag episodesConnection(first : $episodesConnectionFirst) { ...EpisodeCardsFragmentOnEpisodeItemConnection } } }
		fragment PlaylistDetailFragmentOnTag on Tag {
			id
			dotId
			name
			urlName
			perex
			category
			images {
				...DefaultFragmentOnImage
			}
			originTag {
				...OriginTagInfoFragmentOnTag
			}
			bannerAdvert {
				...DefaultFragmentOnBannerAdvert
			}
		}
	
		fragment EpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection {
			totalCount
			pageInfo {
				endCursor
				hasNextPage
			}
			edges {
				node {
					...EpisodeCardFragmentOnEpisode
				}
			}
		}
	
		fragment DefaultFragmentOnImage on Image {
			usage,
			url
		}
	
		fragment OriginTagInfoFragmentOnTag on Tag {
			id,
			dotId,
			name,
			urlName,
			category,
			invisible,
			images {
				...DefaultFragmentOnImage
			}
		}
	
		fragment DefaultFragmentOnBannerAdvert on BannerAdvert {
			section
		}
	
		fragment EpisodeCardFragmentOnEpisode on Episode {
			id
			dotId
			name
			duration
			images {
				...DefaultFragmentOnImage
			}
			urlName
			originTag {
				...DefaultOriginTagFragmentOnTag
			}
			publish
			views
		}
	
		fragment DefaultOriginTagFragmentOnTag on Tag {
			id,
			dotId,
			name,
			urlName,
			category,
			images {
				...DefaultFragmentOnImage
			}
		}
        ''', params)
        
    for item in data[u'data'][u'tagData'][u'episodesConnection'][u'edges']:
        link = { "urlid": item[u'node'][u'id'], "url": item[u'node'][u'urlName'], "category": "show" }
        image = 'https:'+item[u'node'][u'images'][0][u'url']
        name = item[u'node'][u'name']
        date = datetime.utcfromtimestamp(item[u'node'][u'publish']).strftime("%Y-%m-%d")
        info = { "duration": item[u'node'][u'duration'], "date": date }
        addResolvedLink(name, link, image, name, info=info)

def listEpisodes(url):
    client = GraphQLClient(_apiurl)
    params = { "urlName": url, "episodesConnectionFirst": 100 }

    data = client.execute('''query LoadTag($urlName : String, $episodesConnectionFirst : Int){ tagData:tag(urlName: $urlName, category: show){ ...ShowDetailFragmentOnTag episodesConnection(first : $episodesConnectionFirst) { ...SeasonEpisodeCardsFragmentOnEpisodeItemConnection } } }
		fragment ShowDetailFragmentOnTag on Tag {
			id
			dotId
			name
			category
			urlName
			favouritesCount
			perex
			images {
				...DefaultFragmentOnImage
			}
			bannerAdvert {
				...DefaultFragmentOnBannerAdvert
			},
			originServiceTag {
				...OriginServiceTagFragmentOnTag
			}
		}	
	
		fragment SeasonEpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection {
			totalCount
			pageInfo {
				endCursor
				hasNextPage
			}
			edges {
				node {
					...SeasonEpisodeCardFragmentOnEpisode
				}
			}
		}
	
		fragment DefaultFragmentOnImage on Image {
			usage,
			url
		}
	
		fragment DefaultFragmentOnBannerAdvert on BannerAdvert {
			section
		}
	
		fragment OriginServiceTagFragmentOnTag on Tag {
			id,
			dotId,
			name,
			urlName,
			category,
			invisible,
			images {
				...DefaultFragmentOnImage
			}
		}
	
		fragment SeasonEpisodeCardFragmentOnEpisode on Episode {
			id
			dotId
			name
			namePrefix
			duration
			images {
				...DefaultFragmentOnImage
			}
			urlName
			originTag {
				...DefaultOriginTagFragmentOnTag
			}
			publish
			views
		}
	
		fragment DefaultOriginTagFragmentOnTag on Tag {
			id,
			dotId,
			name,
			urlName,
			category,
			images {
				...DefaultFragmentOnImage
			}
		}
        ''', params)
        
    for item in data[u'data'][u'tagData'][u'episodesConnection'][u'edges']:
        link = { "urlid": item[u'node'][u'id'], "url": item[u'node'][u'urlName'], "category": "show" }
        image = 'https:'+item[u'node'][u'images'][0][u'url']
        name = item[u'node'][u'name']
        date = datetime.utcfromtimestamp(item[u'node'][u'publish']).strftime("%Y-%m-%d")
        info={ "duration": item[u'node'][u'duration'], "date": date }
        addResolvedLink(name, link, image, name, info=info)

def listChannelEpisodesLatest(url, category):
    client = GraphQLClient(_apiurl)
    params = {"urlName": url, "childTagsConnectionFirst": 1, "episodesConnectionFirst": 100}

    data = client.execute('''query LoadChildTags($urlName : String, $childTagsConnectionFirst : Int, $episodesConnectionFirst : Int){ tag(urlName: $urlName, category: '''+category+'''){ childTagsConnection(first : $childTagsConnectionFirst) { ...TimelineBoxFragmentOnTagConnection  edges { node { episodesConnection(first : $episodesConnectionFirst) { ...EpisodeCardsFragmentOnEpisodeItemConnection } } } } } }
		fragment TimelineBoxFragmentOnTagConnection on TagConnection {
			totalCount
			pageInfo {
				endCursor
				hasNextPage
			}
			edges {
				node {
					...TimelineBoxFragmentOnTag
				}
			}
		}
	
		fragment EpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection {
			totalCount
			pageInfo {
				endCursor
				hasNextPage
			}
			edges {
				node {
					...EpisodeCardFragmentOnEpisode
				}
			}
		}
	
		fragment TimelineBoxFragmentOnTag on Tag {
			id,
			dotId,
			name,
			urlName,
			category,
			originTag {
				...DefaultOriginTagFragmentOnTag
			}
		}
	
		fragment EpisodeCardFragmentOnEpisode on Episode {
			id
			dotId
			name
			duration
			images {
				...DefaultFragmentOnImage
			}
			urlName
			originTag {
				...DefaultOriginTagFragmentOnTag
			}
			publish
			views
		}
	
		fragment DefaultOriginTagFragmentOnTag on Tag {
			id,
			dotId,
			name,
			urlName,
			category,
			images {
				...DefaultFragmentOnImage
			}
		}
	
		fragment DefaultFragmentOnImage on Image {
			usage,
			url
		}
	''', params)
    
    for item in data[u'data'][u'tag'][u'childTagsConnection'][u'edges'][0][u'node'][u'episodesConnection'][u'edges']:
        link = { "urlid": item[u'node'][u'id'], "url": item[u'node'][u'urlName'], "category": "show" }
        name = item[u'node'][u'name']
        tag = item[u'node'][u'originTag'][u'name']
        if tag:
            name = tag + ' | ' + name 
        for images in item[u'node'][u'images']:
            image = 'https:'+images[u'url'] 
        date = datetime.utcfromtimestamp(item[u'node'][u'publish']).strftime("%Y-%m-%d")
        info={'duration':item[u'node'][u'duration'],'date':date}
        addResolvedLink(name, link, image, item[u'node'][u'name'], info=info)

def listEpisodesLatest():
    client = GraphQLClient(_apiurl)
    params = { "limit": 1, "episodesConnectionFirst": 50 }

    data = client.execute('''query LoadTags($limit : Int, $episodesConnectionFirst : Int){ tags(listing: homepage, limit: $limit){ ...TimelineBoxFragmentOnTag episodesConnection(first : $episodesConnectionFirst) { ...EpisodeCardsFragmentOnEpisodeItemConnection } } tagsCount(listing: homepage) }
		fragment TimelineBoxFragmentOnTag on Tag {
			id,
			dotId,
			name,
			urlName,
			category,
			originTag {
				...DefaultOriginTagFragmentOnTag
			}
		}
	
		fragment EpisodeCardsFragmentOnEpisodeItemConnection on EpisodeItemConnection {
			totalCount
			pageInfo {
				endCursor
				hasNextPage
			}
			edges {
				node {
					...EpisodeCardFragmentOnEpisode
				}
			}
		}
	
		fragment DefaultOriginTagFragmentOnTag on Tag {
			id,
			dotId,
			name,
			urlName,
			category,
			images {
				...DefaultFragmentOnImage
			}
		}
	
		fragment EpisodeCardFragmentOnEpisode on Episode {
			id
			dotId
			name
			duration
			images {
				...DefaultFragmentOnImage
			}
			urlName
			originTag {
				...DefaultOriginTagFragmentOnTag
			}
			publish
			views
		}
	
		fragment DefaultFragmentOnImage on Image {
			usage,
			url
		}
	''', params)
        
    
    for item in data[u'data'][u'tags'][0][u'episodesConnection'][u'edges']:
        link = { "urlid": item[u'node'][u'id'], "url": item[u'node'][u'urlName'], "category": "show" }
        tag = item[u'node'][u'originTag'][u'name']
        name = item[u'node'][u'name']
        if tag:
            name = tag + ' | ' + name
        image = 'https:'+item[u'node'][u'images'][0][u'url']
        date = datetime.utcfromtimestamp(item[u'node'][u'publish']).strftime("%Y-%m-%d")
        info={'duration':item[u'node'][u'duration'],'date':date}
        addResolvedLink(name, link, image, item[u'node'][u'name'], info=info)

def getVideoLink(url):
    req = urllib2.Request(url, None, {'Content-type': 'application/json', 'Accept': 'application/json'})
    resp = urllib2.urlopen(req)
    return json.loads(resp.read().decode('utf-8'))
    
def videoLink(url):
    client = GraphQLClient(_apiurl)
    params = { "urlName": url }

    data = client.execute('''query LoadEpisode($urlName : String){ episode(urlName: $urlName){ ...VideoDetailFragmentOnEpisode } }
		fragment VideoDetailFragmentOnEpisode on Episode {
			id
			dotId
			dotOriginalService
			originalId
			name
			perex
			duration
			images {
				...DefaultFragmentOnImage
			}
			spl
			commentsDisabled
			productPlacement
			urlName
			originUrl
			originTag {
				...OriginTagInfoFragmentOnTag
			}
			advertEnabled
			adverts {
				...DefaultFragmentOnAdvert
			}
			bannerAdvert {
				...DefaultFragmentOnBannerAdvert
			}
			views
			publish
			links {
				...DefaultFragmentOnLinks
			}
			recommendedAbVariant
			sklikRetargeting
		}
	
		fragment DefaultFragmentOnImage on Image {
			usage,
			url
		}
	
		fragment OriginTagInfoFragmentOnTag on Tag {
			id,
			dotId,
			name,
			urlName,
			category,
			invisible,
			images {
				...DefaultFragmentOnImage
			}
		}
	
		fragment DefaultFragmentOnAdvert on Advert {
			zoneId
			section
			collocation
			position
			rollType
		}
	
		fragment DefaultFragmentOnBannerAdvert on BannerAdvert {
			section
		}
	
		fragment DefaultFragmentOnLinks on Link {
			label,
			url
		}
	''', params)
    
    name = data[u'data'][u'episode'][u'name']
    image = 'https:'+data[u'data'][u'episode'][u'images'][0][u'url']
    perex = data[u'data'][u'episode'][u'perex']
    link = data[u'data'][u'episode'][u'spl'].split('/')
    
    url=getVideoLink(data[u'data'][u'episode'][u'spl']+'spl2,3')

    if 'Location' in url:
        link = url[u'Location'].split('/')
        url = getVideoLink(url[u'Location'])
    
    for quality in sorted(url[u'data'][u"mp4"], key=lambda kv: kv[1], reverse=True):
        stream_quality=quality
        video_url = url[u'data'][u"mp4"][stream_quality][u"url"][3:]

    stream_url = '/'.join(link[0:5])+'/'+video_url

    liz = xbmcgui.ListItem()
    liz = xbmcgui.ListItem(path=stream_url)  
    liz.setInfo( type="Video", infoLabels={ "Title": name, "Plot": perex})
    liz.setProperty('isPlayable', 'true')
    xbmcplugin.setResolvedUrl(handle=addonHandle, succeeded=True, listitem=liz)

def getParams():
    param=[]
    paramstring=sys.argv[2]
    if len(paramstring)>=2:
        params=sys.argv[2]
        cleanedparams=params.replace('?','')
        if (params[len(params)-1]=='/'):
            params=params[0:len(params)-2]
        pairsofparams=cleanedparams.split('&')
        param={}
        for i in range(len(pairsofparams)):
            splitparams={}
            splitparams=pairsofparams[i].split('=')
            if (len(splitparams))==2:
                param[splitparams[0]]=splitparams[1]
    return param

def composePluginUrl(urlid, url, category, mode, name):
    return sys.argv[0]+"?urlid="+urllib.quote_plus(urlid.encode('utf-8'))+"&url="+urllib.quote_plus(url.encode('utf-8'))+"&category="+urllib.quote_plus(category.encode('utf-8'))+"&mode="+str(mode)+"&name="+urllib.quote_plus(name.encode('utf-8'))

def addItem(name, url, mode, iconimage, desc, isfolder, islatest=False, info={}):  
    u = composePluginUrl(url[u'urlid'], url[u'url'], url[u'category'], mode, name)
    ok=True
    liz=xbmcgui.ListItem(name, iconImage="DefaultFolder.png", thumbnailImage=iconimage)
    liz.setInfo(type="Video", infoLabels={"Title": name, 'plot': desc})
    liz.setProperty("Fanart_Image", iconimage)
    if u'duration' in info:
            liz.setInfo('video', {'duration': info[u'duration']})
    if u'date' in info:
            liz.setInfo('video', {'premiered': info[u'date']})
    liz.setInfo('video', {'mediatype': 'episode', 'title': name, 'plot': desc})
    if not isfolder:
        liz.setProperty("isPlayable", "true")
    else:
        xbmcplugin.addSortMethod( handle = addonHandle, sortMethod=xbmcplugin.SORT_METHOD_LABEL )
    ok=xbmcplugin.addDirectoryItem( handle = addonHandle,url=u,listitem=liz,isFolder=isfolder )
    return ok

def addDir(name, url, mode, iconimage, plot='', info={}):
    print url
    #logDbg("addDir(): '"+name+"' url='"+url+"' icon='"+iconimage+"' mode='"+str(mode)+"'")
    return addItem(name, url, mode, iconimage, plot, True)
    
def addResolvedLink(name, url, iconimage, plot='', islatest=False, info={}):
    xbmcplugin.setContent(addonHandle, 'episodes')
    mode = MODE_VIDEOLINK
    #logDbg("addUnresolvedLink(): '"+name+"' url='"+url+"' icon='"+iconimage+"' mode='"+str(mode)+"'")
    return addItem(name, url, mode, iconimage, plot, False, islatest, info)

addonHandle=int(sys.argv[1])
params=getParams()
urlid = None
url = None
category = None
name = None
thumb = None
mode = None

try:
    urlid = urllib.unquote_plus(params["urlid"])
except:
    pass

try:
    url = urllib.unquote_plus(params["url"])
except:
    pass

try:
    category = urllib.unquote_plus(params["category"])
except:
    pass
    
try:
    name = urllib.unquote_plus(params["name"])
except:
    pass
    
try:
    mode = int(params["mode"])
except:
    pass

logDbg("Mode: "+str(mode))
logDbg("URLid: "+str(urlid))
logDbg("URL: "+str(url))
logDbg("Category: "+str(category))
logDbg("Name: "+str(name))

if mode==None or url==None or len(url)<1:
    logDbg('listContent()')
    listContent()

elif mode == MODE_LIST_SHOWS:
    logDbg('listShows()')
    listShows()
    
elif mode == MODE_LIST_CATEGORIES:
    logDbg('listCategories()')
    listCategories()

elif mode == MODE_LIST_CHANNELS:
    logDbg('listChannels()')
    listChannels(urlid, url, category)  
    
elif mode == MODE_LIST_EPISODES:
    logDbg('listEpisodes()')
    listEpisodes(url)

elif mode == MODE_LIST_PLAYLIST_EPISODES:
    logDbg('listPlaylistEpisodes()')
    listPlaylistEpisodes(url)
    
elif mode == MODE_LIST_EPISODES_LATEST:
    logDbg('listEpisodesLatest()')
    listEpisodesLatest()
       
elif mode == MODE_LIST_CHANNEL_EPISODES_LATEST:
    logDbg('listChannelEpisodesLatest()')
    listChannelEpisodesLatest(url, category)

elif mode == MODE_VIDEOLINK:
    logDbg('videoLink() with url ' + str(url))
    videoLink(url)
    
xbmcplugin.endOfDirectory(addonHandle)
