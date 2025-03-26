#!/usr/bin/env python2
from flask import Flask, render_template, request, make_response
import os
import textwrap

from makeimage import makeimage
from config import SECRET

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process/', methods=['GET', 'POST'])
def process():
    if 'whoa' not in request.args:
        return "lol"
    if not request.args['whoa'] == SECRET:
        return "lol"
    if 'text' not in request.args or 'size' not in request.args:
        return "Missing text or font size"

    makeimage(request.args['size'], request.args['text'])
    os.system("screen -S tehpix -X stuff './viewimage.sh *.png\n'")
    return render_template("done.html")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=2345)
