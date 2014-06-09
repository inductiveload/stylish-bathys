#! /usr/bin/python

import os, re
import glob
import mechanize
from lxml.html import fromstring
import sqlite3
import argparse

import difflib

try:
    import updaterConfig as CFG
except ImportError:
    print "Could not find config file - have you renamed \
updaterConfig.example.py to updaterConfig.py and inserted the correct \
details?"
    exit(1)

DIR = os.path.dirname(os.path.realpath(__file__))

def getStyle():
    indexFilename = os.path.join(DIR, "index")
    indexFile = open(indexFilename, 'r')

    styles = {}

    for line in indexFile:
        line = line.strip()

        # skip blanks and comments
        if not line or line[0] == '#':
            continue;

        parts = line.split('\t')

        styles[parts[1]] = {'id' : parts[0]}

    style = ''

    while style not in styles:
        style = raw_input("Style to update at userstyles: ")

    return style, styles[style]

def getStyleCss(style):
    styleDir = os.path.join(DIR, style)

    css = [x for x in os.listdir(styleDir) if x.endswith(".css")][0]

    css = os.path.join(styleDir, css)

    cssData = open(css, 'r').read()

    return cssData

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def getCssFromStylish(settingsDir, style):

    conn = sqlite3.connect(os.path.join(settingsDir,"stylish.sqlite"))

    conn.row_factory = dict_factory
    cur = conn.cursor()
    cur.execute('SELECT id,name FROM styles')

    ids = {}

    while True:
        row = cur.fetchone()
        if not row:
            break;
        ids[row['id']] = row['name']

    found = 0;
    select = ''
    for availStyle in ids:
        if style in ids[availStyle]:
            found += 1
            select = availStyle

    # no match, or can't decide
    if found != 1:
        for s in ids:
            print "%4d  %s" % (s, ids[s])

        select = '0'

        while int(select) not in ids:
            select = raw_input("\nChoose style ID: ")

    # now get the site ID and the CSS code
    cur.execute('SELECT code,idUrl FROM styles WHERE id=%s' % select)
    row = cur.fetchone()

    try:
        theId = int(row['idUrl'].split('/')[-1])
    except AttributeError:
        theId = None

    return theId, row['code']

class UserStyleUpdater():

    def __init__(self, usid):
        self.usid = usid
        self.baseUrl = "http://userstyles.org"
        self.editUrl = self.baseUrl + "/styles/%d/edit" % usid

        self.cj = mechanize.LWPCookieJar()
        self.br = mechanize.Browser()
        self.br.set_cookiejar(self.cj)

        if os.path.exists(".userstylecookies.txt"):
            self.cj.load(".userstylecookies.txt", ignore_discard=True, ignore_expires=True)

    def selectFormById(self, formId):
        formCnt = 0
        for form in self.br.forms():
            if 'id' in form.attrs and form.attrs['id'] == formId:
                self.br.form = form
                break
            formCnt += 1

        self.br.select_form(nr=formCnt)

    def login(self, username, password):

        print self.br.title()

        self.selectFormById("password-login")
        self.br["login"] = username;
        self.br["password"] = password;
        response = self.br.submit()

        self.cj.save(".userstylecookies.txt", ignore_discard=True, ignore_expires=True)

    def update(self, username, password, css):

        screenshotType = 'manual'

        while True:
            self.br.open(self.editUrl)

            if self.br.title().startswith("Login - "):
                self.login(username, password)
                self.br.open(self.editUrl)

            print self.br.title()

            self.br.select_form(nr=0)

            '''
            print css
            print self.br["style[css]"]
            return

            if self.br["style[css]"] == css:
                print "CSS is identical"
                return
            '''

            self.br["style[css]"] = css
            self.br["style[screenshot_type_preference]"] = [screenshotType]

            #print self.br.response().read()

            form = self.br.form

            for c in form.controls[:]:
                if not c.name or "fakeId" in c.name or "style_settings" in c.name:
                    form.controls.remove(c)

            print "Submitting form"

            response = self.br.submit()

            xml = fromstring(response.read())

            errors = xml.cssselect('div.errorExplanation li')

            retry = False
            for error in errors:
                if "Primary screenshot must be provided" in error.text and screenshotType == 'manual':
                    print "Using auto screenshot..."
                    screenshotType = 'auto'
                    retry = True

            if retry:
                continue

            if errors:
                print "Errors on save:"

                for error in errors:
                    print "\t" + error.text

            break
class GitUpdater():

    def __init__(self):
        pass

    def applyUpdate(self, css):

        filename = ""
        for line in css.split("\n"):
            m = re.match(r"^ \* File: *(\S+)", line)

            if m:
                filename = m.group(1)
                break

        if not filename:
            print "No filename found in source, cannot update working copy"
            return
        else:
            print "Found filename in source: %s" % filename

        filename = os.path.join(CFG.gitRepoRoot, filename)

        if os.path.exists(filename):
            print "Found the source file"
        else:
            print "Could not find the source file at %s" % filename
            return

        theFile = open(filename, "w")

        theFile.write(css.replace("\r\n", "\n"))
        theFile.close()

        print "Wrote file"


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Update user styles')

    parser.add_argument('--style', metavar='Stylefragment', type=str,
                   help='name fragment to match', default="")
    parser.add_argument('--username', metavar='USERNAME', type=str,
                   help='Userstyles username', default="")

    args = parser.parse_args()

    print "Updating %s" % args.style

    usid, css = getCssFromStylish(CFG.firefoxProfile, args.style)

    if not usid:
        print "No UserStyles ID found - maybe this hasn't been put on there yet?"
    else:
        print "User style ID: %d" % usid

        usu = UserStyleUpdater(usid)

        usu.update(CFG.username, CFG.password, css)
    print "\nUpdating working copy in the local git repo"
    gitu = GitUpdater()

    gitu.applyUpdate(css)


