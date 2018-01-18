from abc import abstractmethod, abstractproperty
from google.appengine.ext import ndb
from google.appengine.ext.ndb import polymodel
import requests
import requests_toolbelt.adapters.appengine
from datetime import datetime
from bs4 import BeautifulSoup
from google.appengine.api import taskqueue
import urlparse

requests_toolbelt.adapters.appengine.monkeypatch()

CROLL_DF = '%Y-%m-%d'
JUMP_FREE_DF = '%B0%d,0%Y'
JUMP_DF = "%b %d, %Y"
CMX_DF = "%d %B %Y"


class Chapter(ndb.Model):
    chapter_no = ndb.FloatProperty()
    published = ndb.DateTimeProperty()
    url = ndb.StringProperty()
    thumbnail = ndb.StringProperty()
    title = ndb.ComputedProperty(lambda self: self.generate_title())

    @classmethod
    def lookup_chapters(cls):
        return Chapter.query().order(Chapter.published).fetch()

    def generate_title(self):
        series_title = self.key.parent().get().title
        return u"{} #{:g}".format(series_title, self.chapter_no)


class Series(polymodel.PolyModel):
    title = ndb.StringProperty()
    url = ndb.StringProperty()
    lookup_url = ndb.StringProperty()

    def get_key(self):
        return self.key.urlsafe()

    @abstractproperty
    def source(self):
        pass

    @abstractmethod
    def check_for_new_chapter(self):
        pass

    def queue_new_chapter_check(self):
        taskqueue.add(queue_name="check-queue", url='/check/' + self.get_key())

    def add_chapter(self, number, link, thumb, published):
        c = Chapter(parent=self.key, chapter_no=number, published=published, url=link, thumbnail=thumb)
        c.put()
        chapters = Chapter.query(ancestor=self.key).order(-Chapter.published).fetch()
        while len(chapters) > 5:
            key = chapters.pop().key
            key.delete()
        return c

    def get_last_published(self):
        last_chapter = Chapter.query(ancestor=self.key).order(-Chapter.published).fetch(1)
        if len(last_chapter) == 0:
            return datetime.min
        else:
            return last_chapter[0].published

    @classmethod
    def get_all(cls):
        return Series.query().order(Series.title).fetch()

    @classmethod
    def delete(cls, string):
        key = ndb.Key(urlsafe=string)
        series = key.get()
        chapters = Chapter.query(ancestor=key).fetch()
        for chapter in chapters:
            chapter.key.delete()
        key.delete()
        return series

    @classmethod
    def add(cls, url):
        o = urlparse.urlparse(url)
        source = o.netloc.split(".")[1]
        if source =="comixology":
            return Comixology.create(url)
        elif source == 'crunchyroll':
            return Crunchyroll.create(url)
        elif source == 'viz':
            path = o.path.split("/")[1::]
            if path[0::1] == ['shonenjump','chapters']:
                return JumpFree.create(url)
            elif path[0] == 'shonenjump':
                return JumpMag(title="Weekly Shonen Jump", url=url, lookup_url=None)

        else:
            return None


    @classmethod
    def get(cls, key):
        return ndb.Key(urlsafe=key).get()


class Crunchyroll(Series):
    @property
    def source(self):
        return "Crunchyroll Manga"

    def check_for_new_chapter(self):
        r2 = requests.get(self.lookup_url)
        r_json = r2.json()
        latest = r_json['chapters'][::-1][0]
        c_number = float(latest['number'])
        c_img_url = latest['thumb_img']
        c_link_url = 'http://www.crunchyroll.com/comics_read/manga?volume_id={}&chapter_num={}'.format(
            latest['volume_id'], c_number)
        c_date = datetime.strptime(latest['availability_start'][0:10], CROLL_DF)
        if c_date > self.get_last_published():
            self.add_chapter(c_number, c_link_url, c_img_url, c_date)

    @classmethod
    def create(cls, url):
        r = requests.get(url)
        soup = BeautifulSoup(r.text, 'lxml')
        title = soup.find('h1', class_='ellipsis').text.split(">")[1].strip()
        vol_id = soup.find('li', class_='volume-simul')['volume_id']
        lookup_url = "http://api-manga.crunchyroll.com/list_chapters?volume_id={}".format(vol_id)
        return Crunchyroll(title=title, url=url, lookup_url=lookup_url)


