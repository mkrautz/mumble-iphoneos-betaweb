from google.appengine.ext import blobstore
from werkzeug import Response
import cgi
import zipfile
import datetime
import hashlib
from cStringIO import StringIO
from external.bplist import BPlistReader

# Parse a date in our 'standard' format.
def parse_date(str):
	try:
		return datetime.datetime.strptime(str.rstrip(), '%Y-%m-%d %H:%M:%S')
	except:
		return None

# Parse a float string. Return a float value on success, or None on failure.
def parse_float(str):
	try:
		return float(str.rstrip())
	except ValueError:
		return None

# Parse an int string. Return an int value on success, or None on failure.
def parse_int(str):
	try:
		return int(str.rstrip())
	except ValueError:
		return None

# Get the list of blob keys from an AppEngine BlobStore upload 'callback'.
def get_request_blobinfos(request):
	fields = cgi.FieldStorage(request.input_stream, environ=request.environ)
	keys = []
	for key in fields.keys():
		field = fields[key]
		if field.type_options.has_key('blob-key'):
			keys.append(field.type_options['blob-key'])
	return blobstore.BlobInfo.get(keys)

# Create a Werkzeug response in the form that AppEngine understands as
# a BlobStore serve response.
# We currently do not support ranged GETs (which the official webapp framework implementation
# does), but this should be good enough for now.
def create_blobinfo_response(blobinfo, filename=None, mimetype='application/octet-stream'):
	if not mimetype:
		mimetype = blobinfo.content_type
	if not filename:
		filename = blobinfo.filename
	rsp = Response(None, 200)
	rsp.headers[blobstore.BLOB_KEY_HEADER] = blobinfo.key()
	rsp.headers['Content-Type'] = mimetype
	rsp.headers['Content-Disposition'] = 'attachment;filename=%s' % filename
	return rsp

# Return the contents of a BetaRelease's Info.plist
# as a Python dictionary.
def info_plist_for_betarelease(blobkey):
	dict = None
	bs = blobstore.BlobReader(blobkey)
	zf = zipfile.ZipFile(bs)
	contents = zf.infolist()
	for entry in contents:
		fn = entry.filename
		if fn == 'Payload/Mumble.app/Info.plist':
			data = zf.read(fn)
			dict = BPlistReader.plistWithString(data)
	return dict

# Return the sha1sum of a stored blob
def get_blob_sha1sum(blobkey):
	bs = blobstore.BlobReader(blobkey)
	if bs:
		sha1sum = hashlib.sha1()
		while True:
			buf = bs.read(1024)
			if not buf:
				break
			sha1sum.update(buf)
		return sha1sum.hexdigest()
	return None
