# https://github.com/line/line-bot-sdk-python/blob/master/examples/flask-kitchensink/app.py

import os
import uuid

from flask import abort
from flask import Flask
from flask import request
from dotenv import load_dotenv
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import ApiClient
from linebot.v3.messaging import TextMessage
from linebot.v3.messaging import MessagingApi
from linebot.v3.messaging import Configuration
from linebot.v3.messaging import MessagingApiBlob
from linebot.v3.messaging import BroadcastRequest
from linebot.v3.messaging import PushMessageRequest
from linebot.v3.messaging import ReplyMessageRequest
from linebot.v3.webhooks import MessageEvent
from linebot.v3.webhooks import TextMessageContent
from linebot.v3.webhooks import ImageMessageContent
from linebot.v3.webhooks import VideoMessageContent
from linebot.v3.webhooks import AudioMessageContent
from linebot.v3.exceptions import InvalidSignatureError


load_dotenv()

DATA_DIR = os.getenv('DATA_DIR')
LINE_DIR = os.path.join(DATA_DIR, os.getenv('LINE_DIR'))
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

os.makedirs(LINE_DIR, exist_ok=True)

application = Flask(__name__)
application.config['CORS_HEADERS'] = 'Content-Type'
application.config['CORS_RESOURCES'] = {r'/api/*': {'origins': '*'}}
application.config['PROPAGATE_EXCEPTIONS'] = True

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


@application.route('/test', methods=['GET'])
def test():
    return 'OK'


@application.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    print('Request body: ' + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print('Invalid signature. Please check your channel access token/channel secret.')
        abort(400)
    return 'OK'


@application.route('/send', methods=['POST'])
def send():
    data = request.get_json(silent=True) or {}
    to = data.get('to')
    text = data.get('text')
    if not to or not text:
        return {'error': "Parameter 'to' and 'text' are required."}, 400
    try:
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message_with_http_info(
                PushMessageRequest(
                    to=to,
                    messages=[TextMessage(text=text)]
                )
            )
    except Exception as e:
        print(f'LINE push failed: {e}')
        abort(500)
    return 'OK'


@application.route('/broadcast', methods=['POST'])
def broadcast():
    data = request.get_json(silent=True) or {}
    text = data.get('text')
    if not text:
        return {'error': 'text required'}, 400
    try:
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).broadcast(
                BroadcastRequest(
                    messages=[TextMessage(text=text)]
                )
            )
    except Exception as e:
        print(f'LINE push failed: {e}')
        abort(500)
    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        reply = TextMessage(text=f'You sent：{event.message.text}')
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[reply]
            )
        )


@handler.add(MessageEvent, message=(ImageMessageContent, VideoMessageContent, AudioMessageContent))
def handle_content_message(event):
    if isinstance(event.message, ImageMessageContent):
        ext = 'jpg'
    elif isinstance(event.message, VideoMessageContent):
        ext = 'mp4'
    elif isinstance(event.message, AudioMessageContent):
        ext = 'm4a'
    else:
        return
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        line_bot_blob_api = MessagingApiBlob(api_client)
        content = line_bot_blob_api.get_message_content(event.message.id)
        temp_name = f'{uuid.uuid4().hex}.{ext}'
        with open(os.path.join(LINE_DIR, temp_name), 'wb') as f:
            f.write(content)
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text='File received!')]
            )
        )


if __name__ == '__main__':
    application.run(host='0.0.0.0', port=5050)
