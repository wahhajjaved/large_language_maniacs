from flask import Flask, request, jsonify
from utils import *
from stego import *


app = Flask(__name__)


@app.route('/')
def index():
    return "Welcome to Stegoman! A collection of API endpoints useful for steganography"


@app.route('/text2img', methods=['POST'])
def img_from_text():
    res = dict()
    status_code = 400

    try:
        req = request.json

        img = text_to_img(text = req["text"])
        img_b64 = img_to_b64(img, format="BMP")

        res['img'] = img_b64
        status_code = 200

    except Exception as e:
        print(e)
        res['error'] = 'Bad params'

    res = jsonify(res)
    res.status_code = status_code    
    return res


@app.route('/shrencrypt', methods=['POST'])
def shrencrypt_img():
    res = dict()
    status_code = 400

    try:
        req = request.json

        text = req['text']
        msg = req['msg']

        msg = list('shre') + [str(len(msg))] + msg

        img = encrypt_lsb(text, msg)
        img_b64 = img_to_b64(img, format="BMP")

        res['img'] = img_b64
        status_code = 200
    
    except Exception as e:
        print(e)
        res['error'] = 'Something went wrong'

    res = jsonify(res)
    res.status_code = status_code    
    return res


@app.route('/deshrencrypt', methods=['POST'])
def deshrencrypt():
    res = dict()
    status_code = 400

    try:
        req = request.json

        img = req['img']

        img = b64_to_img(img)

        msg = decrypt_shre(img)

        res['msg'] = msg
        status_code = 200

    except Exception as e:
        print(e)
        res['error'] = 'Something went wrong'

    res = jsonify(res)
    res.status_code = status_code    
    return res


if __name__ == '__main__':
    app.run(debug=True)