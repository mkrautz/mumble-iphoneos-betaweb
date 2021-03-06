from flask import Flask, g, abort, render_template, request, redirect, session, url_for

from django.utils.timesince import timesince as django_timesince
from django.template.defaultfilters import date as django_date
from django.utils import simplejson as json

from werkzeug import Response

from google.appengine.api import memcache
from google.appengine.api import users as gaeusers
from google.appengine.api import mail
from google.appengine.ext import blobstore
from google.appengine.api.labs import taskqueue
from google.appengine.ext import db

import os
import logging
import datetime
import plistlib
import cStringIO
import zipfile
import cgi

import settings
app = Flask(__name__)
app.secret_key = settings.APP_SECRET_KEY 

if not app.jinja_env.filters.has_key('timesince'):
    app.jinja_env.filters['timesince'] = django_timesince
if not app.jinja_env.filters.has_key('date'):
    app.jinja_env.filters['date'] = django_date

import github
import twitter
import facebook
from util import get_request_blobinfos, create_blobinfo_response, info_plist_for_betarelease, get_blob_digest
from util import extract_mobileprovision, udids_for_mobileprovision
from util import parse_date_epoch, parse_float, parse_int
from decorators import requires_notlogin, requires_login, requires_admin, requires_gaeadmin, requires_remoteapi
from models import DiagnosticReport, BetaRelease, BetaUser, CrashReport
from external.bplist import BPlistReader

# Before-request handler to add the currently logged-in
# user to the global object.
@app.before_request
def before_request():
    g.betauser = BetaUser.get_current_user()

def get_latest_commits(limit=5):
    commits = []
    commits.extend(github.commits('mkrautz', 'mumble-iphoneos', limit=10))
    commits.extend(github.commits('mkrautz', 'mumble-iphoneos-betaweb', limit=10))
    commits.extend(github.commits('mkrautz', 'mumblekit', limit=10))
    commits.extend(github.commits('mkrautz', 'mumble-ios-crashreporter', limit=10))

    def datesort(d1, d2):
        if d1['date'] > d2['date']:
            return -1
        elif d1['date'] < d2['date']:
            return 1
        else:
            return 0
    commits.sort(datesort)
    return commits[:limit]

def get_emailable_betausers():
    query = BetaUser.all()
    query.filter('inbeta =', True)
    query.filter('emailnotify =', True)
    bu = query.fetch(200)
    return [ u.email for u in bu ]

def send_email_notification(subject, body):
    taskqueue.add(url=url_for('betauser_email_notification'), payload=json.dumps({
        'subject':  subject,
        'body':     body,
    }), headers={
        'Content-Type': 'application/json'
    })

@app.route('/_github_push', methods=['GET', 'POST'])
def github_push():
    commits = get_latest_commits()
    if not memcache.set('commits', commits, namespace='frontpage'):
        logging.warning('Could not update commits in memcache')
    return ''

# Template-rendered CSS for all our pages.
@app.route('/betaweb.css')
def stylesheet():
    try:
        import images
        bg = images.background
        topbar = images.topbar
    except ImportError:
        bg = '/static/bg.png'
        topbar = '/static/topbar.png'
    embedded = request.values.get('embedded')
    buf = render_template('betaweb.css', bgurl=bg, topbarurl=topbar, embedded=bool(embedded))
    return Response(buf, mimetype='text/css')

@app.route('/')
def index():
    commits = memcache.get('commits', namespace='frontpage')
    if not commits:
        commits = get_latest_commits()
        if not memcache.add('commits', commits, namespace='frontpage'):
            logging.warning('Could not add commits to memcache')

    # Possible race... Do we care?
    session.pop('login-redirect-url', None)

    return render_template('index.html',
                           commits=commits)

# AppEngine's default login URL. We get redirected here from AppEngine things that
# require login.
@app.route('/_ah/login_required', methods=['GET'])
def gae_login_required():
    abort(404)

# OpenID login page.
@app.route('/login/openid', methods=['GET'])
@requires_notlogin
def login_openid():
    continue_url = request.values.get('continue', url_for('login_openid_callback'))
    openid_url = request.values.get('openid', None)
    logging.info(openid_url)
    logging.info(continue_url)
    if not openid_url:
        return render_template('login.html', continue_url=continue_url)
    else:
        return redirect(gaeusers.create_login_url(continue_url, None, openid_url))

