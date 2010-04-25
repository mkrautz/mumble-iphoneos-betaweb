#!/usr/bin/python

import xml.dom.minidom as minidom
import urllib2
import datetime
import logging

signof = lambda x: x > 0 and 1 or -1

def parse_date(date, hd=None, md=None):
	hour = ''
	minute = ''
	colon = 0
	tz = False
	tokens = []
	for token in date:
		if colon >= 2 and token in ('-', '+'):
			tz = True
			colon = 0
		if token == ':':
			colon += 1
		if tz:
			if token == ':':
				continue
			if colon == 0:
				hour += token
			elif colon == 1:
				minute += token
			continue
		else:
			tokens.append(token)
	txt = ''.join(tokens)
	hour = int(hour)
	minute = signof(hour) * int(minute)
	dt = datetime.datetime.strptime(txt, '%Y-%m-%dT%H:%M:%S') - datetime.timedelta(hours=int(hour), minutes=int(minute))
	return dt

def commits(username, project, branch='master', limit=5):
	"""Fetch a list of GitHub commits."""
	commits = []
	web_url = 'http://github.com/%s/%s/' % (username, project)
	try:
		r = urllib2.urlopen(web_url + 'commits/%s.atom' % branch)
	except IOError:
		return commits

	xml = r.read()
	tree = minidom.parseString(xml)
	entries = tree.getElementsByTagName('entry')
	for entry in entries:
		d = {}
		d['project'] = project
		d['weburl'] = web_url
		d['url'] = entry.getElementsByTagName('link')[0].getAttribute('href')
		d['title'] = entry.getElementsByTagName('title')[0].childNodes[0].data
		date = entry.getElementsByTagName('updated')[0].childNodes[0].data
		d['date'] = parse_date(date)
		author = entry.getElementsByTagName('author')[0]
		d['author'] = author.getElementsByTagName('name')[0].childNodes[0].data
		commits.append(d)

	return commits[:limit]

if __name__ == '__main__':
	print commits('mkrautz', 'mumble-iphoneos')
