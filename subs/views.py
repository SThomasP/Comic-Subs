import flask
from subs import app
from datastore import Series, Chapter, Crunchyroll, Comixology, JumpMag, JumpFree
from feed import Feed



def check():
    series_list = Series.get_all()
    for series in series_list:
        print series.title
        series.check_for_new_chapter()
    return "", 200

@app.route("/subscriptions.rss")
def get_feed():
    chapters = Chapter.lookup_chapters()
    print(chapters)
    feed = Feed(flask.request.url_root)
    for chapter in chapters:
        series = chapter.key.parent().get()
        feed.add_chapter(chapter, series)
    resp = flask.make_response(feed.rss(), 200)
    resp.headers['content-type'] = 'application/rss+xml'
    return resp