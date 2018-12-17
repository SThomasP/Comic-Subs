from abc import abstractmethod, abstractproperty
from google.appengine.ext import ndb
from google.appengine.ext.ndb import polymodel
import requests
import requests_toolbelt.adapters.appengine
from datetime import datetime
from bs4 import BeautifulSoup
from google.appengine.api import taskqueue
import urlparse
import base64

# this allows us to use requests in GAE
requests_toolbelt.adapters.appengine.monkeypatch()

CROLL_DF = '%Y-%m-%d'
JUMP_FREE_DF = '%B0%d,0%Y'
CMX_DF = "%d %B %Y"


# Model of the chapters
class Chapter(ndb.Model):
    chapter_no = ndb.FloatProperty()
    published = ndb.DateTimeProperty()
    url = ndb.StringProperty()
    title = ndb.ComputedProperty(lambda self: self.generate_title())

    # Get a list of chapters in the datastore for the rss feed
    @classmethod
    def lookup_chapters(cls):
        return Chapter.query().order(Chapter.published).fetch()

    # generate the title of the chapter in the form "Series #No"
    def generate_title(self):
        series_title = self.key.parent().get().title
        return u"{} #{:g}".format(series_title, self.chapter_no)


# PolyModel of Series classes, allows for multiple class of lookup, rather than one for each class
class Series(polymodel.PolyModel):
    title = ndb.StringProperty()
    url = ndb.StringProperty()
    lookup_url = ndb.StringProperty()
    image = ndb.TextProperty()

    # get the key of the series object
    def get_key(self):
        return self.key.urlsafe()

    # abstract property, used to get a nice name for the source
    @abstractproperty
    def source(self):
        pass

    # abstract property used to get the logo representation of the source
    @abstractproperty
    def sourcelogo(self):
        pass

    # abstract method for the the various different sources get requests
    @abstractmethod
    def check_for_new_chapter(self):
        pass

    def get_chapters(self):
        chapters = Chapter.query(ancestor=self.key).order(Chapter.chapter_no).fetch()
        return chapters

    # queue the check for a new chapter in this series
    def queue_new_chapter_check(self):
        taskqueue.add(queue_name="check-queue", url='/tasks/check/' + self.get_key())

    # add a chapter to the series
    def add_chapter(self, number, link, published):
        c = Chapter(parent=self.key, chapter_no=number, published=published, url=link)
        c.put()
        chapters = Chapter.query(ancestor=self.key).order(-Chapter.published).fetch()
        # if there are more than 5 chapters, delete until there are 5
        while len(chapters) > 5:
            key = chapters.pop().key
            key.delete()
        return c

    # get the date of the last chapter published
    def get_last_published(self):
        last_chapter = Chapter.query(ancestor=self.key).order(-Chapter.published).fetch(1)
        if len(last_chapter) == 0:
            # if no chapters, return datetime.min
            return datetime.min
        else:
            return last_chapter[0].published

    def get_last_chapter_number(self):
        last_chapter = Chapter.query(ancestor=self.key).order(-Chapter.chapter_no).fetch(1)
        if len(last_chapter) == 0:
            # if no chapters, return datetime.min
            return -1
        else:
            return last_chapter[0].chapter_no

    # get all the series in a list
    @classmethod
    def get_all(cls):
        return Series.query().fetch()

    # delete a series
    @classmethod
    def delete(cls, string):
        key = ndb.Key(urlsafe=string)
        series = key.get()
        # get the chapters of the series an delete them
        chapters = Chapter.query(ancestor=key).fetch()
        for chapter in chapters:
            chapter.key.delete()
        # then delete the series
        key.delete()
        return series

    # add the series
    @classmethod
    def add(cls, url):
        # examine the url to find the source class, then create an object of that class and return it
        o = urlparse.urlparse(url)
        source = o.netloc.split(".")[1]
        if source =="comixology":
            return Comixology.create(url)
        elif source == 'crunchyroll':
            return Crunchyroll.create(url)
        elif source == 'viz':
            path = o.path.split("/")[1::]
            if path[0:2] == ['shonenjump','chapters']:
                return JumpFree.create(url)
        # if no source return None
        else:
            return None

    @staticmethod
    def get_data_url(url):
        r = requests.get(url)
        data_url = 'data:image/jpeg;base64,' + base64.b64encode(r.content)
        return data_url


    # get a series object
    @classmethod
    def get(cls, key):
        return ndb.Key(urlsafe=key).get()


