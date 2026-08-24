import aiohttp, asyncio, warnings, pytz
from datetime import datetime, timedelta
from pytz import timezone

# ── Kurigram monkey-patches ────────────────────────────────────────────────
# Force User.mention to produce safe HTML with quoted href attribute
# (Kurigram's HTML parser is stricter than Pyrogram 2.x)
from pyrogram.types import User as _PyroUser
from html import escape as _html_escape

@property
def _safe_mention(self):
    name = _html_escape(self.first_name or str(self.id))
    return f'<a href="tg://user?id={self.id}">{name}</a>'

_PyroUser.mention = _safe_mention

# Monkey-patch : InlineKeyboardButton → Button intelligent (couleurs automatiques)
# ❌/annuler/cancel → rouge (DANGER) | ✅/confirmer/oui → vert (SUCCESS)
import pyrogram.types as _pyro_types
from button import Button as _SmartButton
_pyro_types.InlineKeyboardButton = _SmartButton

# Monkey-patch pour AnimatedChatPhoto._parse (fix bug Kurigram si profil photo vide/invalide)
if hasattr(_pyro_types, "AnimatedChatPhoto"):
    _orig_anim_parse = getattr(_pyro_types.AnimatedChatPhoto, "_parse", None)
    async def _safe_anim_parse(client, chat_photo):
        try:
            if not getattr(chat_photo, "video_sizes", None):
                return None
            return await _orig_anim_parse(client, chat_photo)
        except Exception:
            return None
    _pyro_types.AnimatedChatPhoto._parse = staticmethod(_safe_anim_parse)
# ──────────────────────────────────────────────────────────────────────────


from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from config import settings
from database.data import hyoshcoder
from aiohttp import web
from route import web_server
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import time
from dotenv import load_dotenv
load_dotenv()

Config = settings
SUPPORT_CHAT = -1002312649950

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

    async def start(self, *args, **kwargs):
        await super().start(*args, **kwargs)
        # Charger les configurations de /bset sauvegardées dans MongoDB
        try:
            from config import config_dict
            db_cfg = await hyoshcoder.load_db_config()
            for k, v in db_cfg.items():
                if k == "_id":
                    continue
                config_dict[k] = v
                if hasattr(settings, k):
                    setattr(settings, k, v)
        except Exception as _cfg_err:
            print(f"Error loading DB config at startup: {_cfg_err}")

        # Migration : Définir video_cover=True pour tous les utilisateurs existants où il est absent
        try:
            await hyoshcoder.migrate_video_cover_default()
        except Exception as _mig_err:
            print(f"Error migrating video_cover: {_mig_err}")

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
                BotCommand("cleanup", "Libérer le sémaphore et la file d'attente 🧹"),
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
                    caption=(
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

if __name__ == "__main__":
    Bot().run()