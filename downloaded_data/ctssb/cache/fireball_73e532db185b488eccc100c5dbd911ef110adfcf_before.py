import io
import os
import sys
import json
import logging
import subprocess
import tempfile
import settings
import requests
import uuid
import concurrent.futures
import re

from flask import Flask, request, jsonify

from boto.s3.connection import S3Connection
from boto.s3.key import Key

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.rl_config import defaultPageSize

from PyPDF2 import PdfFileMerger

from PIL import Image

app = Flask(__name__)

def main():
    app.run(threaded=True, debug=True, port=5000, host='0.0.0.0')

@app.route('/pdf', methods=['POST'])
def generate():
    """example docstring"""
    request_data = request.json

    output = request_data["output"]
    pages = request_data["pages"]
    custom_types = request_data["customTypes"]

    s3Connection = get_s3_connection()

    session_folder = make_session_folder()

    (fd, workfile) = tempfile.mkstemp(prefix=session_folder)
    logging.info("generate will use workfile %s", workfile)

    # load the cover pdf for the first page
    cover_page = pages[0]
    (cover_page_fd, cover_page_filename) = tempfile.mkstemp(prefix=session_folder)
    logging.info("generate will use cover page filename %s", cover_page_filename)

    download_success = False
    if cover_page["type"] == "pdf" and cover_page["method"] == "download":
        download_success = download(cover_page["input"], cover_page_filename)
    else:
        logging.error("cover page was invalid")
        return "cover page was invalid"

    if download_success != True:
        logging.error("problem during download")
        return "problem during download"

    # generate pdf from the rest of the pages

    pages_to_download = []
    playbook = []

    # skip first page
    pages_iterator = iter(pages)
    next(pages_iterator)
    for page in pages_iterator:
        page["id"] = str(uuid.uuid4())
        playbook.append(page)
        if page["type"] == "jpg" and page["method"] == "s3":
            pages_to_download.append(page)
            logging.debug("adding %s to list of images to download", page["input"])
        elif page["type"] in custom_types:
            # found custom type
            logging.debug("found custom type %s", page["type"])
        else:
            logging.error("unknown page type %s", page["type"])
            return "unknown page type %s", page["type"]

    parallel_fetch(s3Connection, pages_to_download, session_folder)

    logging.debug("creating pdf")

    pdf = Canvas(workfile, pageCompression=1)

    pages_iterator = iter(pages)
    next(pages_iterator)
    for page in pages_iterator:
        if page in pages_to_download:
            downloaded_file = session_folder + "/" + page["input"]
            if os.path.exists(downloaded_file):
                if pdf_append_image(pdf, downloaded_file):
                    # all good
                    pass
                else:
                    # problem
                    return jsonify({"success": False, "message": "problem with image"})
            else:
                # missing
                pdf_append_custom(pdf, custom_types["missing"])
        elif page["type"] == "redacted":
            pdf_append_custom(pdf, custom_types["redacted"])

    pdf.save()

    #write_file_to_s3(workfile, output, "application/pdf")

    response_data = {
        "success": True
    }

    return jsonify(response_data)

@app.route('/general-case/', methods=['POST'])
def generate_general_case():
    """example docstring"""
    request_data = request.get_json()

    output_method = request_data.get("method")
    output = request_data.get("output")

    pages = request_data.get("pages")

    custom_types = request_data.get("customTypes")

    # create a plan for the operations
    # if any pages are a pdf, then we will need to merge results with them

    # e.g. p1 = pdf, p2 = jpg, p3 = jpg
    # plan = merge(p1, pdf(p2,p3))

    # p1 = jpg, p2 = jpg, p3 = pdf
    # plan = merge(pdf(p1,p2), p3)

    # p1 = jpg, p2 = pdf, p3 = jpg, p4 = pdf
    # plan = merge(pdf(p1), p2, pdf(p3), p4)

    # p1 = jpg, p2 = jpg, p3 = jpg
    # plan = pdf(p1,p2,p3)

    plan = []

    if any(page.type == "pdf" for page in pages):
        # got pdfs to merge with our generated pages
        logging.debug("we will need to merge existing pdf with our work")

    workfile = ""

    page_index = 0

    for page in pages:
        page_index = page_index + 1
        logging.debug("page %d: type=%s", page_index, page.type)

    if output_method == "s3":
        write_file_to_s3(workfile, output, "application/pdf")
