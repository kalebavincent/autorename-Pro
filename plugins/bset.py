"""
Plugin : /bset — Réglages et Variables Globales du Bot (Admin/Owner)
Permet de visualiser, éditer et sauvegarder les variables de configuration en temps réel.
"""
import asyncio
import os
from time import time
from functools import partial
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.handlers import MessageHandler
from config import settings, config_dict
from database.data import hyoshcoder
from helpers.security import mask_sensitive_value

START = 0
STATE = 'view'
handler_dict = {}

# Copie des valeurs par défaut au démarrage
default_values = dict(config_dict)


def is_admin_user(user_id: int) -> bool:
    """Vérifie si l'utilisateur est dans la liste des ADMINS."""
    admins = settings.ADMIN
    if not admins:
        return False
    if isinstance(admins, (list, set, tuple)):
        return user_id in admins or str(user_id) in [str(a) for a in admins]
    return str(user_id) == str(admins)


class ButtonMaker:
    def __init__(self):
        self._button = []
        self._header_button = []
        self._footer_button = []

    def reset(self):
        self._button.clear()
        self._header_button.clear()
        self._footer_button.clear()

    def button_data(self, key, data, position=None):
        btn = InlineKeyboardButton(text=key, callback_data=data)
        if position == 'header':
            self._header_button.append(btn)
        elif position == 'footer':
            self._footer_button.append(btn)
        else:
            self._button.append(btn)

    def build_menu(self, b_cols=2, h_cols=8, f_cols=8):
        menu = [self._button[i:i + b_cols] for i in range(0, len(self._button), b_cols)]
        if self._header_button:
            if len(self._header_button) > h_cols:
                header_buttons = [self._header_button[i:i + h_cols] for i in range(0, len(self._header_button), h_cols)]
                menu = header_buttons + menu
            else:
                menu.insert(0, self._header_button)
        if self._footer_button:
            if len(self._footer_button) > f_cols:
                footer_buttons = [self._footer_button[i:i + f_cols] for i in range(0, len(self._footer_button), f_cols)]
                menu.extend(footer_buttons)
            else:
                menu.append(self._footer_button)
        return InlineKeyboardMarkup(menu) if len(menu) else None


async def get_buttons(key=None, edit_type=None):
    buttons = ButtonMaker()
    if key is None:
        buttons.button_data('⚙️ Variables du Bot', 'botset var')
        buttons.button_data('📁 Fichiers Privés', 'botset private')
        buttons.button_data('❌ Fermer', 'botset close', 'footer')
        msg = '<b>⚙️ PARAMÈTRES ET CONFIGURATION DU BOT</b>'
    elif edit_type is not None:
        if edit_type == 'botvar':
            buttons.button_data('<<', 'botset var')
            if key not in ['API_HASH', 'API_ID', 'BOT_TOKEN', 'DATA_URI']:
                buttons.button_data('🔄 Défaut', f'botset resetvar {key}')
            buttons.button_data('❌ Fermer', 'botset close')
            masked_val = mask_sensitive_value(key, str(config_dict.get(key, '')))
            msg = f'Envoyez une valeur valide pour <b>{key}</b>.\nValeur actuelle : <b>{masked_val}</b>.\n\n<i>Délai d\'expiration : 60s.</i>'
    elif key == 'var':
        all_keys = list(config_dict.keys())
        for k in all_keys[START:20 + START]:
            buttons.button_data(k, f'botset botvar {k}')
        if STATE == 'view':
            buttons.button_data('✏️ Passer en Mode Édition', 'botset edit var')
        else:
            buttons.button_data('👁️ Passer en Mode Lecture', 'botset view var')
        buttons.button_data('<<', 'botset back')
        buttons.button_data('❌ Fermer', 'botset close')
        for x in range(0, len(all_keys), 20):
            buttons.button_data(str(int(x/20) + 1), f'botset start var {x}', 'footer')
        msg = f'<b>⚙️ BOT VARIABLES ~ Page {int(START/20) + 1}\nMode actuel :</b> {STATE.upper()}'
    elif key == 'private':
        buttons.button_data('<<', 'botset back')
        buttons.button_data('❌ Fermer', 'botset close')
        msg = ('<b>📁 FICHIERS DE CONFIGURATION PRIVÉS</b>\n\n'
               '<b>┌</b> <code>.env</code>\n'
               '<b>├</b> <code>config.py</code>\n'
               '<b>├</b> <code>docker-compose.yml</code>\n'
               '<b>└</b> <code>requirements.txt</code>\n\n'
               '<i>Ces fichiers sont protégés et gérés sur le serveur.</i>')

    return msg, buttons.build_menu(2)


