from django.conf import settings

import requests
import json

def send_message(text, username=None, icon_emoji=None, icon_url=None, channel=None, attachments=None, unfurl_links=False):
	payload = {}
	if username: payload['username'] = username
	if icon_emoji: payload['icon_emoji'] = icon_emoji
	if icon_url: payload['icon_url'] = icon_url
	if channel: payload['channel'] = channel
	if attachments: payload['attachments'] = attachments
	if unfurl_links: payload['unfurl_links'] = unfurl_links
	payload['text'] = text
	requests.post(settings.SLACK_WEBHOOK_URL, data=json.dumps(payload))