# gotta keep 'em separated

def pdf_append_custom(pdf, custom_type):
    """example docstring"""

    page_width = defaultPageSize[0]
    page_height = defaultPageSize[1]

    text = custom_type["message"]
    text_width = stringWidth(text, 'Helvetica', '10')
    text_start_y = page_height * 0.3
    pdf_text_object = pdf.beginText((page_width - text_width) / 2.0, text_start_y)
    pdf_text_object.textOut(text)
    pdf.showPage()

def pdf_append_image(pdf, filename):
    """example docstring"""
    try:
        image = Image.open(filename)
        image_width, image_height = image.size
        try:
            dpi = image.info['dpi'][0]
        except KeyError:
            pass
        width = image_width * 72 / dpi
        height = image_height * 72 / dpi
        pdf.setPageSize((width, height))
        pdf.drawImage(image, 0, 0, width=width, height=height)
        pdf.showPage()
    except Exception as append_exception:
        logging.exception("problem during append to pdf of %s: %s", filename, str(append_exception))
        return False
    return True
  
def write_file_to_s3(workfile, output, mime_type):
    """example docstring"""
    logging.debug("write_file_to_s3")

def make_session_folder():
    """example docstring"""
    session_folder = settings.WORK_FOLDER + "/" + str(uuid.uuid4())
    try:
        os.stat(session_folder)
    except os.error:
        os.mkdir(session_folder)
    return session_folder

def parallel_fetch(s3Connection, download_list, base_folder):
    """example docstring"""

    succeeded = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.DOWNLOAD_POOL_SIZE) as executor:
        futures = {
            executor.submit(fetch, s3Connection, base_folder, page):
                page for page in download_list
        }
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                succeeded += 1

    return download_list.count == succeeded

def fetch(s3Connection, base_folder, page):
    """example docstring"""
    target_filename = base_folder + "/" + page["id"]
    logging.debug("fetching %s to %s", page["input"], target_filename)
    if page["input"].startswith('s3://'):
        return download_s3(s3Connection, page["input"], target_filename)
    else:
        return download(page["input"], target_filename)

def download_s3(s3Connection, uri, filename):
    """example docstring"""
    logging.debug("using s3 strategy to download %s", uri)

    (bucket_name, key) = parse_bucket_uri(uri)

    bucket = s3Connection.get_bucket(bucket_name)

    s3_key = Key(bucket)
    s3_key.key = key

    try:
        s3_key.get_contents_to_filename(filename + ".moving")

        logging.debug("downloaded %s -> $s", (uri, filename + ".moving"))
        os.rename(filename + ".moving", filename)
        logging.debug("renamed to " + filename)
    except Exception as download_exception:
        logging.exception('hit a problem while trying to download %s: %s',
                          uri, str(download_exception))
        return False
    return True

def download(url, filename):
    """example docstring"""
    try:
        download_request = requests.get(url)
        with open(filename, 'wb') as file:
            file.write(download_request.content)
        return True
    except Exception as download_exception:
        logging.exception("problem during download of %s to %s: %s", url, filename,
                          str(download_exception))
    return False

def get_s3_connection():
    """example docstring"""
    return S3Connection(
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY)

def parse_bucket_uri(uri):
    """
    uri: s3://bucket/key
    returns: bucket, key
    """

    match = re.search(r's3://([^\/]+)/(.*)$', uri)
    if match:
        return match.group(1), match.group(2)

    return None, None

def setup_logging():
    """example docstring"""
    logging.basicConfig(filename="fireball.log",
                        filemode='a',
                        level=logging.DEBUG,
                        format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s', )
    logging.getLogger('boto').setLevel(logging.ERROR)
    logging.getLogger('botocore').setLevel(logging.ERROR)
    logging.getLogger('werkzeug').setLevel(logging.DEBUG)

if __name__ == "__main__":
    setup_logging()
    main()
