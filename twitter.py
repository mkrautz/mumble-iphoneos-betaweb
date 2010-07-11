from flask import redirect, session, abort, request, url_for

import cgi
import urllib
import oauth2 as oauth
import logging
import datetime

import settings
from models import BetaUser

callback_url = 'https://mumble-ios.appspot.com/login/twitter/callback'

# Initiate an OAuth 1.x authentication through Twitter
def login():
	# Request a request token
	consumer = oauth.Consumer(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET)
	client = oauth.Client(consumer)
	resp, content = client.request('https://api.twitter.com/oauth/request_token', 'GET')
	if resp['status'] != '200':
		abort(404)
	request_token = dict(cgi.parse_qsl(content))

	# Store our request token as a session variable. We'll need this
	# when we get called back by Twitter.
	session['twitter-req-token'] = request_token

	# Redirect to Twitter's authenticate endpoint.
	return redirect('https://api.twitter.com/oauth/authenticate?' + urllib.urlencode({
		'oauth_token': request_token['oauth_token'],
		'oauth_callback_url': callback_url,
	}))

# Twitter OAuth authenticate callback
def finish_login():
	# Get the token from the request itself (although we've stored it in a session variable)
	code = request.args.get('oauth_token', None)
	if code:
		# Make sure the passed-in code and our session-stored code match up.
		if session['twitter-req-token']['oauth_token'] != code:
			session.pop('twitter-req-token', None)
			# fixme(mkrautz): Show a page explaining what went wrong, instead.
			abort(404)

		# Set up our client object to fetch our access token
		token = oauth.Token(code, session['twitter-req-token']['oauth_token_secret'])
		consumer = oauth.Consumer(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET)
		client = oauth.Client(consumer, token)
		# Get the access token
		resp, content = client.request('https://api.twitter.com/oauth/access_token', 'GET')
		data = dict(cgi.parse_qsl(content))

		# Get existing or create a new user.
		bu = BetaUser.get_twitter_user(data['user_id'])
		if not bu:
			bu = BetaUser(sid=data['user_id'], service=BetaUser.SERVICE_TWITTER, name=data['screen_name'], admin=False, lastlogin=datetime.datetime.now())
			bu.udid = None
		bu.lastlogin = datetime.datetime.now()
		bu.put()

		# Store the key for the currently logged-in betauser.
		session['betauser'] = bu.key()
		session.pop('twitter-req-token', None)
		session.permanent = True

		# fixme(mkrautz): See comment about the same thing in facebook.py.
		return redirect('http://mumble-ios.appspot.com')

	session.pop('twitter-req-token', None)
	abort(404)