# OpenID callback url (i.e. continue url).
# We use the continue url to check if the user successfully authenticated via OpenID.
@app.route('/login/openid/callback', methods=['GET'])
@requires_notlogin
def login_openid_callback():
    # Convert a logged in GAE OpenID user to a BetaUser...
    user = gaeusers.get_current_user()
    if user:
        # First, check if there's already a BetaUser for this OpenID identity...
        bu = BetaUser.get_openid_user(user.federated_identity())
        if not bu:
            bu = BetaUser(sid=user.federated_identity(), service=BetaUser.SERVICE_OPENID, name=None, admin=False, lastlogin=datetime.datetime.now())
        bu.lastlogin = datetime.datetime.now()
        bu.put()

        # Store betauser key in our session cookie
        session['betauser'] = bu.key()
        session.permanent = True
    else:
        logging.warning('No OpenID user logged in.')

    # Should we redirect to a specific page?
    login_redirect_url = session.pop('login-redirect-url', None)
    if login_redirect_url:
        return redirect(login_redirect_url)
    # Redirect to front page
    else:
        return redirect('/')

# Twitter login page.
@app.route('/login/twitter', methods=['GET'])
@requires_notlogin
def login_twitter():
    return twitter.login()

# Twitter OAuth callback. Fetch access token, user info, etc.
@app.route('/login/twitter/callback', methods=['GET'])
@requires_notlogin
def login_twitter_callback():
    return twitter.finish_login()

# Facebook login page.
@app.route('/login/facebook', methods=['GET'])
@requires_notlogin
def login_facebook():
    return facebook.login()

# Facebook OAuth callbcak. Fetch user info, etc.
@app.route('/login/facebook/callback', methods=['GET'])
@requires_notlogin
def login_facebook_callback():
    return facebook.finish_login()

# Logout of a BetaUser
@app.route('/logout', methods=['GET'])
@requires_login
def logout():
    # Make sure we're logged out of any OpenID accounts (internal App Engine thingamajig).
    return redirect(gaeusers.create_logout_url(url_for('logout_callback')))

# Logout callback. Perform our own logout procedures after AppEngine has 
# made sure that the logged-in user is marked as logged out in there.
@app.route('/logout/callback', methods=['GET'])
@requires_login
def logout_callback():
    BetaUser.logout()
    login_redirect_url = session.pop('login-redirect-url', None)
    if login_redirect_url:
        return redirect(login_redirect_url)
    else:
        return redirect('/')

# Diagnostic report url for iOS client.
@app.route('/diagnostics', methods=['POST'])
def diagnostics_submit():
    required = set(('device', 'operating-system', 'udid', 'version', 'git-revision',
                    'build-date-epoch', 'time-since-launch', 'preprocessor-avg-runtime'))
    if not required.issubset(set(request.form.keys())):
        abort(404)

    report = DiagnosticReport()
    report.submit_date = datetime.datetime.utcnow()
    report.device = request.form['device'].rstrip()
    report.system = request.form['operating-system'].rstrip()
    report.udid = request.form['udid'].rstrip()
    report.version = request.form['version'].rstrip()
    report.gitrev = request.form['git-revision'].rstrip()
    report.build_date = parse_date_epoch(request.form['build-date-epoch'])
    report.time_since_launch = parse_float(request.form['time-since-launch'])
    report.preprocessor_avg_runtime = parse_int(request.form['preprocessor-avg-runtime'])
    report.put()

    return ''

# This handler servces a property list that the beta client queries to figure
# out if a new beta was released. We use this to nag peopole into upgrading
# to the latest betas (as they should!)
@app.route('/latest.plist', methods=['GET'])
def latest_release():
    br = BetaRelease.get_latest_release()
    buf = cStringIO.StringIO()
    plistlib.writePlist({
        'MumbleGitRevision':   br.gitrev,
        'MumbleBuildDate':     br.build_date,
    }, buf)
    return Response(buf.getvalue(), mimetype='text/plist')

@app.route('/participant-queue', methods=['GET'])
@requires_admin
def participant_queue():
    fetch = request.values.get('fetch', 'all')
    bu = BetaUser.all()
    bu.filter('participate =', True)
    users = bu.fetch(100)
    queue = []
    if fetch == 'all':
        queue = users
    elif fetch == 'notinbeta':
        queue = [u for u in users if not u.inbeta]
    elif fetch == 'inbeta':
        queue = [u for u in users if u.inbeta]
    return render_template('profile-list.html', queue=queue)

