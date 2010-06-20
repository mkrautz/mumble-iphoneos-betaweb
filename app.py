from flask import Flask, abort, render_template, request
from django.utils.timesince import timesince

import os
import logging
import datetime

app = Flask(__name__)
if not app.jinja_env.filters.has_key('timesince'):
	app.jinja_env.filters['timesince'] = timesince
logging.info(app.jinja_env)

import github
from models import DiagnosticReport

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

@app.route('/_github_push', methods=['POST'])
def github_push():
	commits = get_latest_commits()
	if not memcache.set('commits', commits, namespace='frontpage'):
		logging.warning('Could not update commits in memcache')
	return ''

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
		if not memcache.add('commits', commits, namespace='frontpage'):
			logging.warning('Could not add commits to memcache')

	return render_template('index.html', bgurl=bg, topbarurl=topbar, commits=commits)

@app.route('/diagnostics', methods=['POST'])
def diagnostics_submit():
	required = set(('device', 'operating-system', 'udid', 'version', 'git-revision',
	                'build-date', 'preprocessor-avg-runtime'))
	if required != set(request.form.keys()):
		return ''

	report = DiagnosticReport()
	report.submit_date = datetime.datetime.now()
	report.device = request.form['device'].rstrip()
	report.system = request.form['operating-system'].rstrip()
	report.udid = request.form['udid'].rstrip()
	report.version = request.form['version'].rstrip()
	report.gitrev = request.form['git-revision'].rstrip()
	report.build_date = request.form['build-date'].rstrip()
	try:
		report.preprocessor_avg_runtime = int(request.form['preprocessor-avg-runtime'].rstrip())
	except ValueError:
		report.preprocessor_avg_runtime = None
	report.put()

	return ''

if __name__ == '__main__':
	app.run()
