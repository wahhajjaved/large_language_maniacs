# Collin Gros
# 12/11/18


# arg description
# "s":scale_factor, "n":min_neighbors, "p":resolution_height, "z":cascade_xml,
# "w":warm, "c":cold, "l":low, "m":medium, "b":high,
# "v":vanilla_set, "f":hat_set, "e":glasses_set,
# "x":profile_pictures, "a":angled_pictures, "o":central_pictures,
# "g":shadows, "i":central_lighting


import cv2
import os
import time
import argparse
import pickle

settings = {}
data = {}
labels = {}

cascade = None
face_rec = None


def read_settings():
# set appropriate settings from argument input
    int_settings = ["n", "p", "w", "c", "l",
                    "m", "b", "v", "f", "e",
                    "x", "a", "o", "g", "i"]
    float_settings = ["s"]
    str_settings = ["z"]

    parser = argparse.ArgumentParser()
    for key in int_settings:
        settings[key] = 0

        cmd_str = "-{0}".format(key)
        parser.add_argument(cmd_str)

    for key in float_settings:
        settings[key] = 0.0

        cmd_str = "-{0}".format(key)
        parser.add_argument(cmd_str)

    for key in str_settings:
        settings[key] = ""

        cmd_str = "-{0}".format(key)
        parser.add_argument(cmd_str)

    args = parser.parse_args()

    all_settings = int_settings + float_settings + str_settings
    for key in all_settings:
        attr = getattr(args, key)
        if attr:
            settings[key] = attr


def init_data():
    int_data = ["skipped", "viewed", "correct", "incorrect"]
    for key in int_data:
        data[key] = 0


def load_data():
# load training data
    xml = settings["z"]

    global cascade
    cascade = cv2.CascadeClassifier(xml)

    global face_rec
    face_rec = cv2.face.LBPHFaceRecognizer_create()
    trained_path = "./train.yml"
    try:
        face_rec.read(trained_path)
    except:
        print("error: no training data was found\nexiting...\n")
        exit()

    labels_path = "./labels.pickle"
    with open(labels_path, "rb") as info:
        og_labels = pickle.load(info)

    for k, v in og_labels.items():
        labels[v] = k


def write_data():
# write data dict in ./stat.txt
    with open("stat.txt", "w") as info:
        for key, value in data.items():
            str = "{0}:{1}\n".format(key, value)
            info.write(str)


def draw(pic, name, conf, id, coords, color_str):
# draw box and text over detected face, save to
# ./{id}.JPG
    if color_str == "green":
        color = (0, 255, 0)
    elif color_str == "red":
        color = (0, 0, 255)

    x = coords[0]
    y = coords[1]
    w = coords[2]
    h = coords[3]

    cv2.rectangle(pic, (x, y), (x+w, y+h), color, 2)
    cv2.putText(pic, name, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, color, 2, cv2.LINE_AA)
    cv2.putText(pic, str(conf), (x+w, y+h+10), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, color, 2, cv2.LINE_AA)

    path = "./{0}.JPG".format(id)
    cv2.imwrite(path, pic)


def guess(path, name):
# guess whose face it is, record results
    str_arr = path.split("/")
    str_arr = str_arr[-1].split(".")
    id = str_arr[0]

    color_pic = cv2.imread(path, 1)
    gray_pic = cv2.imread(path, 0)

    height = int(settings["p"])
    width = int(height * 1.5)
    color_pic = cv2.resize(color_pic, (width, height))
    gray_pic = cv2.resize(gray_pic, (width, height))

    detected = cascade.detectMultiScale(gray_pic, scaleFactor=float(settings["s"]),
                                        minNeighbors=int(settings["n"]))
    if not len(detected):
    # no faces were detected
        data["skipped"] += 1
        return

    for (x, y, w, h) in detected:
        data["viewed"] += 1

        face = gray_pic[y:y+h, x:x+w]
        label, conf = face_rec.predict(face)

        guess = labels[label]
        coords = [x, y, w, h]

        if guess == name:
            data["correct"] += 1
            draw(color_pic, guess, conf, id, coords, "green")
        else:
            data["incorrect"] += 1
            draw(color_pic, guess, conf, id, coords, "red")


def filter(name, name_type, num=0):
# if we don't want to include the specified media, return 0
    if name_type == "occ":
        if name == "vanilla" and settings["v"]:
            return 1
        elif name == "glasses" and settings["e"]:
            return 1
        elif name == "hat" and settings["f"]:
            return 1
    elif name_type == "pos":
        profile = ["0", "4"]
        angled = ["1", "3"]
        central = ["2"]

        str = name.split("_")
        name = str[-1]

        if name in profile and settings["x"]:
            return 1
        elif name in angled and settings["a"]:
            return 1
        elif name in central and settings["o"]:
            return 1
    elif name_type == "light":
        shadows = ["1", "2", "3", "5", "6", "7"]
        central = ["4"]

        str = name.split("_")
        name = str[-1]

        if name in shadows and settings["g"]:
            return 1
        elif name in central and settings["i"]:
            return 1
    elif name_type == "color":
        if num == 0 and settings["w"]:
            return 1
        elif num == 1 and settings["c"]:
            return 1
        elif num == 2 and settings["l"]:
            return 1
        elif num == 3 and settings["m"]:
            return 1
        elif num == 4 and settings["b"]:
            return 1

    print("filter returning 0 for {0}:{1}".format(name, name_type))
    return 0


def test():
# for each filtered image, guess and record results
    ids = "./test"
    for id in os.listdir(ids):

        id_path = ids + "/" + id
        for occ in os.listdir(id_path):
            if not filter(occ, "occ"):
                continue

            occ_path = id_path + "/" + occ
            for pos in os.listdir(occ_path):
                if not filter(pos, "pos"):
                    continue

                light_path = occ_path + "/" + pos
                for light in os.listdir(light_path):
                    if not filter(light, "light"):
                        continue

                    num = 0
                    color_path = light_path + "/" + light
                    for color in os.listdir(color_path):
                        if not filter(color, "color", num):
                            continue

                        pic_path = color_path + "/" + color
                        print("guess: {0}:{1}".format(pic_path, id))
                        guess(pic_path, id)

                        num += 1


start = time.time()

read_settings()
init_data()
load_data()

test()

finish = time.time()
data["time"] = start - finish

write_data()