@app.route('/beta-participants.csv', methods=['GET'])
@requires_admin
def beta_participants_csv():
    sep = ','
    if request.values.get('excel', None) is not None:
        sep = ';'
    notprov = request.values.get('notprovisioned', None) is not None
    bu = BetaUser.all()
    bu.filter('participate =', True)
    testers = [u for u in bu if u.inbeta]
    buf = cStringIO.StringIO()
    buf.write('# name, email, udid, devtype\n')
    for u in testers:
        br = BetaRelease.get_latest_release()
        if notprov and br.udids is not None and u.udid in br.udids:
            continue
        s = sep.join((u.name, u.email, u.udid, u.devtype))+'\n'
        buf.write(s.encode('utf-8'))
    return Response(buf.getvalue(), mimetype='text/csv')


@app.route('/viewprofile', methods=['GET'])
@requires_admin
def view_profile():
    key = request.values.get('key', None)
    if key is None:
        abort(404)
    user = BetaUser.get(key)
    return render_template('viewprofile.html', user=user)

@app.route('/beta-enroll', methods=['POST'])
@requires_admin
def beta_enroll():
    key = request.values.get('key', None)
    if key is None:
        abort(404)
    user = BetaUser.get(key)
    user.inbeta = True
    user.save()
    if user.emailnotify:
        taskqueue.add(url=url_for('user_beta_status_change'), params={
            'user-key': user.key(),
        })
    return redirect(url_for('view_profile', key=key))

@app.route('/beta-remove', methods=['POST'])
@requires_admin
def beta_remove():
    key = request.values.get('key', None)
    if key is None:
        abort(404)
    user = BetaUser.get(key)
    user.inbeta = False
    user.save()
    if user.emailnotify:
        taskqueue.add(url=url_for('user_beta_status_change'), params={
            'user-key': user.key(),
        })
    return redirect(url_for('view_profile', key=key))

@app.route('/upload', methods=['GET'])
@requires_admin
def upload():
    return render_template('upload.html', url=blobstore.create_upload_url('/upload-done'))

@app.route('/upload-done', methods=['POST'])
@requires_admin
def upload_handler():
    # Add a task for handling the longer-running creation process
    # (Look through the zip archive, populate the datastore with some
    # metadata, etc.)
    bi = get_request_blobinfos(request) 
    for blob in bi:
        taskqueue.add(url=url_for('create_beta_release'), params={
            'blob-key': blob.key()
        })

    # Redirect to front page for now...
    rsp = Response(None, 301)
    rsp.headers['Location'] = url_for('index')
    return rsp

# Download page
@app.route('/download')
@requires_login
def download():
    if not g.betauser.inbeta:
        abort(404)

    # Get the latest release
    latest_release = BetaRelease.get_latest_release()

    # Get older releases
    query = BetaRelease.all()
    query.order('-release_date')
    older_releases = query.fetch(limit=20)
    for rel in older_releases:
        if rel.key() == latest_release.key():
            older_releases.remove(rel)
            break
    return render_template('download.html',
                    latest_release=latest_release,
                    older_releases=older_releases)

# Download a BetaRelease by its filename.
@app.route('/download/files/<filename>', methods=['GET'])
@requires_login
def download_by_filename(filename):
    if not g.betauser.inbeta:
        abort(404)
    return BetaRelease.get_blobinfo_response_for_fn(filename)

# Schedule a re-do of the post-release stuff for a BetaRelease
@app.route('/betarelease/redo/<blobkey>', methods=['GET'])
@requires_admin
def recreate_beta_release(blobkey):
    taskqueue.add(url=url_for('create_beta_release'), params={
                'blob-key': blobkey,
    })
    return 'scheduled recreate for %s' % blobkey