async def update_buttons(message: Message, key: str = None, edit_type: str = None):
    try:
        msg, buttons = await get_buttons(key, edit_type)
        await message.edit_text(msg, reply_markup=buttons)
    except Exception as e:
        if "MESSAGE_NOT_MODIFIED" not in str(e):
            print(f"Erreur dans update_buttons: {e}")


import re

def parse_config_value(key: str, raw_value: str):
    raw_value = raw_value.strip()
    if key in ["ADMIN"]:
        parts = re.split(r'[\s,]+', raw_value)
        return [int(x) if x.lstrip('-').isdigit() else x for x in parts if x]
    elif key in ["FORCE_SUB_CHANNELS"]:
        parts = re.split(r'[\s,]+', raw_value)
        return [x.strip() for x in parts if x.strip()]
    elif key in ["WEBHOOK"]:
        return raw_value.lower() in ("true", "1", "yes", "on")
    elif key in ["API_ID", "LOG_CHANNEL", "CHANNEL_LOG", "DUMP_CHANNEL", "BACKUP_GROUP_ID", "DAILY_BACKUP_POINTS", "PORT"]:
        if raw_value.lstrip('-').isdigit():
            return int(raw_value)
        return raw_value
    return raw_value


async def edit_variable(_, message: Message, omsg: Message, key: str):
    handler_dict[message.chat.id] = False
    raw_text = message.text.strip()
    parsed_value = parse_config_value(key, raw_text)

    config_dict[key] = parsed_value
    await hyoshcoder.update_db_config({key: parsed_value})

    if hasattr(settings, key):
        setattr(settings, key, parsed_value)

    try:
        await message.delete()
    except Exception:
        pass
    await update_buttons(omsg, 'var')


async def event_handler(client: Client, query: CallbackQuery, pfunc: partial, rfunc: partial):
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    handler_dict[chat_id] = True
    start_time = time()

    def event_filter(_, __, event):
        if not event or not event.from_user:
            return False
        return bool(event.from_user.id == user_id and event.chat.id == chat_id and event.text)

    handler = client.add_handler(MessageHandler(pfunc, filters=filters.create(event_filter)), group=-1)
    while handler_dict.get(chat_id, False):
        await asyncio.sleep(0.5)
        if time() - start_time > 60:
            handler_dict[chat_id] = False
            await rfunc()

    try:
        if isinstance(handler, tuple):
            client.remove_handler(handler[0], handler[1])
        else:
            client.remove_handler(handler)
    except Exception as e:
        print(f"Error removing handler: {e}")


@Client.on_callback_query(filters.regex(r'^botset'))
async def edit_bot_settings(client: Client, query: CallbackQuery):
    global START, STATE
    message = query.message
    data = query.data.split()
    user_id = query.from_user.id

    if not is_admin_user(user_id):
        await query.answer("⚠️ Action réservée aux administrateurs du bot !", show_alert=True)
        return

    handler_dict[message.chat.id] = False

    if data[1] == 'close':
        await query.answer()
        await message.delete()
    elif data[1] == 'back':
        await query.answer()
        START = 0
        await update_buttons(message, None)
    elif data[1] in ['var', 'private']:
        await query.answer()
        await update_buttons(message, data[1])
    elif data[1] == 'resetvar':
        await query.answer("Réinitialisé par défaut !")
        key = data[2]
        value = default_values.get(key, "")
        config_dict[key] = value
        await hyoshcoder.update_db_config({key: value})
        if hasattr(settings, key):
            setattr(settings, key, value)
        await update_buttons(message, 'var')
    elif data[1] == 'botvar' and STATE == 'edit':
        await query.answer()
        pfunc = partial(edit_variable, omsg=message, key=data[2])
        rfunc = partial(update_buttons, message, 'var')
        await update_buttons(message, data[2], data[1])
        asyncio.create_task(event_handler(client, query, pfunc, rfunc))
    elif data[1] == 'botvar' and STATE == 'view':
        key = data[2]
        value = config_dict.get(key, "")
        masked_val = mask_sensitive_value(key, str(value))
        await query.answer(f"{key}: {masked_val}", show_alert=True)
    elif data[1] == 'edit':
        STATE = 'edit'
        await query.answer("Mode Édition activé ✏️")
        await update_buttons(message, data[2])
    elif data[1] == 'view':
        STATE = 'view'
        await query.answer("Mode Lecture activé 👁️")
        await update_buttons(message, data[2])
    elif data[1] == 'start':
        await query.answer()
        if START != int(data[3]):
            START = int(data[3])
            await update_buttons(message, data[2])


@Client.on_message(filters.private & filters.command(["bset", "botsetting", "botsettings"]))
async def bot_settings(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_admin_user(user_id):
        await message.reply_text("⛔ **Commande réservée aux administrateurs du bot.**")
        return
    handler_dict[message.chat.id] = False
    msg, buttons = await get_buttons()
    await message.reply_text(msg, reply_markup=buttons)
