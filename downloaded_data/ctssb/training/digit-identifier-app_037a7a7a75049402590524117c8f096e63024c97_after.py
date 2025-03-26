# Dependencies used to build the web app
from flask import Flask, render_template, jsonify, request
from keras.models import load_model
from keras.preprocessing.image import img_to_array
from keras.applications import imagenet_utils
import numpy as np
from PIL import Image, ImageOps, ExifTags
from werkzeug.exceptions import HTTPException
import traceback
import io
import functools

app = Flask(__name__)
model = None


def load_keras_model():
    """
    This method loads our model, so that we can use it to perform predictions.
    """
    global model
    # Only load model once
    if not model:
        print("------------------------>>>> loading model...")
        model = load_model('./mnistmodel_cnn.h5')
    return model


# Homepage: The form
@app.route('/')
def form():
    return render_template('form.html')


@app.route('/process_form', methods=["POST"])
def process_form():
    if not valid_image_request():
        # TODO: do not jsonify.
        return jsonify({
            "success": False,
            "error": "You must provide a valid `image`."
        })

    image = request.files["image"].read()
    image = Image.open(io.BytesIO(image))
    # Note that when using images uploaded from iphones, sometimes they will be rotated incorrectly.
    # This method fixes rotation if needed.
    image = image_transpose_exif(image)
    image, image_display = prepare_image(image)

    model = load_keras_model()

    # Returns an np array.. convert to list with .tolist()
    prediction_classes = model.predict_classes(image).tolist()

    # Displays probability for each number
    prediction_probabilities_list = model.predict(image).tolist()[0]
    prediction_probabilities = {}

    # Turn this into a dictionary of digit => probability
    prediction_probabilities = {}
    for num, p in enumerate(prediction_probabilities_list, start=0):
        prediction_probabilities[num] = p

    return render_template('results.html', prediction=prediction_classes[0], probabilities=prediction_probabilities, image=image_display)


def valid_image_request():
    return request.method == "POST" and request.files.get("image")


def prepare_image(image, should_smart_crop=False):
    # if the image mode is not grayscale ("L"), convert it
    # https://pillow.readthedocs.io/en/4.1.x/handbook/concepts.html#modes
    if image.mode != "L":
        image = image.convert("L")

    # Model is trained on inverted images, so we must invert our input
    image = ImageOps.invert(image)

    # autocontrast cleans up photos that are taken in e.g. lower light
    image = ImageOps.autocontrast(image, cutoff=2)

    if should_smart_crop:
        # Smart crop will attempt to find and auto-crop a digit in the image.
        # Returns a 28x28 image
        image = smart_crop(image)
    else:
        image = ImageOps.fit(image, size=(28, 28))

    # Convert into input format for model
    image = img_to_array(image)
    image = np.expand_dims(image, axis=0)

    # 28x28 image used for display
    # (if using CNN, this is the same as the model input image)
    image_display = image

    # NOTE: CNN model does not need this (comment out if using CNN model)
    # image = image.reshape(1, 784)

    # return the processed image
    return image, image_display


def smart_crop(image):
    # NOTE: Don't worry about the details of this method
    # --- Let's try to smart crop the image by finding the digit, to handle imperfect images
    # ref: https://codereview.stackexchange.com/a/132933

    # This will not work well for images that are already small (i.e. already 28x28)
    # In that case, return the image directly
    if image.size == (28, 28):
        return image

    # Assume that any pixel with value of 75 or less is black (part of background, since inverted)
    mask = img_to_array(image) > 100

    # Find coordinates of non-black pixels
    coords = np.argwhere(mask)

    # Bounding box of non-black pixels.
    y0, x0, _ = coords.min(axis=0)
    y1, x1, _ = coords.max(axis=0) + 1   # slices are exclusive at the top

    # Get the contents of the bounding box.
    cropped = image.crop((x0, y0, x1, y1))

    # Make the image square, with the size being the largest current size
    new_size = max(cropped.size)
    width_border = int((new_size - cropped.size[0]) / 2)
    height_border = int((new_size - cropped.size[1]) / 2)
    border = (width_border, height_border, width_border, height_border)
    image = ImageOps.expand(cropped, border=border)

    # Convert to final size, minus a border
    image = ImageOps.fit(image, size=(20, 20))

    # add border (so final size is 28x28)
    image = ImageOps.expand(image, border=4)

    return image


def image_transpose_exif(im):
    """
    Fixes rotation of image, by checking EXIF data.
    This fixes issues with images uploaded directly from a smart phone camera.
    Source: https://stackoverflow.com/a/30462851/76710
    """

    exif_orientation_tag = 0x0112
    exif_transpose_sequences = [                   # Val  0th row  0th col
        [],                                        #  0    (reserved)
        [],                                        #  1   top      left
        [Image.FLIP_LEFT_RIGHT],                   #  2   top      right
        [Image.ROTATE_180],                        #  3   bottom   right
        [Image.FLIP_TOP_BOTTOM],                   #  4   bottom   left
        [Image.FLIP_LEFT_RIGHT, Image.ROTATE_90],  #  5   left     top
        [Image.ROTATE_270],                        #  6   right    top
        [Image.FLIP_TOP_BOTTOM, Image.ROTATE_90],  #  7   right    bottom
        [Image.ROTATE_90],                         #  8   left     bottom
    ]

    try:
        seq = exif_transpose_sequences[im._getexif()[exif_orientation_tag]]
    except Exception:
        return im
    else:
        return functools.reduce(type(im).transpose, seq, im)

# Start the server
if __name__ == "__main__":
    print("* Starting Flask server..."
          "please wait until server has fully started")
    # debug=True options allows us to view our changes without restarting the server.
    app.run(host='0.0.0.0', debug=True)
