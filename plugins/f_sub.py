import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.errors import UserNotParticipant
from config import settings
from helpers.utils import get_random_photo

logger = logging.getLogger(__name__)


def _get_channels():
    channels = settings.FORCE_SUB_CHANNELS
    if isinstance(channels, str):
        channels = [c.strip() for c in channels.split(",") if c.strip()]
    elif isinstance(channels, list):
        channels = [c for c in channels if c]
    return channels or []


async def not_subscribed(_, __, message):
    if not message.from_user:
        return False
    channels = _get_channels()
    if not channels:
        return False

    for channel in channels:
        try:
            target = int(channel) if str(channel).startswith("-100") or str(channel).lstrip("-").isdigit() else str(channel)
            user = await message._client.get_chat_member(target, message.from_user.id)
            if user.status in {"kicked", "left"}:
                return True
        except UserNotParticipant:
            return True
        except Exception as e:
            # Si le bot n'a pas accès au canal ou ID invalide, ne pas bloquer les utilisateurs
            logger.warning(f"f_sub check failed for channel {channel}: {e}")
            continue
    return False


@Client.on_message(filters.private & filters.create(not_subscribed))
async def forces_sub(client, message):
    IMAGE_URL = await get_random_photo()
    not_joined_channels = []
    channels = _get_channels()

    for channel in channels:
        try:
            target = int(channel) if str(channel).startswith("-100") or str(channel).lstrip("-").isdigit() else str(channel)
            user = await client.get_chat_member(target, message.from_user.id)
            if user.status in {"kicked", "left"}:
                not_joined_channels.append(str(channel))
        except UserNotParticipant:
            not_joined_channels.append(str(channel))
        except Exception:
            continue

    if not not_joined_channels:
        return

    buttons = []
    for channel in not_joined_channels:
        ch_str = str(channel)
        url = f"https://t.me/{ch_str}" if not ch_str.startswith("-") else "https://t.me"
        buttons.append([
            InlineKeyboardButton(
                text=f"• ʀᴇᴊᴏɪɴᴅʀᴇ {ch_str.capitalize()} •", url=url
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="• ᴊ'ᴀɪ ʀᴇᴊᴏɪɴᴛ •", callback_data="check_subscription"
        )
    ])

    text = "**ʙᴀᴋᴀᴋᴀ !!, ᴠᴏᴜs ɴ'ᴇ̂ᴛᴇs ᴘᴀs ᴀʙᴏɴɴᴇ́ ᴀ̀ ᴛᴏᴜs ʟᴇs ᴄᴀɴᴀᴜx ʀᴇǫᴜɪs, ʀᴇᴊᴏɪɢɴᴇᴢ ʟᴇs ᴄᴀɴᴀᴜx ᴅᴇ ᴍɪsᴇ ᴀ̀ ᴊᴏᴜʀ ᴘᴏᴜʀ ᴄᴏɴᴛɪɴᴜᴇʀ.**"
    try:
        await message.reply_photo(
            photo=IMAGE_URL,
            caption=text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Failed to send forces_sub message: {e}")


@Client.on_callback_query(filters.regex("check_subscription"))
async def check_subscription(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    not_joined_channels = []
    channels = _get_channels()

    for channel in channels:
        try:
            target = int(channel) if str(channel).startswith("-100") or str(channel).lstrip("-").isdigit() else str(channel)
            user = await client.get_chat_member(target, user_id)
            if user.status in {"kicked", "left"}:
                not_joined_channels.append(str(channel))
        except UserNotParticipant:
            not_joined_channels.append(str(channel))
        except Exception:
            continue

    if not not_joined_channels:
        await callback_query.answer("✅ Merci d'avoir rejoint tous les canaux !", show_alert=True)
        new_text = "**ᴠᴏᴜs ᴇ̂ᴛᴇs ᴀʙᴏɴɴᴇ́ ᴀ̀ ᴛᴏᴜs ʟᴇs ᴄᴀɴᴀᴜx ʀᴇǫᴜɪs. ᴍᴇʀᴄɪ ! 😊 /start ᴍᴀɪɴᴛᴇɴᴀɴᴛ.**"
        try:
            if callback_query.message.caption != new_text:
                await callback_query.message.edit_caption(
                    caption=new_text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("• ᴄʟɪǫᴜᴇᴢ ɪᴄɪ ᴍᴀɪɴᴛᴇɴᴀɴᴛ •", callback_data='help')]
                    ])
                )
        except Exception:
            pass
    else:
        await callback_query.answer("⚠️ Vous n'avez pas encore rejoint tous les canaux.", show_alert=True)
        buttons = []
        for channel in not_joined_channels:
            ch_str = str(channel)
            url = f"https://t.me/{ch_str}" if not ch_str.startswith("-") else "https://t.me"
            buttons.append([
                InlineKeyboardButton(
                    text=f"• ʀᴇᴊᴏɪɴᴅʀᴇ {ch_str.capitalize()} •", url=url
                )
            ])
        buttons.append([
            InlineKeyboardButton(
                text="• ᴊ'ᴀɪ ʀᴇᴊᴏɪɴᴛ •", callback_data="check_subscription"
            )
        ])

        text = "**ᴠᴏᴜs ᴇ̂ᴛᴇs ᴀʙᴏɴɴᴇ́ ᴀ̀ ᴛᴏᴜs ʟᴇs ᴄᴀɴᴀᴜx ʀᴇǫᴜɪs. ᴠᴇᴜɪʟʟᴇᴢ ʀᴇᴊᴏɪɴᴅʀᴇ ʟᴇs ᴄᴀɴᴀᴜx ᴅᴇ ᴍɪsᴇ ᴀ̀ ᴊᴏᴜʀ ᴘᴏᴜʀ ᴄᴏɴᴛɪɴᴜᴇʀ.**"
        try:
            if callback_query.message.caption != text:
                await callback_query.message.edit_caption(
                    caption=text,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
        except Exception:
            pass
