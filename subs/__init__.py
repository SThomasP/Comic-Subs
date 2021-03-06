from flask import Flask
from google.appengine.api.app_logging import AppLogsHandler


app = Flask(__name__)
app.config.from_json("../config.json")
# Uncomment this line for debugging
# app.debug = True

# error logger
app.logger.addHandler(AppLogsHandler())

from subs import views
