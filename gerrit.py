#!/usr/bin/env python

import json
import os
import requests
import sys
import configparser
from optparse import OptionParser
from requests.auth import HTTPDigestAuth

version = '0.1'
CONFIG_FILENAME = os.getenv("HOME") + '/.gerrit.cfg'


def main():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILENAME)
    parser = OptionParser(usage='%prog [options] changes', version="%prog " + version)

    # Logging
    group = parser.add_option_group('Logging options')
    group.add_option('-v', '--verbose',
                     action='store_true', dest='verbose',
                     help='Print status messages to stdout')

    # Gerrit - URL
    group = parser.add_option_group('Gerrit options')
    group.add_option('-r', '--review-url', dest='review_url',
                     help='Gerrit URL', metavar='URL',
                     default=config.get("Defaults", "review_url"))

    # Gerrit - Login Data
    group.add_option('-u', '--username', dest='username',
                     help='Gerrit Username', metavar='USERNAME')
    group.add_option('-p', '--password', dest='password',
                     help='Gerrit Password', metavar='PASSWORD')

    # Changes
    group = parser.add_option_group('Changes options')
    group.add_option('-s', '--submit',
                     action='store_true', dest='submit',
                     help='Submit changes')
    group.add_option('-a', '--add-reviewers', dest='reviewers',
                     help='Add reviewers', metavar='REVIEWERS')
    group.add_option('-t', '--topic', dest='topic',
                     help='Set topic or Merge by topic', metavar='TOPIC')

    (options, args) = parser.parse_args()

    if len(args) < 1 and not options.topic:
        parser.error('You must specify either a range of commits or a topic')
        sys.exit()

    if not options.review_url:
        parser.error('Review URL must be set')
        sys.exit()

    if options.username:
        username = options.username
    else:
        try:
            username = config.get(options.review_url, "username")
        except:
            parser.error('Username must be set')
            sys.exit()

    if options.password:
        password = options.password
    else:
        try:
            password = config.get(options.review_url, "password")
        except:
            parser.error('Password must be set')
            sys.exit()

    auth = HTTPDigestAuth(username=username, password=password)

    changes = []
    url = "https://" + options.review_url + "/a/changes/"

    if options.topic:
        print('Fetching topic changes')
        response = requests.get(url + "?q=topic:" + options.topic, auth=auth)
        if response.status_code != 200:
            print("Could not fetch topic changes")
            sys.exit()
        else:
            j = json.loads(response.text[5:])
            for k in j:
                changes.append(str(k['_number']))

    if len(args) >= 1:
        for i, param in enumerate(args):
            if '-' in param:
                templist = param.split('-')
                for i in range(int(templist[0]), int(templist[1]) + 1):
                    changes.append(str(i))
            else:
                changes.append(param)

    if len(changes) < 1:
        parser.error("You must specify either a range of commits or a topic")
        sys.exit()

    print("Fetching info about " + str(len(changes)) + " commits...\n")
    messages = []

    for c in changes:
        try:
            response = requests.get(url + c + "/detail/", auth=auth)
            if response.status_code != 200:
                print("Could not fetch commit information")
                sys.exit()
            else:
                j = json.loads(response.text[5:])
                messages.append("[" + j['status'] + "]  " + j['subject'])
        except:
            sys.exit()

    for m in messages:
        print(m)

    if options.submit:
        i = input("\nAbout to ship the preceeding commits. You good with this? [y/N] ")

        if i != 'y':
            print("Cancelled...")
            sys.exit()

        for c in changes:
            try:
                # Rebase it
                response = requests.post(url + c + "/rebase", auth=auth)
                if response.status_code != 200:
                    if response.status_code != 409 or "Change is already" not in response.text:
                        print("Failed to rebase " + c + " with error " + str(
                            response.status_code) + ": " + response.text.rstrip())
                        sys.exit(0)
            except Exception:
                print("Already at top of HEAD")
                pass

            # +2 it
            j = {}
            j['labels'] = {}
            try:
                labels = config.get(options.review_url, "labels").split(',')
                labels_range = config.get(options.review_url, "labels_range").split(',')
                for i in labels.size:
                    j['labels'][labels[i]] = '+' + labels_range[i]
            except:
                print('Failed to parse labels')
            response = requests.post(url + c + "/revisions/current/review", auth=auth, json=j)
            if response.status_code != 200:
                print("Failed to +2 change " + c + " with error " + str(
                    response.status_code) + ": " + response.text.rstrip())
                sys.exit(0)

            # SHIPIT!!!
            response = requests.post(url + c + "/revisions/current/submit", auth=auth)
            if response.status_code != 200:
                print(
                    "Failed to ship " + c + " with error " + str(response.status_code) + ": " + response.text.rstrip())
            else:
                print("Shipped: " + c + "!")


if __name__ == "__main__":
    main()
