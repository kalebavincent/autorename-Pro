"""
Plugin : Menu Paramètres Utilisateur (/uset /settings) pour AutoRename Pro
Permet de gérer la miniature, la caption, la police, le format de renommage,
les métadonnées, le mode séquentiel et la source d'extraction avec des boutons interactifs.
"""
import asyncio
from functools import partial
from time import time

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
)

from database.data import hyoshcoder
from config import settings
from helpers.font import AVAILABLE_FONTS, FONT_PREVIEWS, FONT_EMOJIS
from plugins.backup_points import get_valid_backup_points

handler_dict = {}

def _check(value) -> str:
    return "✅" if value else "☑️"


# ──────────────────────────────────────────────────────────────────────────────
# Textes et Claviers principaux
# ──────────────────────────────────────────────────────────────────────────────

async def build_main_text_and_keyboard(user_id: int):
    user_data = await hyoshcoder.read_user(user_id)
    if not user_data:
        user_data = {}

    sub_points  = user_data.get("points", 0)
    bp, _, _    = await get_valid_backup_points(user_id)

    thumb        = user_data.get("file_id", None)
    caption      = user_data.get("caption", None)
    font         = user_data.get("font", None)
    template     = user_data.get("format_template", None)
    sequential   = user_data.get("sequential_mode", False)
    src_info     = user_data.get("scr_info", "file_name")
    metadata     = user_data.get("metadata", True)
    meta_code    = user_data.get("metadata_code", "@hyoshassistantbot")
    video_cover  = user_data.get("video_cover", True)
    media_pref   = (user_data.get("media_type") or user_data.get("media_preference") or "document").lower()

    font_preview    = f"{FONT_EMOJIS.get(font,'▪️')} {FONT_PREVIEWS.get(font, font)}" if font else "aucune"
    caption_preview = f"`{caption[:30]}...`" if caption and len(caption) > 30 else (f"`{caption}`" if caption else "aucune")
    template_str    = f"`{template}`" if template else "non défini"
    src_str         = "Nom du fichier" if src_info == "file_name" else "Caption"
    media_icon      = "🎥" if media_pref == "video" else ("🎵" if media_pref == "audio" else "📄")

    text = (
        "⚙️ **Mes Paramètres AutoRename Pro**\n\n"
        f"💳 **Points d'abonnement** : `{sub_points}`\n"
        f"🔋 **Points de secours (00:00 UTC)** : `{bp}/{settings.DAILY_BACKUP_POINTS}`\n\n"
        f"🖼️ **Miniature**    : {_check(thumb)} {'définie' if thumb else 'non définie'}\n"
        f"📝 **Caption**      : {_check(caption)} {caption_preview}\n"
        f"🎨 **Police**       : {_check(font)} {font_preview}\n"
        f"🏷️ **Modèle**       : {template_str}\n"
        f"🔄 **Séquentiel**   : {_check(sequential)} {'Activé' if sequential else 'Désactivé'}\n"
        f"📌 **Extraire de**  : `{src_str}`\n"
        f"🏷️ **Métadonnées**  : {_check(metadata)} {'Active' if metadata else 'Inactive'}\n"
        f"🎞️ **Video Cover**  : {_check(video_cover)} {'Activé' if video_cover else 'Désactivé'}\n"
        f"📂 **Envoi comme**  : {media_icon} `{media_pref.upper()}`\n"
    )

    rows = [
        [
            InlineKeyboardButton(f"{_check(thumb)} 🖼️ Miniature", callback_data=f"uset {user_id} thumb"),
            InlineKeyboardButton(f"{_check(caption)} 📝 Caption", callback_data=f"uset {user_id} caption"),
        ],
        [
            InlineKeyboardButton(f"{_check(font)} 🎨 Police {'`'+font+'`' if font else ''}", callback_data=f"uset {user_id} font"),
            InlineKeyboardButton("🏷️ Modèle Nom", callback_data=f"uset {user_id} template"),
        ],
        [
            InlineKeyboardButton(f"{_check(sequential)} 🔄 Mode Séquentiel", callback_data=f"uset {user_id} toggle_seq"),
            InlineKeyboardButton(f"📍 Extraire: {src_str}", callback_data=f"uset {user_id} toggle_src"),
        ],
        [
            InlineKeyboardButton(f"{_check(metadata)} 🏷️ Métadonnées", callback_data=f"uset {user_id} toggle_meta"),
            InlineKeyboardButton(f"{_check(video_cover)} 🎞️ Video Cover", callback_data=f"uset {user_id} toggle_cover"),
        ],
        [
            InlineKeyboardButton(f"{media_icon} Envoi: {media_pref.upper()}", callback_data=f"uset {user_id} toggle_media"),
            InlineKeyboardButton("💳 Mes Points / Plan", callback_data=f"uset {user_id} points_info"),
        ],
        [
            InlineKeyboardButton("❌ Fermer", callback_data=f"uset {user_id} close"),
        ],
    ]
    return text, InlineKeyboardMarkup(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Claviers des sous-menus
# ──────────────────────────────────────────────────────────────────────────────

async def build_thumb_keyboard(user_id: int) -> InlineKeyboardMarkup:
    thumb = await hyoshcoder.get_thumbnail(user_id)
    rows = []
    if thumb:
        rows.append([
            InlineKeyboardButton("👁️ Voir miniature", callback_data=f"uset {user_id} viewthumb"),
            InlineKeyboardButton("🗑️ Supprimer", callback_data=f"uset {user_id} delthumb"),
        ])
    rows.append([
        InlineKeyboardButton("📤 Définir une miniature", callback_data=f"uset {user_id} setthumb"),
    ])
    rows.append([
        InlineKeyboardButton("🔙 Retour", callback_data=f"uset {user_id} back"),
        InlineKeyboardButton("❌ Fermer", callback_data=f"uset {user_id} close"),
    ])
    return InlineKeyboardMarkup(rows)


async def build_caption_keyboard(user_id: int) -> InlineKeyboardMarkup:
    caption = await hyoshcoder.get_caption(user_id)
    rows = []
    if caption:
        rows.append([
            InlineKeyboardButton("✏️ Modifier", callback_data=f"uset {user_id} setcaption"),
            InlineKeyboardButton("🗑️ Supprimer", callback_data=f"uset {user_id} delcaption"),
        ])
    else:
        rows.append([
            InlineKeyboardButton("➕ Définir caption", callback_data=f"uset {user_id} setcaption"),
        ])
    rows.append([
        InlineKeyboardButton("🔙 Retour", callback_data=f"uset {user_id} back"),
        InlineKeyboardButton("❌ Fermer", callback_data=f"uset {user_id} close"),
    ])
    return InlineKeyboardMarkup(rows)


async def build_font_keyboard(user_id: int) -> InlineKeyboardMarkup:
    current_font = await hyoshcoder.get_font(user_id)
    buttons = []
    row = []
    for i, name in enumerate(AVAILABLE_FONTS):
        emoji = FONT_EMOJIS.get(name, "▪️")
        preview = FONT_PREVIEWS.get(name, name)
        label = f"{'✅ ' if name == current_font else ''}{emoji} {preview}"
        row.append(InlineKeyboardButton(label, callback_data=f"uset {user_id} selfont {name}"))
        if len(row) == 2 or i == len(AVAILABLE_FONTS) - 1:
            buttons.append(row)
            row = []
    if current_font:
        buttons.append([
            InlineKeyboardButton("🗑️ Supprimer la police", callback_data=f"uset {user_id} delfont"),
        ])
    buttons.append([
        InlineKeyboardButton("🔙 Retour", callback_data=f"uset {user_id} back"),
        InlineKeyboardButton("❌ Fermer", callback_data=f"uset {user_id} close"),
    ])
    return InlineKeyboardMarkup(buttons)


# ──────────────────────────────────────────────────────────────────────────────
# Wait for user input helper
# ──────────────────────────────────────────────────────────────────────────────

async def _wait_for_text(client: Client, chat_id: int, user_id: int, got_text_func, timeout=60):
    handler_dict[chat_id] = True
    start_time = time()

    def text_filter(_, __, event: Message):
        if not event.from_user:
            return False
        return event.from_user.id == user_id and event.chat.id == chat_id and event.text

    handler = client.add_handler(MessageHandler(got_text_func, filters=filters.create(text_filter)), group=-1)
    while handler_dict.get(chat_id, False):
        await asyncio.sleep(0.5)
        if time() - start_time > timeout:
            handler_dict[chat_id] = False

    try:
        if isinstance(handler, tuple):
            client.remove_handler(handler[0], handler[1])
        else:
            client.remove_handler(handler)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Callback query handler
# ──────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^uset "))
async def uset_callback(client: Client, query: CallbackQuery):
    parts = query.data.split()
    if len(parts) < 3:
        await query.answer()
        return

    owner_id = int(parts[1])
    action   = parts[2]
    extra    = parts[3] if len(parts) > 3 else None
    caller   = query.from_user.id
    message  = query.message

    if caller != owner_id:
        await query.answer("⛔ Ce menu n'est pas le vôtre !", show_alert=True)
        return

    handler_dict[message.chat.id] = False

    if action == "close":
        await query.answer()
        await message.delete()

    elif action == "back":
        await query.answer()
        txt, kb = await build_main_text_and_keyboard(owner_id)
        await message.edit_text(txt, reply_markup=kb)

    # ── Miniature ──────────────────────────────────────────────────────────
    elif action == "thumb":
        await query.answer()
        thumb = await hyoshcoder.get_thumbnail(owner_id)
        status = "✅ Miniature définie" if thumb else "☑️ Aucune miniature"
        kb = await build_thumb_keyboard(owner_id)
        await message.edit_text(
            f"🖼️ **Gestion de la miniature**\n\n{status}\n\n"
            "Envoyez une photo ou utilisez les boutons ci-dessous.",
            reply_markup=kb
        )

    elif action == "viewthumb":
        await query.answer()
        thumb = await hyoshcoder.get_thumbnail(owner_id)
        if thumb:
            try:
                await client.send_photo(message.chat.id, photo=thumb, caption="🖼️ Votre miniature actuelle")
            except Exception:
                await query.answer("❌ Impossible d'afficher la miniature.", show_alert=True)
        else:
            await query.answer("Aucune miniature.", show_alert=True)

    elif action == "delthumb":
        await query.answer("🗑️ Miniature supprimée !")
        await hyoshcoder.set_thumbnail(owner_id, file_id=None)
        kb = await build_thumb_keyboard(owner_id)
        await message.edit_text("🖼️ **Gestion de la miniature**\n\n☑️ Aucune miniature", reply_markup=kb)

    elif action == "setthumb":
        await query.answer()

        async def got_photo(_, msg: Message):
            handler_dict[message.chat.id] = False
            if msg.photo:
                await hyoshcoder.set_thumbnail(owner_id, msg.photo.file_id)
                try:
                    await msg.delete()
                except Exception:
                    pass
                kb = await build_thumb_keyboard(owner_id)
                await message.edit_text("🖼️ **Gestion de la miniature**\n\n✅ Miniature enregistrée !", reply_markup=kb)

        def photo_filter(_, __, event: Message):
            return event.from_user and event.from_user.id == owner_id and event.chat.id == message.chat.id and event.photo

        await message.edit_text(
            "🖼️ **Envoyez votre photo** maintenant.\n_Délai : 60s_",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Annuler", callback_data=f"uset {owner_id} thumb")]])
        )

        handler_dict[message.chat.id] = True
        start_time = time()
        handler = client.add_handler(MessageHandler(got_photo, filters=filters.create(photo_filter)), group=-1)
        while handler_dict.get(message.chat.id, False):
            await asyncio.sleep(0.5)
            if time() - start_time > 60:
                handler_dict[message.chat.id] = False
        try:
            client.remove_handler(*handler) if isinstance(handler, tuple) else client.remove_handler(handler)
        except Exception:
            pass

    # ── Caption ────────────────────────────────────────────────────────────
    elif action == "caption":
        await query.answer()
        cap = await hyoshcoder.get_caption(owner_id)
        cap_info = f"```{cap}```" if cap else "☑️ Aucune caption définie"
        kb = await build_caption_keyboard(owner_id)
        await message.edit_text(
            f"📝 **Gestion de la Caption**\n\n{cap_info}\n\n"
            "Variables disponibles : `{filename}`, `{filesize}`, `{duration}`",
            reply_markup=kb
        )

    elif action == "delcaption":
        await query.answer("🗑️ Caption supprimée !")
        await hyoshcoder.set_caption(owner_id, caption=None)
        kb = await build_caption_keyboard(owner_id)
        await message.edit_text("📝 **Gestion de la Caption**\n\n☑️ Aucune caption définie", reply_markup=kb)

    elif action == "setcaption":
        await query.answer()

        async def got_caption_msg(_, msg: Message):
            handler_dict[message.chat.id] = False
            new_c = msg.text.strip()
            await hyoshcoder.set_caption(owner_id, caption=new_c)
            try:
                await msg.delete()
            except Exception:
                pass
            kb = await build_caption_keyboard(owner_id)
            await message.edit_text(f"📝 **Gestion de la Caption**\n\n✅ Caption enregistrée !\n\n```{new_c[:150]}```", reply_markup=kb)

        await message.edit_text(
            "📝 **Entrez votre nouvelle caption** :\n\n"
            "Exemple : `📕 Nom : {filename}\n🔗 Taille : {filesize}\n⏰ Durée : {duration}`\n\n_Délai : 60s_",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Annuler", callback_data=f"uset {owner_id} caption")]])
        )
        await _wait_for_text(client, message.chat.id, owner_id, got_caption_msg)

    # ── Police (Font) ──────────────────────────────────────────────────────
    elif action == "font":
        await query.answer()
        font = await hyoshcoder.get_font(owner_id)
        font_info = f"{FONT_EMOJIS.get(font,'▪️')} `{font}` → {FONT_PREVIEWS.get(font, font)}" if font else "☑️ Aucune police définie"
        kb = await build_font_keyboard(owner_id)
        await message.edit_text(f"🎨 **Choisissez votre police**\n\n{font_info}\n\nCliquez sur un style pour l'appliquer.", reply_markup=kb)

    elif action == "selfont" and extra:
        if extra not in AVAILABLE_FONTS:
            await query.answer("❌ Police inconnue.", show_alert=True)
            return
        await hyoshcoder.set_font(owner_id, extra)
        preview = f"{FONT_EMOJIS.get(extra,'▪️')} `{extra}` → {FONT_PREVIEWS.get(extra, extra)}"
        await query.answer(f"✅ Police {extra} enregistrée !")
        kb = await build_font_keyboard(owner_id)
        await message.edit_text(f"🎨 **Choisissez votre police**\n\n{preview}\n\nCliquez sur un style pour l'appliquer.", reply_markup=kb)

    elif action == "delfont":
        await hyoshcoder.del_font(owner_id)
        await query.answer("🗑️ Police supprimée !")
        kb = await build_font_keyboard(owner_id)
        await message.edit_text("🎨 **Choisissez votre police**\n\n☑️ Aucune police définie", reply_markup=kb)

    # ── Template de renommage ──────────────────────────────────────────────
    elif action == "template":
        await query.answer()

        async def got_template_msg(_, msg: Message):
            handler_dict[message.chat.id] = False
            tpl = msg.text.strip()
            await hyoshcoder.set_format_template(owner_id, tpl)
            try:
                await msg.delete()
            except Exception:
                pass
            txt, kb = await build_main_text_and_keyboard(owner_id)
            await message.edit_text(f"✅ Modèle enregistré !\n\n{txt}", reply_markup=kb)

        tpl_curr = await hyoshcoder.get_format_template(owner_id)
        tpl_str  = f"`{tpl_curr}`" if tpl_curr else "aucun"
        await message.edit_text(
            f"🏷️ **Modèle de renommage automatique**\n\n"
            f"📌 Modèle actuel : {tpl_str}\n\n"
            "Tapez le nouveau modèle d'exemple :\n"
            "`MonSuperAnime S{saison}E{episode} [{quality}]`\n\n_Délai : 60s_",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Annuler", callback_data=f"uset {owner_id} back")]])
        )
        await _wait_for_text(client, message.chat.id, owner_id, got_template_msg)

    # ── Toggles ────────────────────────────────────────────────────────────
    elif action == "toggle_seq":
        await hyoshcoder.toggle_sequential_mode(owner_id)
        await query.answer("🔄 Mode séquentiel inversé !")
        txt, kb = await build_main_text_and_keyboard(owner_id)
        await message.edit_text(txt, reply_markup=kb)

    elif action == "toggle_src":
        await hyoshcoder.toogle_src_info(owner_id)
        await query.answer("📍 Source d'extraction inversée !")
        txt, kb = await build_main_text_and_keyboard(owner_id)
        await message.edit_text(txt, reply_markup=kb)

    elif action == "toggle_meta":
        curr = await hyoshcoder.get_metadata(owner_id)
        await hyoshcoder.set_metadata(owner_id, not curr)
        await query.answer("🏷️ Métadonnées inversées !")
        txt, kb = await build_main_text_and_keyboard(owner_id)
        await message.edit_text(txt, reply_markup=kb)

    elif action == "toggle_cover":
        new_val = await hyoshcoder.toggle_video_cover(owner_id)
        status = "✅ Video Cover activé !" if new_val else "☑️ Video Cover désactivé !"
        await query.answer(status)
        txt, kb = await build_main_text_and_keyboard(owner_id)
        await message.edit_text(txt, reply_markup=kb)

    elif action == "toggle_media":
        curr_pref = (await hyoshcoder.get_media_preference(owner_id) or "document").lower()
        next_pref = "video" if curr_pref == "document" else ("audio" if curr_pref == "video" else "document")
        await hyoshcoder.set_media_preference(owner_id, next_pref)
        await query.answer(f"📂 Mode d'envoi réglé sur : {next_pref.upper()}")
        txt, kb = await build_main_text_and_keyboard(owner_id)
        await message.edit_text(txt, reply_markup=kb)

    elif action == "points_info":
        sub_pts = await hyoshcoder.get_points(owner_id) or 0
        bp, _, _ = await get_valid_backup_points(owner_id)
        await query.answer(
            f"💳 Points d'abonnement : {sub_pts}\n"
            f"🔋 Points de secours : {bp}/{settings.DAILY_BACKUP_POINTS}",
            show_alert=True
        )


# ──────────────────────────────────────────────────────────────────────────────
# Commandes /uset et /set_font
# ──────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.command(["uset", "settings", "myconfig"]))
async def user_settings(client: Client, message: Message):
    user_id = message.from_user.id
    handler_dict[message.chat.id] = False
    txt, kb = await build_main_text_and_keyboard(user_id)
    await message.reply_text(txt, reply_markup=kb)


@Client.on_message(filters.private & filters.command("set_font"))
async def set_font_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) > 1:
        chosen = message.command[1].lower().replace('-', '_')
        if chosen in AVAILABLE_FONTS:
            await hyoshcoder.set_font(user_id, chosen)
            preview = FONT_PREVIEWS.get(chosen, chosen)
            emoji   = FONT_EMOJIS.get(chosen, '▪️')
            await message.reply_text(f"✅ Police enregistrée avec succès !\n\n{emoji} `{chosen}` → {preview}")
            return

    # Si aucun argument ou police invalide → afficher le clavier interactive
    font = await hyoshcoder.get_font(user_id)
    font_info = f"{FONT_EMOJIS.get(font,'▪️')} `{font}` → {FONT_PREVIEWS.get(font, font)}" if font else "☑️ Aucune police définie"
    kb = await build_font_keyboard(user_id)
    await message.reply_text(
        f"🎨 **Choisissez votre police de renommage**\n\n{font_info}\n\nCliquez sur un style pour l'appliquer.",
        reply_markup=kb
    )
