from datetime import datetime
import boto3
import json
import urllib
import sys
import re
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.info("Loading function")

rekognitionClient = boto3.client("rekognition")
rekThreshold = 1
rekMaxFaces = 1
rekCollectionId = "MyCollection"
channelSecret = os.environ["CHANNEL_ACCESS_TOKEN"]
LINE_BASE_URL = "https://api.line.me/v2/bot/message"
REPLY_URL = "https://ReplaceS3BucketName.s3-ap-northeast-1.amazonaws.com"

def get_image(message_id):
    """LINE Message APIサーバから、送信されたImageを取得"""
    url = f"{LINE_BASE_URL}/{message_id}/content"
    headers = {
        "Authorization": channelSecret,
        "Content-Type": "application/json"
    }
    request = urllib.request.Request(url, method="GET", headers=headers)
    with urllib.request.urlopen(request) as res:
        return res.read()

def get_face_match(body):
    """一致度判定"""
    response = rekognitionClient.search_faces_by_image(
        CollectionId=rekCollectionId,
        Image={
            "Bytes": body,
        },
        FaceMatchThreshold=rekThreshold,
        MaxFaces=rekMaxFaces
    )

    faceMatches = response["FaceMatches"]
    logger.info("Matching faces")

    for match in faceMatches:
        score = match["Similarity"]
        rek_message = f"一致度は{score:.2f}%でした！"
        rek_image_key = ["Face"]["ExternalImageId"]
        return {"rek_message": rek_message, "rek_image_key": rek_image_key}

def create_reply_request(replyToken, rek_message, image_url):
    """Reply用リクエスト生成"""
    url = f"{LINE_BASE_URL}/reply"
    method = "POST"
    headers = {
        "Authorization": channelSecret,
        "Content-Type": "application/json"
    }
    message = [
        {
            "type": "text",
            "text": "偉人との一致度を判定しました！\n判定結果は、、、、"
        },
        {
            "type": "image",
            "originalContentUrl": image_url,
            "previewImageUrl": image_url

        },
        {
            "type": "text",
            "text": str(rek_message)
        }
    ]
    params = {
        "replyToken": replyToken,
        "messages": message
    }
    return {"url": url, "header": headers, "body": message, "params": params, "method": method}

def lambda_handler(event, context):

    jsonstr = json.dumps(event, indent=2)
    logger.info("Received event: " + jsonstr)

    body = json.loads(event["Records"][0]["body"])
    timestamp = body["timestamp"]
    messageId = body["message"]["id"]
    replyToken = body["replyToken"]
    logger.info(f"timestamp: {timestamp}")
    logger.info(f"messageId: {messageId}")
    logger.info(f"replytoken: {replyToken}")

    image_body = get_image(messageId)
    # TODO: bytes型の取り回し、こう修正したい
    # rek_dict = get_face_match(image_body)
    
    # 一致度判定
    response = rekognitionClient.search_faces_by_image(
        CollectionId=rekCollectionId,
        Image={
            "Bytes": image_body,
        },
        FaceMatchThreshold=rekThreshold,
        MaxFaces=rekMaxFaces
    )
    faceMatches = response["FaceMatches"]
    logger.info("Matching faces")

    for match in faceMatches:
        score = match["Similarity"]
        rek_message = f"一致度は{score:.2f}%でした！"
        rek_image_key = match["Face"]["ExternalImageId"]
        rek_dict = {"rek_message": rek_message, "rek_image_key": rek_image_key}
    
    logger.info(str(rek_dict))
    
    # Reply用画像URL生成
    image_key = rek_dict["rek_image_key"]
    image_url = f"{REPLY_URL}/{image_key}"
    logger.info(image_url)
    
    # Reply用リクエスト生成
    request_dict = create_reply_request(replyToken, rek_dict["rek_message"], image_url)
    logger.info(str(request_dict))

    request = urllib.request.Request(url=request_dict["url"], data=json.dumps(
        request_dict["params"]).encode("utf-8"), method=request_dict["method"], headers=request_dict["header"])

    with urllib.request.urlopen(request) as res:
        body = res.read()
    
    # TODO: 適切な戻り値判定
    return 0   
