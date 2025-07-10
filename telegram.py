import os
import uuid
import asyncio
import mimetypes
import threading

from flask import abort
from flask import Flask
from flask import jsonify
from flask import request
from flask import send_from_directory
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from telethon import events
from telethon import TelegramClient
from telethon.tl import types as tl


load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), os.getenv('DATA_DIR'))
TELEGRAM_DIR = os.path.join(DATA_DIR, os.getenv('TELEGRAM_DIR'))
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

STATIC_DIR = os.path.join(os.path.dirname(__file__), os.getenv('STATIC_DIR'))

application = Flask(__name__)
application.config['CORS_HEADERS'] = 'Content-Type'
application.config['CORS_RESOURCES'] = {r'/api/*': {'origins': '*'}}
application.config['PROPAGATE_EXCEPTIONS'] = True

mongo_client = MongoClient('localhost', 27017)
telegram_db = mongo_client['telegram']
message_collection = telegram_db['message']
user_collection = telegram_db['user']
chat_collection = telegram_db['chat']
channel_collection = telegram_db['channel']

os.makedirs(TELEGRAM_DIR, exist_ok=True)

USER_SESSION_DIR = os.path.join(TELEGRAM_DIR, 'user_session')
BOT_SESSION_DIR = os.path.join(TELEGRAM_DIR, 'bot_session')

user_client = TelegramClient(USER_SESSION_DIR, int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
bot_client = TelegramClient(BOT_SESSION_DIR, int(TELEGRAM_API_ID), TELEGRAM_API_HASH)

bot_id = None
telegram_loop = None


@user_client.on(events.NewMessage())
async def handle_user_message(event):
    print(f'handle_user_message')
    await _common_handler(event, user_client)


@bot_client.on(events.NewMessage())
async def handle_bot_message(event):
    print(f'handle_bot_message')
    await _common_handler(event, bot_client)


async def _common_handler(event, client):
    sender = await event.get_sender()
    user_id = None
    target_id = None
    if isinstance(sender, tl.User):
        print(f'[_common_handler] sender (user): {sender}')
        upsert_user(sender)
        user_id = sender.id
    elif isinstance(sender, tl.Chat):
        print(f'[_common_handler] sender (chat): {sender}')
        upsert_chat(sender)
    elif isinstance(sender, tl.Channel):
        print(f'[_common_handler] sender (channel): {sender}')
        upsert_channel(sender)
    chat = await event.get_chat()
    source_id = None
    tag = None
    if isinstance(chat, tl.User):
        print(f'[_common_handler] chat (user): {chat}')
        upsert_user(chat)
        target_id = chat.id
        tag = 'private'
    elif isinstance(chat, tl.Chat):
        print(f'[_common_handler] chat (chat): {chat}')
        upsert_chat(chat)
        source_id = chat.id
        tag = 'group'
        participants = await client.get_participants(chat)
        for p in participants:
            print(f"- {p.id}: {p.first_name} {p.last_name or ''} {p.username or ''} {p.phone or ''}")
            upsert_user(p)
    elif isinstance(chat, tl.Channel):
        print(f'[_common_handler] chat (channel): {chat}')
        upsert_channel(chat)
        source_id = chat.id
        tag = 'channel'
        participants = await client.get_participants(chat)
        for p in participants:
            print(f"- {p.id}: {p.first_name} {p.last_name or ''} {p.username or ''}  {p.phone or ''}")
            upsert_user(p)
    print(f'[_common_handler] tag: {tag}')
    message = event.message
    print(f'[_common_handler] message: {message}')
    timestamp = datetime.now()
    if message.message:
        insert_message('text', message.message, tag, source_id, user_id, target_id, timestamp)
    if any((message.photo, message.video, message.document, message.voice, message.audio)):
        file_name, mtype = await save_media(message)
        print(f'[_common_handler] file_name: {file_name}, mtype: {mtype}')
        insert_message(mtype, file_name, tag, source_id, user_id, target_id, timestamp)


async def save_media(message):
    if not (message.photo or message.video or message.document or message.voice or message.audio):
        return '', ''
    mime = message.file.mime_type or ''
    ext = mimetypes.guess_extension(mime) or '.bin'
    file_name = f'{uuid.uuid4().hex}{ext}'
    await message.download_media(file=os.path.join(TELEGRAM_DIR, file_name))
    if message.photo:
        return file_name, 'photo'
    if message.video:
        return file_name, 'video'
    if message.voice or message.audio:
        return file_name, 'audio'
    return file_name, 'document'


def upsert_user(user: tl.User):
    timestamp = datetime.now()
    user_collection.update_one(
        {'user_id': user.id},
        {
            '$set': {
                'username': user.username,
                'first_name': user.first_name,
                'last_name':  user.last_name,
                'phone': user.phone,
                'is_self': user.is_self,
                'updated_at': timestamp
            },
            '$setOnInsert': {
                'created_at': timestamp
            }
        },
        upsert=True
    )


def upsert_chat(chat: tl.Chat):
    timestamp = datetime.now()
    chat_collection.update_one(
        {'chat_id': chat.id},
        {
            '$set': {
                'title': chat.title,
                'updated_at': timestamp
            },
            '$setOnInsert': {
                'created_at': timestamp
            }
        },
        upsert=True
    )


def upsert_channel(channel: tl.Channel):
    timestamp = datetime.now()
    channel_collection.update_one(
        {'channel_id': channel.id},
        {
            '$set': {
                'title': channel.title,
                'username': channel.username,
                'updated_at': timestamp
            },
            '$setOnInsert': {
                'created_at': timestamp
            }
        },
        upsert=True
    )


def insert_message(message_type, message_content, source_type, source_id, user_id, target_id, timestamp):
    message_doc = {
        'bot_id': bot_id,
        'message_type': message_type,
        'message_content': message_content,
        'source_type': source_type,
        'source_id': source_id,
        'user_id': user_id,
        'target_id': target_id,
        'created_at': timestamp,
        'updated_at': timestamp
    }
    message_collection.insert_one(message_doc)


async def bootstrap():
    global bot_id, telegram_loop
    await user_client.start()
    await bot_client.start(bot_token=TELEGRAM_BOT_TOKEN)
    print('>>> Start Listening ...')
    bot_id = (await bot_client.get_me()).id
    telegram_loop = asyncio.get_running_loop()
    print(f'[bootstrap] Bot started. bot_id={bot_id}')
    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected()
    )


