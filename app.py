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

from google.appengine.api import memcache

def get_latest_commits(limit=5):
	commits = []
	commits.extend(github.commits('mkrautz', 'mumble-iphoneos', limit=10))
	commits.extend(github.commits('mkrautz', 'mumble-iphoneos-betaweb', limit=10))
	commits.extend(github.commits('mkrautz', 'mumblekit', limit=10))

	def datesort(d1, d2):
		if d1['date'] > d2['date']:
			return -1
		elif d1['date'] < d2['date']:
			return 1
		else:
			return 0
	commits.sort(datesort)
	return commits[:limit]

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

	commits = memcache.get('commits', namespace='frontpage')
	if not commits:
		commits = get_latest_commits()
		if not memcache.add('commits', commits, 60*60, namespace='frontpage'):
			logging.warning('Could not add commits to memcache')

	return render_template('index.html', bgurl=bg, topbarurl=topbar, commits=commits)

if __name__ == '__main__':
	app.run()
