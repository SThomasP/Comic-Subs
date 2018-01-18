# noinspection PyUnresolvedReferences
from feedgen.feed import FeedGenerator
from pytz import utc


# wrapper for feedgen, save work by simplyfing things
class Feed:
    # create the feed
    def __init__(self, url):
        self.feed = FeedGenerator()
        self.feed.title("Comic Subs")
        self.feed.link(href=url)
        self.feed.description("The Comics Subscription Feed")

    # add a chapter to the feed
    def add_chapter(self, chapter):
        fe = self.feed.add_entry()
        fe.title(chapter.title)
        fe.guid(chapter.url)
        fe.link(href=chapter.url)
        fe.description('<p><a href="{}"><img src="{}" width="200"> </img> </a></p>'.format(chapter.url, chapter.thumbnail))
        fe.pubdate(chapter.published.replace(tzinfo=utc))

    # return the feed's rss
    def rss(self):
        return self.feed.rss_str()
