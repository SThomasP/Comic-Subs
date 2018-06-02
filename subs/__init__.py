from flask import Flask
from google.appengine.api.app_logging import AppLogsHandler


app = Flask(__name__)
app.config.from_json("../config.json")
# error logger
app.debug = True
app.logger.addHandler(AppLogsHandler())

from subs import views
