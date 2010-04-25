from flask import Flask, render_template
from django.utils.timesince import timesince

import os
import logging

app = Flask(__name__)
if not app.jinja_env.filters.has_key('timesince'):
	app.jinja_env.filters['timesince'] = timesince
logging.info(app.jinja_env)

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

@app.route('/')
def index():
	try:
		import images
		bg = images.background
		topbar = images.topbar
	except ImportError:
		bg = '/static/bg.png'
		topbar = '/static/topbar.png'

	commits = memcache.get('commits', namespace='frontpage')
	if not commits:
		commits = get_latest_commits()
		if not memcache.add('commits', commits, 60*60, namespace='frontpage'):
			logging.warning('Could not add commits to memcache')

	return render_template('index.html', bgurl=bg, topbarurl=topbar, commits=commits)

if __name__ == '__main__':
	app.run()
