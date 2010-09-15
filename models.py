from flask import session

from google.appengine.ext import db
from google.appengine.api import memcache

import logging

# A Mumble for iOS Diagnostic Report
class DiagnosticReport(db.Model):
	# General
	submit_date = db.DateTimeProperty()
	# System
	device = db.StringProperty()
	system = db.StringProperty()
	udid = db.StringProperty()
	# Application
	version = db.StringProperty()
	gitrev = db.StringProperty()
	build_date = db.DateTimeProperty()
	time_since_launch = db.FloatProperty()
	# Audio
	preprocessor_avg_runtime = db.IntegerProperty()


# A download
class Download(db.Model):
	# The blobstor key identifying the data of this download
	blobkey = db.StringProperty(required=True)
	# The filename this download should be identified as
	filename = db.StringProperty(required=True)
	# Number of downloads
	downloads = db.IntegerProperty(required=True)
	# SHA1 sum of the blob
	sha1sum = db.StringProperty(required=True)
	# The date that this download was 'released'
	release_date = db.DateTimeProperty(required=True)


# A beta release download
class BetaRelease(Download):
	# Build date
	build_date = db.DateTimeProperty(required=True)
	# Git revision
	gitrev = db.StringProperty(required=True)
	# Version
	version = db.StringProperty(required=True)
	# Provisioned UDIDs
	udids = db.StringListProperty()

	# Get the latest (as in release date) BetaRelease from the datastore.
	@classmethod
	def get_latest_release_from_datastore(cls):
		query = BetaRelease.all()
		query.order('-release_date')
		return query.get()

	# Set the latest release (stored in memcache)
	@classmethod
	def set_latest_release(cls, key):
		memcache.set('betarelease-latest-key', str(key), 86400)
	
	# Get the latest (as in date) BetaRelease using a memcache stored key.
	# If that fails, we will query the datastore for the latest release, and
	# update our memcache appropriately.
	@classmethod
	def get_latest_release(cls):
		key = memcache.get('betarelease-latest-key')
		if not key:
			br = BetaRelease.get_latest_release_from_datastore()
			if not br:
				logging.warning('Unable to get latest release from datastore.')
				return None
			memcache.set('betarelease-latest-key', str(br.key()), 86400)
			return br
		else:
			return BetaRelease.get(key)
	
	# Get the download URL for this BetaRelease.
	def get_download_url(self):
		# We shouldn't hardcode this.
		return '/download/files/%s' % (self.filename)


# A beta participant
class BetaUser(db.Model):
	SERVICE_OPENID = 0
	SERVICE_FACEBOOK = 1
	SERVICE_TWITTER = 2

	# Service User identifier
	sid = db.StringProperty(required=True)
	# Service that the user is authenticated through
	service = db.IntegerProperty(required=True)
	# Full name of the user
	name = db.StringProperty()
	# Is the user an administrator?
	admin = db.BooleanProperty(required=True)
	# Last login
	lastlogin = db.DateTimeProperty(required=True)
	# The UDID of the users device
	udid = db.StringProperty()
	# A device describing the device matching the UDID above
	devtype = db.StringProperty()
	# Wants to participate?
	participate = db.BooleanProperty()
	# The user's email address (for recovery purposes)
	email = db.StringProperty()
	# User's beta test "other comments" -- why should we pick *them*?
	comments = db.StringProperty(multiline=True)
	# Has the user been picked for the beta?
	inbeta = db.BooleanProperty(default=False)
	# Email notifications
	emailnotify = db.BooleanProperty(default=False)
	# OS version
	osver = db.StringProperty()

	# Get the name of the user. Handles None names by giving a
	# nicer display name such as 'Unknown User'.
	def get_name(self):
		if self.name is None:
			return 'Unknown User'
		else:
			return self.name

	# Lookup a BetaUser by service and sid
	@classmethod
	def get_service_user(cls, service, sid):
		query = BetaUser.all()
		query.filter('sid =', sid)
		query.filter('service =', service)
		return query.get()

	# Lookup a Facebook-authenticating BetaUser using the person's
	# Facebook ID#
	@classmethod
	def get_facebook_user(cls, sid):
		return cls.get_service_user(BetaUser.SERVICE_FACEBOOK, sid)

	# Lookup a Twitter-authenticating BetaUSer using that person's
	# Twitter userid.
	@classmethod
	def get_twitter_user(cls, sid):
		return cls.get_service_user(BetaUser.SERVICE_TWITTER, sid)
	
	# Lookup a OpenID-authenticating BetaUser using that person's
	# OpenID identity string.
	@classmethod
	def get_openid_user(cls, sid):
		return cls.get_service_user(BetaUser.SERVICE_OPENID, sid)
	
	# Gets the currently logged-in BetaUser
	@classmethod
	def get_current_user(cls):
		key = session.get('betauser', None)
		if key:
			return cls.get(key)
		return None
	
	# Logs out the currently logged-in BetaUser. For OpenID authenticating
	# users, a regular AppEngine user-logout is probably also a good idea.
	@classmethod
	def logout(cls):
		session.pop('betauser', None)

# A crash report
class CrashReport(db.Model):
	# The user who submitted the report
	user = db.ReferenceProperty(BetaUser, required=True)
	# The text of the crash report
	data = db.TextProperty(required=True)
	# Whether or not the CrashReport has been symbolicated (because TextProperties are not filterable)
	symbolicated = db.BooleanProperty(default=False)
	# The symbolicated data
	symbolicated_data = db.TextProperty(default='')
