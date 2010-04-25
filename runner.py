#!/usr/bin/python

# Add modules.zip to our path for App Engine to see our
# jinja2, werkzeug and flask modules.
import sys
sys.path.insert(0, 'modules.zip')

# Force-import them here. For some reason, it doesn't work when flask
# imports them itself...
import jinja2
import werkzeug

# Set up a Django configuration so we can call Django functions (so we can use
# Django filters in Jinja2, for example)
from django.conf import settings
try:
	settings.configure(DEBUG=False, TEMPLATE_DEBUG=False, TEMPLATE_DIRS=())
except EnvironmentError:
	pass

# Serve
from app import app
from google.appengine.ext.webapp import util
util.run_wsgi_app(app)
