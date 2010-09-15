from flask import Flask, g, abort, request
from google.appengine.api import users as gaeusers

import logging
from functools import wraps
from settings import GAE_REMOTEAPI_SECRET

from models import BetaUser

# Decorator that requires that a user not be logged in to be
# granted access. We use this to disallow users that are already
# logged in to access login URLs. They need to log out first.
def requires_notlogin(f):
	@wraps(f)
	def decorated(*args, **kwargs):
		logging.info('in decorated')
		if g.betauser:
			abort(404)
		return f(*args, **kwargs)
	return decorated

# Decorator that requires that a user be logged in to be
# granted access.
def requires_login(f):
	@wraps(f)
	def decorated(*args, **kwargs):
		if g.betauser is None:
			abort(404)
		return f(*args, **kwargs)
	return decorated

# Decorator that requires the currently logged-in user to
# be an admin to be granted access.
def requires_admin(f):
	@wraps(f)
	def decorated(*args, **kwargs):
		if not g.betauser or not g.betauser.admin:
			abort(404)
		return f(*args, **kwargs)
	return decorated

# Decorator that requires the currently logged-in user to be
# marked as an admin by the GAE users service.
def requires_gaeadmin(f):
	@wraps(f)
	def decorated(*args, **kwargs):
		if not gaeusers.is_current_user_admin():
			abort(404)
		return f(*args, **kwargs)
	return decorated

# Decorator that requires a valid remote api key
def requires_remoteapi(f):
	@wraps(f)
	def decorated(*args, **kwargs):
		rkey = request.headers.get('X-RemoteAPI-Key', None)
		if rkey is None:
			abort(404)
		if rkey != GAE_REMOTEAPI_SECRET:
			abort(404)
		return f(*args, **kwargs)
	return decorated