class Comixology(Series):

    @classmethod
    def create(cls, url):
        r = requests.get(url)
        soup = BeautifulSoup(r.text, 'lxml')
        title = soup.find("h1", itemprop="name").text
        s = Comixology(title=title, url=url, lookup_url=None)
        return s

    @property
    def source(self):
        return "Comixology"

    def check_for_new_chapter(self):

        def extract_chapters(chapter_soup):
            chapter_list = chapter_soup.find('div', class_='Issues')
            extracted = chapter_list.ul.contents
            while '\n' in extracted:
                extracted.remove('\n')
            return extracted

        def get_chapters(page_no):
            r2 = requests.get(self.url + '?Issues_pg={}'.format(page_no))
            soup2 = BeautifulSoup(r2.text, 'lxml')
            extracted = extract_chapters(soup2)
            return extracted

        r = requests.get(self.url)
        soup = BeautifulSoup(r.text, 'lxml')
        pager = soup.find('div', class_='Issues').find('div', class_='pager')
        if pager:
            page_count = int(pager['data-page-count'])
            chapters = get_chapters(page_count)
        else:
            chapters = extract_chapters(soup)
            page_count = 1

        found = False
        while len(chapters) > 0 or not found:
            chapter = chapters.pop()
            if chapter.find('a', class_='buy-action'):
                found = True
                thumb = chapter.find('img')['src']
                number = float(chapter.find('h6').text.split('#')[1])
                link = chapter.find('a', class_='content-details')['href']
                date = Comixology._get_date(link)
                if date > self.get_last_published():
                    self.add_chapter(number, link, thumb, date)
            elif len(chapters) == 0 and page_count > 1:
                page_count -= 1
                if page_count == 1:
                    chapters += extract_chapters(soup)
                else:
                    chapters += get_chapters(page_count)





    @staticmethod
    def _get_date(url):
        r = requests.get(url)
        soup = BeautifulSoup(r.text, 'lxml')
        titles = soup.find_all('h4', class_='subtitle')
        for title in titles:
            if title.text == 'Digital Release Date':
                date_text = title.next_sibling.text
                date1 = datetime.strptime(date_text, CMX_DF)
                return date1


class JumpFree(Series):
    @property
    def source(self):
        return "WSJ Free Section"

    def check_for_new_chapter(self):
        r = requests.get(self.url)
        soup = BeautifulSoup(r.text, 'lxml')
        chapters = soup.find('div', class_='o_products').contents
        while '\n' in chapters:
            chapters.remove('\n')
        chapter = chapters[0]
        thumb = chapter.find('img')['data-original']
        link_url = 'https://viz.com{}'.format(chapter('a')[0]['href'])
        ctitle = chapter.find('div', class_='type-md').text
        number = float(ctitle[9:len(ctitle)])
        date = chapter.find('div', class_='mar-b-md').text.replace(' ', '0')
        date = datetime.strptime(date, JUMP_FREE_DF)
        if date > self.get_last_published():
            self.add_chapter(number, link_url, thumb, date)

    @classmethod
    def create(cls, url):
        o = urlparse.urlparse(url)
        r = requests.get('https://www.viz.com/shonenjump/chapters/all')
        soup = BeautifulSoup(r.text, 'lxml')
        title = soup.find('a', href=o.path).text.split("\n\n\n")[1].strip()
        return JumpFree(title=title, url=url, lookup_url=None)


class JumpMag(Series):
    @property
    def source(self):
        return "WSJ Magazine"

    def check_for_new_chapter(self):
        r = requests.get(self.url)
        soup = BeautifulSoup(r.text, 'lxml')
        link1 = soup.find('a', class_='product-thumb')
        thumb1 = link1.img['src']
        link1 = "https://www.viz.com" + link1['href']
        number1 = float(link1.rsplit('/', 1)[0].rsplit('-', 1)[1])
        date1 = datetime.strptime(soup.find('h3').text, JUMP_DF)
        if date1 > self.get_last_published():
            self.add_chapter(number1, link1, thumb1, date1)