# Task handler for post-upload release work. This handler will add
# a new BetaRelease to the datastore and populate it with data from
# the app bundle's plist.
@app.route('/_tasks/create-release', methods=['POST'])
def create_beta_release():
    blobkey = request.values.get('blob-key', None)
    if blobkey:
        # The iOS distributable packages (.ipa files) are simply
        # zip archives with an application bundle in them. Let's
        # try to read from the release's Info.plist to get the
        # data we need.
        d = info_plist_for_betarelease(blobkey)
        if d:
            identifier = d.get('CFBundleIdentifier', '')
            version = d.get('CFBundleVersion', '')
            gitrev = d.get('MumbleGitRevision', '')
            builddate = d.get('MumbleBuildDate', None)
            datepart = ''
            if builddate is not None:
                datepart = builddate.strftime('%Y-%m-%d-%H%M')
            fn = 'MumbleiOS-%s--%s--%s.ipa' % (version, datepart, gitrev)
            sha1sum = get_blob_digest(blobkey, 'sha1')
            md5sum = get_blob_digest(blobkey, 'md5')

            # Extract the embedded mobile provisioning profile in the betarelease
            mprov = extract_mobileprovision(blobkey)
            # Get the embedded.mobileprovision from the uploaded ipa
            # and extract the list of provisioned UDIDs.
            udids = udids_for_mobileprovision(mprov)

            # Does a BetaRelease for this blobkey already exist? If so, use that.
            query = BetaRelease.all()
            query.filter('blobkey =', blobkey)
            rel = query.get()
            if rel is not None:
                rel.filename = fn
                rel.build_date = builddate
                rel.gitrev = gitrev
                rel.version = version
                rel.sha1sum = sha1sum
                rel.udids = udids
                rel.mobileprovision = mprov
                rel.identifier = identifier
                rel.wmanifest = None
                rel.save()

                logging.info('Updated already-existing BetaRelease')
            else:
                rel = BetaRelease(blobkey=blobkey,
                                  filename=fn,
                                  build_date=builddate,
                                  gitrev=gitrev,
                                  version=version,
                                  downloads=0,
                                  release_date=datetime.datetime.now(),
                                  sha1sum=sha1sum,
                                  udids=udids,
                                  identifier=identifier,
                                  mobileprovision=mprov)
                rel.put()

                subject='[Mumble iOS Beta] New Beta Release: %s %s' % (rel.version, rel.gitrev)
                body='''Hello Mumble for iOS beta tester!

You are receiving this email to notify you that a new beta release is available on the Mumble for iOS Beta Portal.

Download it from https://mumble-ios.appspot.com%s

Enjoy,
Mumble for iOS Beta Team''' % (rel.get_download_url())
                send_email_notification(subject, body)

                # Make sure memcache is up-to-date.
                BetaRelease.set_latest_release(rel.key())

                logging.info('Successfully stored new BetaRelease.');
        else:
            logging.warning('Unable to parse bplist.')
    else:
        logging.warning('No blob-key supplied. Nothing to do.')

    return ''

# Task handler for emailing all notification-enabled BetaUsers
@app.route('/_tasks/betauser-email-notification', methods=['POST'])
def betauser_email_notification():
    data = request.stream.read()
    params = json.loads(data)
    emails = get_emailable_betausers()
    mail.send_mail(sender='notify@mumble-ios.appspotmail.com',
                   to='devnull@mumble-ios.appspotmail.com',
                   bcc=emails,
                   subject=params.get('subject', 'Mumble for iOS Beta Email Notification'),
                   body=params.get('body', ''))
    return ''

# Task handler for incrementing the download counter for BetaReleases.
@app.route('/_tasks/incr-download-counter', methods=['POST'])
def beta_release_downloaded():
    blobkey = request.values.get('blob-key', None)
    if blobkey:
        query = BetaRelease.all()
        query.filter('blobkey =', blobkey)
        release = query.get()
        if release:
            def incr():
                logging.info('running incr()')
                release.downloads += 1
                release.put()
            db.run_in_transaction(incr)
        else:
            logging.warning('No BetaRelease with blobkey=%s found.' % blobkey)
    else:
        logging.warning('No-blob-key supplied to task handler. Nothing to do.')
    return ''

# Task handler for when a user's beta status changes
@app.route('/_tasks/user-beta-status-change', methods=['POST'])
def user_beta_status_change():
    key = request.values.get('user-key', None)
    if key:
        user = BetaUser.get(key)
        if user:
            status = 'Not Participating'
            if user.inbeta:
                status = 'Participating'
            mail.send_mail(sender='notify@mumble-ios.appspotmail.com',
                      to=user.email,
                      subject='[Mumble iOS Beta] Beta Status Change',
                      body='''Hello %s!

You are receiving this email to notify you that your beta status on the Mumble for iOS Beta Portal has changed.

Your new status is '%s'

Please visit the portal for further information.

Thanks,
Mumble for iOS Beta Team''' % (user.name, status))
    return ''


@app.route('/profile')
@requires_login
def profile():
    return render_template('profile.html')

@app.route('/profile/update', methods=['POST'])
@requires_login
def update_profile():
    comments = request.values.get('comments').encode('utf-8')
    if len(comments) > 500:
        abort(404)

    g.betauser.name = request.values.get('name')
    g.betauser.email = request.values.get('email')
    g.betauser.udid = request.values.get('udid')
    g.betauser.devtype = request.values.get('devtype')
    g.betauser.osver = request.values.get('osver')
    g.betauser.emailnotify = request.values.get('emailnotify', None) is not None
    g.betauser.participate = request.values.get('participate', None) is not None
    g.betauser.comments = request.values.get('comments')
    g.betauser.save()
    return redirect(url_for('profile'))

