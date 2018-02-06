#!/usr/bin/env python

import configparser
import json
import os
import sys
from optparse import OptionParser

import requests
from requests.auth import HTTPBasicAuth

version = '0.1'
CONFIG_FILENAME = os.getenv("HOME") + '/.gerrit.cfg'


def main():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILENAME)
    parser = OptionParser(
        usage='%prog [options] changes', version="%prog " + version)

    # Logging
    group = parser.add_option_group('Logging options')
    group.add_option('-v', '--verbose',
                     action='store_true', dest='verbose',
                     help='Print status messages to stdout')

    # Gerrit - URL
    group = parser.add_option_group('Gerrit options')
    group.add_option('-r', '--review-url', dest='review_url',
                     help='Gerrit URL', metavar='URL')

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
                     help='Set topic or submit by topic', metavar='TOPIC')
    group.add_option('-e', '--exclude', dest='exclude',
                     help='Exclude changes', metavar='EXCLUDE')

    # Labels
    group = parser.add_option_group('Label options')
    group.add_option('--labels', dest='labels',
                     help='Specify the labels', metavar='LABEL,LABEL')
    group.add_option('--labels-ranges', dest='labels_ranges',
                     help='Specify the labels ranges', metavar='RANGE,RANGE')

    (options, args) = parser.parse_args()

    if not args and not options.topic:
        parser.error('You must specify either a range of commits or a topic')
        sys.exit()

    if options.review_url:
        review_url = options.review_url
    else:
        try:
            review_url = config.get("Defaults", "review_url")
        except:
            parser.error('Review URL must be set')
            sys.exit()

    if options.username:
        username = options.username
    else:
        try:
            username = config.get(review_url, "username")
        except:
            parser.error('Username must be set')
            sys.exit()

    if options.password:
        password = options.password
    else:
        try:
            password = config.get(review_url, "password")
        except:
            parser.error('Password must be set')
            sys.exit()

    auth = HTTPBasicAuth(username=username, password=password)

    changes = []
    url = review_url + "/a/changes/"

    if args:
        for i, param in enumerate(args):
            if '..' in param:
                temp_list = param.split('..')
                for j in range(int(temp_list[0]), int(temp_list[1]) + 1):
                    changes.append(str(j))
            else:
                changes.append(param)

    if options.topic:
        print('Fetching topic changes')
        status = ""
        if options.submit:
            status = "+status:open"
        response = requests.get(
            url + "?q=topic:" + options.topic + status + "&pp=0", auth=auth)
        if response.status_code != 200:
            sys.exit("Could not fetch topic changes")
        else:
            j = json.loads(response.text[5:])
            for k in j:
                changes.append(str(k['_number']))

    if options.exclude:
        changes = list(set(changes) - set(options.exclude.split(',')))

    if len(changes) < 1:
        parser.error("You must specify either a range of commits or a topic")
        sys.exit()

    print("Fetching info about " + str(len(changes)) + " commits...\n")
    messages = []

    for c in changes:
        try:
            response = requests.get(url + c + "?pp=0", auth=auth)
            if response.status_code != 200:
                sys.exit("Could not fetch commit information")
            else:
                j = json.loads(response.text[5:])
                messages.append("[%s] [%s] %s" %
                                (j['status'], j['_number'], j['subject']))
        except:
            sys.exit()

    for m in messages:
        print(m)

    if options.submit:
        i = input(
            "\nAbout to submit the proceeding commits. You good with this? [y/N] ")

        if i != 'y':
            sys.exit("Cancelled...")

        # Load labels needed for the submit
        j = {'labels': {}}
        try:
            if options.labels:
                labels = options.labels.split(',')
            else:
                labels = config.get(review_url, "labels").split(',')

            if options.labels_ranges:
                labels_ranges = options.labels_ranges.split(',')
            else:
                labels_ranges = config.get(
                    review_url, "labels_ranges").split(',')

            for i in range(0, len(labels)):
                j['labels'][labels[i].strip()] = '+' + labels_ranges[i].strip()
        except:
            sys.exit('Failed to parse labels')

        for c in changes:
            # Rebase it
            base = {'base': ''}
            response = requests.post(url + c + "/rebase", auth=auth, json=base)
            if response.status_code != 200:
                if response.status_code != 409 or "Change is already" not in response.text:
                    sys.exit("Failed to rebase " + c +
                             " with error: " + response.text.rstrip())

            response = requests.post(
                url + c + "/revisions/current/review", auth=auth, json=j)
            if response.status_code != 200:
                sys.exit("Failed to apply labels to change " + c +
                         " with error: " + response.text.rstrip())

            # Submit it
            response = requests.post(
                url + c + "/revisions/current/submit", auth=auth)
            if response.status_code != 200:
                print("Failed to submit " + c +
                      " with error: " + response.text.rstrip())
            else:
                print("Submitted: " + c + "!")
    elif options.reviewers:
        i = input(
            "\nAbout to add reviewers to the proceeding commits. You good with this? [y/N] ")

        if i != 'y':
            sys.exit("Cancelled...")

        for c in changes:
            reviewers = options.reviewers.split(',')
            for reviewer in reviewers:
                j = {'reviewer': reviewer.strip()}
                response = requests.post(
                    url + c + "/reviewers", auth=auth, json=j)
                if response.status_code == 200:
                    # Handle groups
                    if "Do you want to add them all as reviewers?" in response.text:
                        j = {'input': reviewer, 'confirmed': 'true'}
                        requests.post(url + c + "/reviewers",
                                      auth=auth, json=j)
                    print('Successfully added ' + reviewer + ' to ' + c)
                else:
                    print("Failed to add reviewer " + reviewer + " to change " + c +
                          " with error: " + response.text.rstrip())
    else:
        sys.exit('Unsupported option')


if __name__ == "__main__":
    main()