def start_telethon_loop():
    asyncio.run(bootstrap())


@application.route('/', methods=['GET'])
def test():
    return 'OK'


@application.route('/data/telegram/<path:filename>', methods=['GET'])
def serve_file(filename):
    try:
        return send_from_directory(TELEGRAM_DIR, filename, as_attachment=False)
    except FileNotFoundError:
        abort(404, description='File not found')


@application.route('/telegram', methods=['GET'])
def serve_html():
    return send_from_directory(STATIC_DIR, 'telegram.html')


@application.route('/api/sources', methods=['GET'])
def get_sources():
    sources = []
    for user in user_collection.find({'is_self': False}):
        sources.append({
            'type': 'private',
            'id': user['user_id'],
            'name': user['username']
        })
    for chat in chat_collection.find():
        sources.append({
            'type': 'group',
            'id': chat['chat_id'],
            'name': chat['title']
        })
    for channel in channel_collection.find():
        sources.append({
            'type': 'channel',
            'id': channel['channel_id'],
            'name': channel['title']
        })
    return jsonify(sources)


@application.route('/api/messages', methods=['GET'])
def api_messages():
    source_type = request.args.get('source_type')
    source_id = request.args.get('source_id')
    user_id = request.args.get('user_id')
    if source_id:
        query = {
            'source_type': source_type,
            'source_id': int(source_id)
        }
    elif user_id:
        query = {
            'source_type': source_type,
            '$or': [
                {'user_id': int(user_id)},
                {'target_id': int(user_id)}
            ]
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
            'user_id': row.get('user_id'),
            'target_id': row.get('target_id'),
            'user_name': user.get('username') if user else user_id,
            'timestamp': row.get('created_at').strftime('%Y-%m-%d %H:%M:%S')
        })
    return jsonify(messages)


@application.route('/api/send_message', methods=['POST'])
def send_message():
    data = request.json
    source_type = data.get('source_type')
    target_id = data.get('target_id')
    message = data.get('message')
    if not all([source_type, target_id, message]):
        return jsonify({'error': 'Missing required parameters'}), 400
    try:
        print('[send_message] telegram_loop ->', telegram_loop)
        coroutine = bot_client.send_message(int(target_id), message)
        asyncio.run_coroutine_threadsafe(coroutine, telegram_loop)
        return jsonify({'status': 'Message sent'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    t = threading.Thread(target=start_telethon_loop, daemon=True)
    t.start()
    application.run(host='0.0.0.0', port=5050)
