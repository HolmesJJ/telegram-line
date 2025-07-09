# https://github.com/line/line-bot-sdk-python/blob/master/examples/flask-kitchensink/app.py
# https://developers.line.biz/en/reference/messaging-api/#get-group-member-user-ids
# https://www.linebiz.com/jp-en/service/line-account-connect/entry/

import os
import uuid

from flask import abort
from flask import Flask
from flask import jsonify
from flask import request
from flask import send_from_directory
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import ApiClient
from linebot.v3.messaging import TextMessage
from linebot.v3.messaging import MessagingApi
from linebot.v3.messaging import Configuration
from linebot.v3.messaging import MessagingApiBlob
from linebot.v3.messaging import BroadcastRequest
from linebot.v3.messaging import PushMessageRequest
from linebot.v3.messaging import ReplyMessageRequest
from linebot.v3.webhooks import JoinEvent
from linebot.v3.webhooks import MessageEvent
from linebot.v3.webhooks import TextMessageContent
from linebot.v3.webhooks import ImageMessageContent
from linebot.v3.webhooks import VideoMessageContent
from linebot.v3.webhooks import AudioMessageContent
from linebot.v3.exceptions import InvalidSignatureError


load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), os.getenv('DATA_DIR'))
LINE_DIR = os.path.join(DATA_DIR, os.getenv('LINE_DIR'))
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

STATIC_DIR = os.path.join(os.path.dirname(__file__), os.getenv('STATIC_DIR'))

os.makedirs(LINE_DIR, exist_ok=True)

application = Flask(__name__)
application.config['CORS_HEADERS'] = 'Content-Type'
application.config['CORS_RESOURCES'] = {r'/api/*': {'origins': '*'}}
application.config['PROPAGATE_EXCEPTIONS'] = True

mongo_client = MongoClient('localhost', 27017)
line_db = mongo_client['line']
message_collection = line_db['message']
user_collection = line_db['user']
group_collection = line_db['group']
room_collection = line_db['room']

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


@application.route('/', methods=['GET'])
def test():
    return 'OK'


@application.route('/data/line/<path:filename>')
def serve_file(filename):
    try:
        return send_from_directory(LINE_DIR, filename, as_attachment=False)
    except FileNotFoundError:
        abort(404, description='File not found')


@application.route('/line')
def serve_html():
    return send_from_directory(STATIC_DIR, 'line.html')


