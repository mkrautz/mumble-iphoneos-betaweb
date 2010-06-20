from google.appengine.ext import db

class DiagnosticReport(db.Model):
	# General
	submit_date = db.DateTimeProperty()
	# System
	device = db.StringProperty()
	system = db.StringProperty()
	udid = db.StringProperty()
	# Build
	version = db.StringProperty()
	gitrev = db.StringProperty()
	build_date = db.StringProperty()
	# Audio
	preprocessor_avg_runtime = db.IntegerProperty()
