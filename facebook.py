from flask import redirect, session, abort, request, url_for

import cgi
import urllib
import logging
import datetime

from django.utils import simplejson as json

from google.appengine.api import urlfetch

import settings
from models import BetaUser

callback_url = 'https://mumble-ios.appspot.com/login/facebook/callback'

# Initiate an OAuth2 authentication through Facebook
def login():
	return redirect('https://graph.facebook.com/oauth/authorize?client_id=%s&redirect_uri=%s' % (settings.FACEBOOK_APP_ID, callback_url))

# Finish the login
def finish_login():
	# Fetch the code we've been passed from Facebook
	code = request.args.get('code', None)
	if not code:
		# fixme(mkrautz): Show a nice page here explaining what's wrong.
		abort(404)

	# Fetch our access token
	data = urlfetch.fetch('https://graph.facebook.com/oauth/access_token?' + urllib.urlencode({
		'client_id': settings.FACEBOOK_APP_ID,
		'client_secret': settings.FACEBOOK_APP_SECRET,
		'code': code,
		'redirect_uri': callback_url,
	}))
	args = dict(cgi.parse_qsl(data.content))
	access_token = args['access_token']

	# Fetch data about the user using our acquired access token.
	data = urlfetch.fetch('https://graph.facebook.com/me?access_token=' + access_token)
	login_data = json.loads(data.content)

	# Get existing user, or create a new one.
	bu = BetaUser.get_facebook_user(login_data['id'])
	if not bu:
		bu = BetaUser(sid=login_data['id'], service=BetaUser.SERVICE_FACEBOOK, name=login_data['name'], admin=False, lastlogin=datetime.datetime.now())
		bu.udid = None
	bu.lastlogin=datetime.datetime.now()
	bu.put()

	# Set the user's BetaUser key in a cookie, so we know
	# they're logged in (and which user they're logged in as).
	session['betauser'] = bu.key()
	session.permanent = True

	# Should we redirect to a specific page?
	login_redirect_url = session.pop('login-redirect-url', None)
	if login_redirect_url:
		return redirect(login_redirect_url)
	# Redirect to front page
	else:
		# We force a redirect to http:// (which means that even users on
		# https:// connections get redirected to the non-TLS version).
		# The reason for this is that App Engine's OpenID 'federated login'
		# feature seems to break when using https://. fixme(mkrautz): Look
		# into why that is.
		return redirect('http://mumble-ios.appspot.com')