@app.route('/faq')
@requires_login
def faq():
    return render_template('faq.html')

@app.route('/reportbug')
@requires_login
def reportbug():
    return render_template('reportbug.html')

@app.route('/reportcrash')
@requires_login
def reportcrash():
    return render_template('reportcrash.html')

@app.route('/crashreporter')
def crashreporter():
    if not session.has_key('betauser'):
        return redirect(url_for('crashreporter_login'))
    return render_template('crashreporter.html')

@app.route('/crashreporter/send', methods=['POST'])
def crashreporter_send_log():
    # Only registered users can submit crash reports
    if not session.has_key('betauser'):
        abort(404)

    data = request.stream.read()

    # Add the report to the datastore
    cr = CrashReport(data=data, user=g.betauser)
    cr.put()

    return ''

@app.route('/crashreporter/help', methods=['GET'])
def crashreporter_help():
    return render_template('crashreporter-help.html')

@app.route('/crashreporter/login')
def crashreporter_login():
    session['login-redirect-url'] = url_for('crashreporter')
    return render_template('crashreporter-login.html')

@app.route('/crashreporter/logout')
def crashreporter_logout():
    session['login-redirect-url'] = url_for('crashreporter')
    return redirect(url_for('logout'))

@app.route('/crashreporter/fetch-unsymbolicated')
@requires_remoteapi
def crashreporter_fetch_unsymbolicated():
    query = CrashReport.all()
    query.filter('symbolicated !=', True)
    reports = query.fetch(100)

    if len(reports) == 0:
        return ''

    memzip = cStringIO.StringIO()
    zf = zipfile.ZipFile(memzip, 'w')
    for report in reports:
        zf.writestr(str(report.key()), report.data)
    zf.close()

    return Response(memzip.getvalue(), mimetype='application/zip')

@app.route('/crashreporter/push-symbolicated', methods=['POST'])
@requires_remoteapi
def crashreporter_push_symbolicated():
    data = request.stream.read()
    buf = cStringIO.StringIO(data)
    zf = zipfile.ZipFile(buf, 'r')
    for i in zf.infolist():
        key, ext = os.path.splitext(i.filename)
        contents = zf.read(i.filename)
        cr = CrashReport.get(key)
        if cr is not None:
            if ext == '' and not cr.symbolicated:
                cr.symbolicated = True
                cr.symbolicated_data = contents
            elif ext == '.plist':
                d = BPlistReader.plistWithString(contents)
                query = BetaRelease.all()
                query.filter('gitrev =', d.get('MumbleGitRevision', None))
                query.filter('build_date =', d.get('MumbleBuildDate', None))
                br = query.get()
                if br is not None:
                    cr.betarelease = br
            cr.save()
    zf.close()

    return ''

@app.route('/crashreports', methods=['GET'])
@requires_admin
def view_crashreport_listing():
    query = CrashReport.all()
    query.filter('symbolicated =', True)
    reports = query.fetch(150)
    return render_template('crashreport-list.html', reports=reports)

@app.route('/crashreports/view/<key>', methods=['GET'])
@requires_admin
def view_crashreport(key):
    cr = CrashReport.get(key)
    if cr is None:
        abort(404)
    return Response(cr.symbolicated_data, mimetype='text/plain')

@app.route('/betamail', methods=['GET', 'POST'])
@requires_admin
def betamail():
    if request.method == 'GET':
        return render_template('betamail.html')
    elif request.method == 'POST':
        subject = request.values.get('subject', None)
        body = request.values.get('body', None)
        send_email_notification(subject, body)
        return redirect(url_for('betamail'))

# Wireless distribution index page.
@app.route('/wdist', methods=['GET'])
def wdist():
    latest = BetaRelease.get_latest_release()
    if latest is None:
        ver = gitrev = None
    else:
        ver = latest.version
        gitrev = latest.gitrev
    return render_template('wdist.html', version=ver, gitrev=gitrev)

# Fetch the wdist manifest.
@app.route('/wdist/manifest')
def wdist_get_manifest():
    latest = BetaRelease.get_latest_release()
    return Response(latest.get_wireless_manifest(), mimetype='text/plist')

# Download a wdist BetaRelease by its filename.
@app.route('/wdist/app.ipa', methods=['GET'])
def wdist_download_app():
    latest = BetaRelease.get_latest_release()
    return latest.get_blobinfo_response()

if __name__ == '__main__':
    app.run()
