#!/usr/bin/python
# package up deps for use on app engine

import os
import sys
import shutil
import tempfile
import zipfile

import plistlib
import flask
import jinja2
import werkzeug
import oauth2
import httplib2

def main():
	tmpdir = tempfile.mkdtemp()
	print ' * Using tmpdir: %s' % tmpdir

	for module in ('flask', 'jinja2', 'werkzeug', 'oauth2', 'httplib2', 'plistlib'):
		fn = sys.modules[module].__file__
		bfn = os.path.basename(fn)
		if bfn.startswith('__init__'):
			dn = os.path.dirname(fn)
			bdn = os.path.basename(dn)
			print ' * Copying dirname: %s' % bdn
			shutil.copytree(dn, os.path.join(tmpdir, bdn))
		else:
			if fn.endswith('.pyc'):
				fn = fn[:-4] + '.py'
			bfn = os.path.basename(fn)
			print ' * Copying filename: %s' % bfn
			shutil.copy(fn, os.path.join(tmpdir, os.path.join(tmpdir, bfn)))

	contents = []
	for e in os.walk(tmpdir):
		root, dirs, files = e
		contents.extend([root]+[os.path.join(root, f) for f in files if not f.endswith('.pyc')])

	zfn = 'modules.zip'
	print ' * Generating zipfile: %s' % zfn
	zf = zipfile.ZipFile(zfn, 'w')
	for c in contents:
		if not os.path.isdir(c):
			zf.write(c, c[len(tmpdir):])
	zf.close()

	print ' * Done!'

if __name__ == '__main__':
	main()