# Crunchyroll Manga Series
class Crunchyroll(Series):

    @property
    def source(self):
        return "Crunchyroll Manga"

    @property
    def sourcelogo(self):
        return 'crunchyroll.png'

    def check_for_new_chapter(self):
        # use the api, rather than bothering with parsing
        r2 = requests.get(self.lookup_url)
        r_json = r2.json()
        # get the last chapter
        chapters = r_json['chapters'][::-1]
        # get the number
        last_chapter_number = self.get_last_chapter_number()
        for chapter in chapters:
            c_number = float(chapter['number'])
            # generate the url
            c_link_url = 'http://www.crunchyroll.com/comics_read/manga?series_id={}&chapter_num={}'.format(
                chapter['series_id'], c_number)
            # and get the date
            try:
                c_date = datetime.strptime(chapter['availability_start'][0:10], CROLL_DF)
            except ValueError:
                c_date = datetime.strptime(chapter['updated'][0:10], CROLL_DF)
            # check to see if it's "new"
            if c_number > last_chapter_number:
                # if so, add it
                self.add_chapter(c_number, c_link_url, c_date)
                if last_chapter_number == -1:
                    break
            else:
                break

    # find the title and lookup url for the series object
    @classmethod
    def create(cls, url):
        r = requests.get(url)
        soup = BeautifulSoup(r.text, 'lxml')
        title = soup.find('h1', class_='ellipsis').text.split(">")[1].strip()
        series_id = soup.find(id="sharing_add_queue_button")['group_id']
        lookup_url = "http://api-manga.crunchyroll.com/list_chapters?series_id={}".format(series_id)
        image = soup.find('img',class_="poster xsmall-margin-bottom").attrs['src']
        image = Series.get_data_url(image)
        return Crunchyroll(title=title, url=url, lookup_url=lookup_url, image=image)




class Comixology(Series):

    # find the title and url for the series object
    @classmethod
    def create(cls, url):
        r = requests.get(url)
        soup = BeautifulSoup(r.text, 'lxml')
        title = soup.find("h1", itemprop="name").text
        image = soup.find("img", class_="series-cover").attrs['src']
        image = Series.get_data_url(image)
        s = Comixology(title=title, url=url, lookup_url=None, image=image)
        return s

    @property
    def sourcelogo(self):
        return 'comixology.png'

    @property
    def source(self):
        return "Comixology"

    def check_for_new_chapter(self):
        # find the chapter list, and then remove blank elements
        def extract_chapters(chapter_soup):
            chapter_list = chapter_soup.find('div', class_='Issues')
            extracted = chapter_list.ul.contents
            while '\n' in extracted:
                extracted.remove('\n')
            return extracted

        # get the chapters from pages 2+
        def get_chapters(page_no):
            r2 = requests.get(self.url + '?Issues_pg={}'.format(page_no))
            soup2 = BeautifulSoup(r2.text, 'lxml')
            extracted = extract_chapters(soup2)
            return extracted

        r = requests.get(self.url)
        soup = BeautifulSoup(r.text, 'lxml')
        # start on the last page
        pager = soup.find('div', class_='Issues').find('div', class_='pager')
        if pager:
            page_count = int(pager['data-page-count'])
            chapters = get_chapters(page_count)
        else:
            chapters = extract_chapters(soup)
            page_count = 1

        last_chapter_number = self.get_last_chapter_number()
        while len(chapters) > 0:
            # take the last chapter
            chapter = chapters.pop()
            # if it's out, mark it found
            if chapter.find('a', class_='buy-action'):
                # get the info
                n = chapter.find('h6').text.split(' ')[1].split('#')[1]
                number = float(n)
                link = chapter.find('a', class_='content-details')['href']
                date = Comixology._get_date(link)
                # check the date
                if number > last_chapter_number:
                    self.add_chapter(number, link, date)
                    if last_chapter_number == -1:
                        break
                else:
                    break
            # if it's not on that page go back a page and keep trying
            elif len(chapters) == 0 and page_count > 1:
                page_count -= 1
                if page_count == 1:
                    chapters += extract_chapters(soup)
                else:
                    chapters += get_chapters(page_count)

    # get the date from the link(not on the list)
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
        return "Shonen Jump"

    @property
    def sourcelogo(self):
        return 'viz.png'

    # look for the latest chapter
    def check_for_new_chapter(self):
        r = requests.get(self.url)
        soup = BeautifulSoup(r.text, 'lxml')
        chapters = soup.find('div', class_='o_sort_container').contents
        while '\n' in chapters:
            chapters.remove('\n')
        last_chapter_number = self.get_last_chapter_number()
        for chapter in chapters:
            link_url = 'https://viz.com{}'.format(chapter('a')[0]['data-target-url'].split('?')[0])
            number = float(chapter.find('div', class_='disp-id').text.split(' ')[1])
            date = chapter.find('td', class_='pad-y-0').text.replace(' ', '0')
            date = datetime.strptime(date, JUMP_FREE_DF)
            if number > last_chapter_number:
                self.add_chapter(number, link_url, date)
                if last_chapter_number == -1:
                    break
            else:
                break

    # look at the index of series and the find the title that way
    @classmethod
    def create(cls, url):
        o = urlparse.urlparse(url)
        r = requests.get('https://www.viz.com/shonenjump')
        soup = BeautifulSoup(r.text, 'lxml')
        thing = soup.find('a', href=o.path)
        title = thing.text.split("\n\n\n")[1].strip()
        image = thing.img.attrs['data-original']
        image = Series.get_data_url(image)
        return JumpFree(title=title, url=url, lookup_url=None, image=image)
