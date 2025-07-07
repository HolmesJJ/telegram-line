import os
import asyncio

from dotenv import load_dotenv
from telethon import events
from telethon import TelegramClient


load_dotenv()

DATA_DIR = os.getenv('DATA_DIR')
TELEGRAM_DIR = os.path.join(DATA_DIR, os.getenv('TELEGRAM_DIR'))
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

USER_SESSION_DIR = os.path.join(TELEGRAM_DIR, 'user_session')
BOT_SESSION_DIR = os.path.join(TELEGRAM_DIR, 'bot_session')

user_client = TelegramClient(USER_SESSION_DIR, int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
bot_client = TelegramClient(BOT_SESSION_DIR, int(TELEGRAM_API_ID), TELEGRAM_API_HASH)


@user_client.on(events.NewMessage())
async def handle_user_message(event):
    print(f'handle_user_message')
    chat = await event.get_chat()
    sender = await event.get_sender()
    print(f'[CHAT]{chat}')
    print(f'[sender]{sender}')
    print(f'[EVENT]{event}')


@bot_client.on(events.NewMessage())
async def handle_bot_message(event):
    print(f'handle_bot_message')
    chat = await event.get_chat()
    sender = await event.get_sender()
    print(f'[CHAT]{chat}')
    print(f'[sender]{sender}')
    print(f'[EVENT]{event}')


async def run():
    await user_client.start()
    await bot_client.start(bot_token=TELEGRAM_BOT_TOKEN)
    print('>>> Start Listening ...')
    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected(),
    )


if __name__ == '__main__':
    asyncio.run(run())
