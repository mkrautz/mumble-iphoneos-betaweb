#!/usr/bin/python

from __future__ import with_statement

import sys
import base64
import mimetypes

def generate(fn, mimetype=None):
	"""Generate a data url from file at fn. If mimetype is not supplied, the function
	   will guess the mimetype to use based on the filename."""
	with open(fn, 'r') as f:
		s = f.read()
		b64s = base64.b64encode(s)
		if not mimetype:
			mimetype, extension = mimetypes.guess_type(fn)
		return 'data:%s;base64,%s' % (mimetype, b64s)

def main():
	if len(sys.argv) < 2:
		print '%s <fn> [<mimetype override>]' % sys.argv[0]
		sys.exit(1)
	target = sys.argv[1]
	mime = None
	if len(sys.argv) > 2:
		mime = sys.argv[2]

	print generate(target, mime)

if __name__ == '__main__':
	main()
