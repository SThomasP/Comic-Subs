from abc import abstractmethod
from google.appengine.ext import ndb
from google.appengine.ext.ndb import polymodel
import requests
import requests_toolbelt.adapters.appengine
from datetime import datetime
from bs4 import BeautifulSoup

requests_toolbelt.adapters.appengine.monkeypatch()


CROLL_DF = '%Y-%m-%d'
JUMP_FREE_DF = '%B0%d,0%Y'
JUMP_DF = "%b %d, %Y"
CMX_DF = "%d %B %Y"


class Chapter(ndb.Model):
    chapter_no = ndb.IntegerProperty()
    published = ndb.DateTimeProperty()
    url = ndb.StringProperty()
    thumbnail = ndb.StringProperty()

    @classmethod
    def lookup_chapters(cls):
        return Chapter.query().order(Chapter.published).fetch()


class Series(polymodel.PolyModel):
    title = ndb.StringProperty()
    url = ndb.StringProperty()
    lookup_url = ndb.StringProperty()

    @abstractmethod
    def check_for_new_chapter(self):
        pass

    def add_chapter(self, number, link, thumb, published):
        c = Chapter(parent=self.key, chapter_no=number, published=published, url=link, thumbnail=thumb)
        c.put()
        return c

    def get_last_published(self):
        last_chapter = Chapter.query(ancestor=self.key).order(Chapter.published).fetch(1)
        print str(last_chapter)
        if len(last_chapter) == 0:
            return datetime.min
        else:
            return last_chapter[0].published

    @classmethod
    def get_all(cls):
        return Series.query().fetch()


class Crunchyroll(Series):
    def check_for_new_chapter(self):
        r2 = requests.get(self.lookup_url)
        r_json = r2.json()
        latest = r_json['chapters'][::-1][0]
        c_number = int(float(latest['number']))
        c_img_url = latest['thumb_img']
        c_link_url = 'http://www.crunchyroll.com/comics_read/manga?volume_id={}&chapter_num={}'.format(
            latest['volume_id'], c_number)
        c_date = datetime.strptime(latest['availability_start'][0:10], CROLL_DF)
        if c_date > self.get_last_published():
            self.add_chapter(c_number, c_link_url, c_img_url, c_date)


class Comixology(Series):
    def check_for_new_chapter(self):
        r = requests.get(self.url)
        soup = BeautifulSoup(r.text, 'lxml')
        chapter_list = soup.find('div', class_='Issues')
        if chapter_list.find('div', class_='pager'):
            page_count = int(chapter_list.find('div', class_='pager')['data-page-count'])
            chapters = self._get_chapters(page_count)
        else:
            chapters = chapter_list.ul.contents
        while '\n' in chapters:
            chapters.remove('\n')
        chapters.reverse()
        found = False
        f = -1
        while not found:
            f += 1
            chapter = chapters[f]
            if chapter.find('a', class_='buy-action'):
                found = True
                thumb = chapter.find('img')['src']
                number = chapter.find('h6').text.split('#')[1]
                link = chapter.find('a', class_='content-details')['href']
                date = Comixology._get_date(link)
                if date > self.get_last_published():
                    self.add_chapter(number,link, thumb, date)

    def _get_chapters(self, page_no):
        r = requests.get(self.url+'?Issues_pg={}'.format(page_no))
        soup = BeautifulSoup(r.text, 'lxml')
        chapter_list = soup.find('div', class_='Issues')
        chapters = chapter_list.ul.contents
        return chapters

    @staticmethod
    def _get_date(url):
        r = requests.get(url)
        soup = BeautifulSoup(r.text,'lxml')
        titles = soup.find_all('h4', class_='subtitle')
        for title in titles:
            if title.text == 'Digital Release Date':
                date_text = title.next_sibling.text
                date1 = datetime.strptime(date_text, CMX_DF)
                return date1


class JumpFree(Series):
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
        number = int(ctitle[9:len(ctitle)])
        date = chapter.find('div', class_='mar-b-md').text.replace(' ', '0')
        date = datetime.strptime(date, JUMP_FREE_DF)
        if date > self.get_last_published():
            self.add_chapter(number, link_url, thumb, date)


class JumpMag(Series):
    def check_for_new_chapter(self):
        r = requests.get(self.url)
        soup = BeautifulSoup(r.text, 'lxml')
        link1 = soup.find('a', class_='product-thumb')
        thumb1 =link1.img['src']
        link1 = "https://www.viz.com" + link1['href']
        number1 = int(link1.rsplit('/', 1)[0].rsplit('-',1)[1])
        date1 = datetime.strptime(soup.find('h3').text, JUMP_DF)
        if date1 > self.get_last_published():
            self.add_chapter(number1,link1, thumb1, date1)