import flask
from subs import app
from datastore import Series, Chapter
from feed import Feed


# queue all series for a new chapter check
@app.route("/check")
def check():
    series_list = Series.get_all()
    for series in series_list:
        series.queue_new_chapter_check()
    return "", 200


# check a series for a new chapter
@app.route("/check/<string:key>", methods=['POST'])
def check_series(key):
    series = Series.get(key)
    series.check_for_new_chapter()
    return ""


# view all series and add and remove them
@app.route("/")
def view():
    series_list = Series.get_all()
    return flask.render_template('view.html', series_list=series_list)


# delete a series from the list
@app.route("/delete")
def delete():
    key = flask.request.args.get('key')
    s = Series.delete(key)
    flask.flash(s.title + " Deleted")
    return flask.redirect(flask.url_for("view"), code=303)


# add a series to the list
@app.route("/add", methods=['GET', 'POST'])
def add():
    url = flask.request.form['url']
    s = Series.add(url)
    if s is not None:
        s.put()
        s.queue_new_chapter_check()
        flask.flash(s.title + ' added')
    else:
        flask.flash("Cannot add")
    return flask.redirect(flask.url_for("view"), code=303)


# get the rss feed (open to all)
@app.route("/subscriptions.rss")
def get_feed():
    chapters = Chapter.lookup_chapters()
    feed = Feed(flask.request.url_root)
    for chapter in chapters:
        feed.add_chapter(chapter)
    resp = flask.make_response(feed.rss(), 200)
    # set the header
    resp.headers['content-type'] = 'application/rss+xml'
    return resp