@application.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    print('[callback] Request body: ' + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print('[callback] Invalid signature. Please check your channel access token/channel secret.')
        abort(400)
    return 'OK'


@application.route('/api/send', methods=['POST'])
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
        print(f'[send] failed: {e}')
        abort(500)
    return 'OK'


@application.route('/api/broadcast', methods=['POST'])
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
        print(f'[broadcast] failed: {e}')
        abort(500)
    return 'OK'


@application.route('/api/bots', methods=['GET'])
def get_bots():
    bot_ids = message_collection.distinct('bot_id')
    return jsonify(bot_ids)


@application.route('/api/sources', methods=['GET'])
def get_sources():
    sources = []
    for user in user_collection.find():
        sources.append({
            'type': 'user',
            'id': user['user_id'],
            'name': user.get('display_name', user['user_id'])
        })
    for group in group_collection.find():
        sources.append({
            'type': 'group',
            'id': group['group_id'],
            'name': group.get('group_name', group['group_id'])
        })
    for room in room_collection.find():
        sources.append({
            'type': 'room',
            'id': room['room_id'],
            'name': room.get('room_id')
        })
    return jsonify(sources)


@application.route('/api/messages', methods=['GET'])
def get_messages():
    bot_id = request.args.get('bot_id')
    source_type = request.args.get('source_type')
    source_id = request.args.get('source_id')
    user_id = request.args.get('user_id')
    if source_id:
        query = {
            'bot_id': bot_id,
            'source_type': source_type,
            'source_id': source_id
        }
    elif user_id:
        query = {
            'bot_id': bot_id,
            'source_type': source_type,
            'user_id': user_id
        }
    else:
        return {'error': "Parameter 'source_id' or 'user_id' is required."}, 400
    messages = []
    cursor = message_collection.find(query).sort('created_at', 1)
    for row in cursor:
        user_id = row.get('user_id', '')
        user = user_collection.find_one({'user_id': user_id})
        messages.append({
            'type': row.get('message_type'),
            'content': row.get('message_content'),
            'user_id': user_id,
            'user_name': user.get('display_name') if user else user_id,
            'timestamp': row.get('created_at').strftime('%Y-%m-%d %H:%M:%S')
        })
    return jsonify(messages)


@handler.add(JoinEvent)
def handle_member_joined(event):
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        source_type = event.source.type
        if source_type == 'group':
            group_id = event.source.group_id
            print(f'[handle_member_joined] group_id: {group_id}')
            group_exists = group_collection.find_one({'group_id': group_id})
            if not group_exists:
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text='Please set a name for this group by typing: /setname YourGroupName')]
                    )
                )
        elif source_type == 'room':
            room_id = event.source.room_id
            print(f'[handle_member_joined] room_id: {room_id}')
            room_exists = room_collection.find_one({'room_id': room_id})
            if not room_exists:
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text='Please set a name for this room by typing: /setname YourRoomName')]
                    )
                )


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    with ApiClient(configuration) as api_client:
        line_api = MessagingApi(api_client)
        source_type = event.source.type
        if source_type == 'group':
            group_id = event.source.group_id
            user_id = event.source.user_id
            print(f'[handle_text_message] user_id: {user_id}, group_id: {group_id}')
            if event.message.text.startswith('/setname'):
                group_name = event.message.text.replace('/setname', '').strip()
                upsert_group(group_id, group_name)
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f'Group name has been set to: {group_name}')]
                    )
                )
            else:
                bot_id = request.json['destination']
                message_text = event.message.text
                timestamp = event.timestamp
                insert_message(bot_id, 'text', message_text, source_type, group_id, user_id, timestamp)
        elif source_type == 'room':
            room_id = event.source.room_id
            user_id = event.source.user_id
            print(f'[handle_text_message] user_id: {user_id}, room_id: {room_id}')
            if event.message.text.startswith('/setname'):
                room_name = event.message.text.replace('/setname', '').strip()
                upsert_room(room_id, room_name)
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f'Room name has been set to: {room_name}')]
                    )
                )
            else:
                bot_id = request.json['destination']
                message_text = event.message.text
                timestamp = event.timestamp
                insert_message(bot_id, 'text', message_text, source_type, room_id, user_id, timestamp)
        elif source_type == 'user':
            user_id = event.source.user_id
            print(f'[handle_text_message] user_id: {user_id}')
            profile = line_api.get_profile(user_id)
            upsert_user(user_id, profile.display_name)
            bot_id = request.json['destination']
            message_text = event.message.text
            timestamp = event.timestamp
            insert_message(bot_id, 'text', message_text, source_type, None, user_id, timestamp)


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
        line_bot_blob_api = MessagingApiBlob(api_client)
        content = line_bot_blob_api.get_message_content(event.message.id)
        file_name = f'{uuid.uuid4().hex}.{ext}'
        with open(os.path.join(LINE_DIR, file_name), 'wb') as f:
            f.write(content)
        bot_id = request.json['destination']
        source_type = event.source.type
        timestamp = event.timestamp
        if source_type == 'group':
            group_id = event.source.group_id
            user_id = event.source.user_id
            print(f'[handle_content_message] user_id: {user_id}, group_id: {group_id}')
            insert_message(bot_id, ext, file_name, source_type, group_id, user_id, timestamp)
        elif source_type == 'room':
            room_id = event.source.room_id
            user_id = event.source.user_id
            print(f'[handle_content_message] user_id: {user_id}, room_id: {room_id}')
            insert_message(bot_id, ext, file_name, source_type, room_id, user_id, timestamp)
        elif source_type == 'user':
            user_id = event.source.user_id
            print(f'[handle_content_message] user_id: {user_id}')
            insert_message(bot_id, ext, file_name, source_type, None, user_id, timestamp)


def upsert_user(user_id, display_name):
    user_collection.update_one(
        {'user_id': user_id},
        {
            '$set': {
                'display_name': display_name,
                'updated_at': datetime.now()
            },
            '$setOnInsert': {
                'created_at': datetime.now()
            }
        },
        upsert=True
    )


def upsert_group(group_id, group_name):
    group_collection.update_one(
        {'group_id': group_id},
        {
            '$set': {
                'group_name': group_name,
                'updated_at': datetime.now()
            },
            '$setOnInsert': {
                'created_at': datetime.now()
            }
        },
        upsert=True
    )


def upsert_room(room_id, room_name):
    room_collection.update_one(
        {'room_id': room_id},
        {
            '$set': {
                'room_name': room_name,
                'updated_at': datetime.now()
            },
            '$setOnInsert': {
                'created_at': datetime.now()
            }
        },
        upsert=True
    )


def insert_message(bot_id, message_type, message_content, source_type, source_id, user_id, timestamp):
    message_doc = {
        'bot_id': bot_id,
        'message_type': message_type,
        'message_content': message_content,
        'source_type': source_type,
        'source_id': source_id,
        'user_id': user_id,
        'created_at': datetime.fromtimestamp(timestamp / 1000),
        'updated_at': datetime.fromtimestamp(timestamp / 1000)
    }
    message_collection.insert_one(message_doc)


if __name__ == '__main__':
    application.run(host='0.0.0.0', port=5050)
