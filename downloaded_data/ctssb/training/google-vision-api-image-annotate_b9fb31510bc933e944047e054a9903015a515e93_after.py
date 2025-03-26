#!/usr/bin/env python
"""
Uses the Google Cloud Vision API, currently in beta as of March 2016.
"""

import argparse
import base64
import csv
import httplib2
import datetime
import json
import os
from apiclient.discovery import build
from oauth2client.client import GoogleCredentials

__author__ = "NC"

# Globals
timestamp = str(datetime.datetime.now())  # Use timestamp to store data in unique filenames
json_file_name = "output data/" + timestamp + "-vision-api-output.json"
csv_file_name = "output data/" + timestamp + "-vision-api-output.csv"

# Initialize csv
with open(csv_file_name, 'a') as csvfile:
    csv_writer = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    csv_writer.writerow(['image_name', 'labels', 'texts'])


def process_images(image_input):
    image_exts = ['.jpg', 'jpeg', '.png']
    ignore_files = ['.DS_Store']

    # Check if folder
    if image_input[-1] == "/":
        dir_name = image_input
        for fn in os.listdir(dir_name):
            ext = os.path.splitext(fn)
            if fn not in ignore_files and ext[1].lower() in image_exts and not os.path.isdir(fn):
                print(fn)
                main(dir_name + fn)
    else:
        print(image_input)
        main(image_input)


def store_json(json_input):
    with open(json_file_name, "a") as f:
        f.write(json_input)
        f.write('\n')


def store_csv(csv_input):
    with open(csv_file_name, 'a') as csvfile:
        csv_writer = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        try:
            csv_writer.writerow(csv_input)
        except UnicodeEncodeError:  # TODO: handle unicode OR just run with Python 3 :)
            csv_writer.writerow(["ERROR"])


def main(photo_file):
    """Run a label request on a single image"""

    API_DISCOVERY_FILE = 'https://vision.googleapis.com/$discovery/rest?version=v1'
    http = httplib2.Http()

    credentials = GoogleCredentials.get_application_default().create_scoped(
            ['https://www.googleapis.com/auth/cloud-platform'])
    credentials.authorize(http)

    service = build('vision', 'v1', http, discoveryServiceUrl=API_DISCOVERY_FILE)

    with open(photo_file, 'rb') as image:
        image_content = base64.b64encode(image.read())
        service_request = service.images().annotate(
                body={
                    'requests': [{
                        'image': {
                            'content': image_content
                        },
                        'features': [{
                            'type': 'LABEL_DETECTION',
                            'maxResults': 20,
                        },
                            {
                            'type': 'TEXT_DETECTION',
                            'maxResults': 20,
                            }]
                    }]
                })
    response = service_request.execute()

    # Prepare parsing of responses into relevant fields
    query = photo_file
    all_labels = ''
    all_text = ''

    try:
        labels = response['responses'][0]['labelAnnotations']
        for label in labels:
            # label = response['responses'][0]['labelAnnotations'][0]['description']
            label_val = label['description']
            score = str(label['score'])
            print('Found label: "%s" with score %s' % (label_val, score))
            all_labels += label_val.encode('utf-8') + ' @ ' + score + ', '
    except KeyError:
        print("N/A labels found")

    print('\n')

    try:
        texts = response['responses'][0]['textAnnotations']
        for text in texts:
            # text = response['responses'][0]['textAnnotations'][0]['description']
            text_val = text['description']
            print('Found text: "%s"' % text_val)
            all_text += text_val.encode('utf-8') + ', '
    except KeyError:
        print("N/A text found")

    print('\n= = = = = Image Processed = = = = =\n')

    response["query"] = photo_file
    csv_response = [query, all_labels, all_text]

    response = json.dumps(response, indent=3)
    store_json(response)
    store_csv(csv_response)

    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('image_input', help='The folder containing images or the image you\'d like to query')
    args = parser.parse_args()
    process_images(args.image_input)

