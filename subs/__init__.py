from flask import Flask
from google.appengine.api.app_logging import AppLogsHandler


app = Flask(__name__)
app.secret_key = 'Y!m&#!s#JW7Qi2q@wVTcFg4dpOvlCuGn$JJMv^D@HUU754K@03'
# error logger
app.logger.addHandler(AppLogsHandler())

from subs import views
