import random

import flask
from subs import app
from datastore import Series, Chapter
from feed import Feed
from google.appengine.api import users


# queue all series for a new chapter check
@app.route("/tasks/schedule")
def check():
    series_list = Series.get_all()
    for series in series_list:
        series.queue_new_chapter_check()
    return "", 200


# check a series for a new chapter
@app.route("/tasks/check/<string:key>", methods=['POST'])
def check_series(key):
    series = Series.get(key)
    app.logger.info("Checking '%s' (%s)", series.title, series.source)
    series.check_for_new_chapter()
    return ""


# view all series and add and remove them
@app.route("/")
def view():
    is_admin = users.is_current_user_admin()
    if users.get_current_user():
        is_user = True
        login_url = users.create_logout_url("/")
    else:
        is_user = False
        login_url = users.create_login_url("/")
    series_list = [x for x in Series.get_all()]
    random.shuffle(series_list)
    return flask.render_template('view.html', series_list=series_list, is_admin=is_admin, is_user=is_user, login_url=login_url)


# delete a series from the list
@app.route("/tasks/delete")
def delete():
    key = flask.request.args.get('key')
    s = Series.delete(key)
    flask.flash(s.title + " Deleted", 'warning')
    return flask.redirect(flask.url_for("view"), code=303)


# add a series to the list
@app.route("/tasks/add", methods=['GET','POST'])
def add():
    url = flask.request.form['url']
    try:
        s = Series.add(url)
    except IndexError:
        s = None
    if s is not None:
        s.put()
        s.queue_new_chapter_check()
        flask.flash(s.title + ' added', 'success')
    else:
        flask.flash("Cannot add Comic", 'danger')
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
