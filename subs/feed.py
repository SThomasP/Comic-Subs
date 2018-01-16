# noinspection PyUnresolvedReferences
from feedgen.feed import FeedGenerator
from pytz import utc


class Feed:
    def __init__(self, url):
        self.feed = FeedGenerator()
        self.feed.title("Comic Subs")
        self.feed.link(href=url)
        self.feed.description("The Comics Subscription Feed")

    def add_chapter(self, chapter):
        fe = self.feed.add_entry()
        fe.title(chapter.title)
        fe.guid(chapter.url)
        fe.link(href=chapter.url)
        fe.description('<p><img src="{}" width="200"> </img></p>'.format(chapter.thumbnail))
        fe.pubdate(chapter.published.replace(tzinfo=utc))

    def rss(self):
        return self.feed.rss_str()
