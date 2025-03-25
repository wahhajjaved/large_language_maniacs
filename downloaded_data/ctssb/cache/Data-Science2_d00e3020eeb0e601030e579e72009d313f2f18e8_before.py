# imports
from flask import Flask, request
from flask import jsonify
from .resnet50 import process_img_path, resnet_model

def create_app():
    app = Flask(__name__)

    @app.route('/predictor', methods=['POST'])
    def predictor():
        '''a route that expects an image url and id. returns image classifications, probabilities, and id'''
        # get info from backend 
        lines = request.get_json(force=True)
    
        # get strings from json
        url = lines['url']
        photo_id = lines['photo_id'] 

        # make sure the input's correct
        assert isinstance(url, str)
        assert isinstance(photo_id, int)

        # process image and predict
        predictions = resnet_model(process_img_path(url))

        # Return JSON object with photo_id and a list of predictions as a string
        try:
            return jsonify(photo_id=photo_id,
                           predictions=str(predictions))

        except IOError:
            return jsonify(error="Error: Invalid URL")

    return app
