import flask
from subs import app
from datastore import Series, Chapter
from feed import Feed


@app.route("/check")
def check():
    series_list = Series.get_all()
    for series in series_list:
        series.queue_new_chapter_check()
    return "", 200


@app.route("/check/<string:key>", methods=['POST'])
def check_series(key):
    series = Series.get(key)
    series.check_for_new_chapter()
    return ""


@app.route("/")
def view():
    series_list = Series.get_all()
    return flask.render_template('view.html', series_list=series_list)


@app.route("/delete")
def delete():
    key = flask.request.args.get('key')
    s = Series.delete(key)
    flask.flash(s.title + " Deleted")
    return flask.redirect(flask.url_for("view"), code=303)


@app.route("/add", methods=['GET', 'POST'])
def add():
    if flask.request.method == 'POST':
        title = flask.request.form['title']
        source = flask.request.form['source']
        url = flask.request.form['url']
        lookup = flask.request.form['lookup']
        s = Series.add(title, source, url, lookup)
        flask.flash(s.title + ' added')
        return flask.redirect(flask.url_for("view"), code=303)
    else:
        return flask.render_template("add.html")


@app.route("/subscriptions.rss")
def get_feed():
    chapters = Chapter.lookup_chapters()
    feed = Feed(flask.request.url_root)
    for chapter in chapters:
        feed.add_chapter(chapter)
    resp = flask.make_response(feed.rss(), 200)
    resp.headers['content-type'] = 'application/rss+xml'
    return resp
