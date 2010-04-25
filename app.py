from flask import Flask, render_template
from django.utils.timesince import timesince

import logging

app = Flask(__name__)
if not app.jinja_env.filters.has_key('timesince'):
	app.jinja_env.filters['timesince'] = timesince
logging.info(app.jinja_env)

import os
import dataurlify
import github

def approot(p):
	return os.path.join(os.path.dirname(__file__), p)

@app.route('/')
def index():
	# Attempt to generate data-urls for some of our static assets.
	# This makes our page feel like it's loading quicker, because
	# there won't be any time where the background and the topbar
	# aren't rendered because they need to be fetched first.
	try:
		bg = dataurlify.generate(approot('static/bg.png'))
	except IOError:
		bg = '/static/bg.png'
	try:
		topbar = dataurlify.generate(approot('static/topbar.png'))
	except IOError:
		topbar = '/static/topbar.png'

	commits = github.commits('mkrautz', 'mumble-iphoneos')

	return render_template('index.html', bgurl=bg, topbarurl=topbar, commits=commits)

if __name__ == '__main__':
	app.run()
