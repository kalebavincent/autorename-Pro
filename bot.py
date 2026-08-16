import aiohttp, asyncio, warnings, pytz
from datetime import datetime, timedelta
from pytz import timezone
from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from config import settings
from database.data import hyoshcoder
from aiohttp import web
from route import web_server
import pyrogram.utils
import pyromod
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import time
from dotenv import load_dotenv
load_dotenv()

pyrogram.utils.MIN_CHANNEL_ID =-1000000000000
Config = settings
SUPPORT_CHAT =-1002312649950

class Bot(Client):

    def __init__(self):
        super().__init__(
            name="autorename",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=200,
            plugins={"root": "plugins"},
            sleep_threshold=15,
        )
        self.start_time = time.time()

    async def start(self):
        await super().start()
        me = await self.get_me()
        self.mention = me.mention
        self.username = me.username  
        self.uptime = Config.BOT_UPTIME     
        if Config.WEBHOOK:
            app = web.AppRunner(await web_server())
            await app.setup()       
            await web.TCPSite(app, "0.0.0.0", 8080).start()     
        print(f"{me.first_name} Is Started.....✨️")

        # Configuration des commandes du bot dans Telegram
        try:
            from pyrogram.types import (
                BotCommand,
                BotCommandScopeAllPrivateChats,
                BotCommandScopeAllGroupChats,
                BotCommandScopeChat,
            )
            private_commands = [
                BotCommand("start", "Démarrer le bot 🚀"),
                BotCommand("uset", "Mes paramètres (miniature, caption, police, etc.) ⚙️"),
                BotCommand("ilove_thebot", "Obtenir le lien du groupe pour vos points 💙"),
                BotCommand("set_font", "Choisir une police 🎨"),
                BotCommand("autorename", "Définir le modèle de renommage 🏷️"),
                BotCommand("bset", "Réglages globaux du bot (Admin) ⚙️"),
                BotCommand("help", "Aide et fonctionnalités ❓"),
                BotCommand("profile", "Mon profil et mes points 👤"),
            ]
            await self.set_bot_commands(private_commands, scope=BotCommandScopeAllPrivateChats())

            group_commands = [
                BotCommand("ilove_thebot", "Régénérer mes points de secours journaliers 💙"),
            ]
            await self.set_bot_commands(group_commands, scope=BotCommandScopeAllGroupChats())

            if Config.BACKUP_GROUP_ID:
                try:
                    await self.set_bot_commands(group_commands, scope=BotCommandScopeChat(chat_id=Config.BACKUP_GROUP_ID))
                except Exception as ex:
                    print(f"Failed to set bot commands for backup group: {ex}")

        except Exception as e:
            print(f"Failed to set bot commands: {e}")

        uptime_seconds = int(time.time() - self.start_time)
        uptime_string = str(timedelta(seconds=uptime_seconds))
        await hyoshcoder.clear_all_user_channels()
        for chat_id in [Config.LOG_CHANNEL, SUPPORT_CHAT]:
            try:
                curr = datetime.now(pytz.timezone("Africa/Lubumbashi"))
                date = curr.strftime('%d %B, %Y')
                time_str = curr.strftime('%I:%M:%S %p')
                
                await self.send_photo(
                    chat_id=chat_id,
                    photo="https://telegra.ph/file/41a6574ff59f886a79071.jpg",
                    caption = (
                        "**Hinata ᴇsᴛ ʀᴇᴅᴇᴍᴀʀʀᴇᴇ ᴇɴᴄᴏʀᴇ !**\n\n"
                        f"ᴊᴇ ɴ'ᴀɪ ᴘᴀs ᴅᴏʀᴍɪs ᴅᴇᴘᴜɪs​ : `{uptime_string}`"
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        [[
                            InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇs", url="https://t.me/hyoshmangavf")
                        ]]
                    )
                )

            except Exception as e:
                print(f"Failed to send message in chat {chat_id}: {e}")

Bot().run()