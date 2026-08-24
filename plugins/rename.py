from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InputMediaDocument, Message, InlineKeyboardButton, InlineKeyboardMarkup
from helpers.utils import take_screen_shot
from PIL import Image
from datetime import datetime
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from helpers.utils import progress_for_pyrogram, humanbytes, convert, extract_episode, extract_quality, extract_season
from database.data import hyoshcoder
from config import settings
import os
import time
import re
import subprocess
import asyncio
import uuid

from shutil import rmtree
from datetime import datetime, timedelta

# Variables globales pour gérer les opérations
renaming_operations = {}
secantial_operations = {}
user_semaphores = {}
user_queue_messages = {}
last_refresh = {}

async def get_user_semaphore(user_id):
    if user_id not in user_semaphores:
        user_semaphores[user_id] = asyncio.Semaphore(3)
    return user_semaphores[user_id]

@Client.on_message(filters.private & filters.command(["cleanup", "cancel", "reset_queue", "clear", "refresh"]))
async def refresh_user_data(client, message):
    if not message.from_user:
        return
    user_id = message.from_user.id
    
    # Vérification du cooldown (1 heure)
    if user_id in last_refresh:
        elapsed = datetime.now() - last_refresh[user_id]
        if elapsed < timedelta(hours=1):
            remaining = timedelta(hours=1) - elapsed
            return await message.reply_text(
                f"⏳ Veuillez attendre {remaining.seconds//3600}h {(remaining.seconds%3600)//60}min "
                "avant de pouvoir utiliser cette commande à nouveau."
            )
    
    deleted = {'files': 0, 'dirs': 0}
    for base_dir in ['downloads', 'Metadata', 'thumbnails']:
        user_dir = os.path.join(base_dir, str(user_id))
        if os.path.exists(user_dir):
            try:
                rmtree(user_dir)
                deleted['dirs'] += 1
            except Exception as e:
                print(f"Erreur suppression {user_dir}: {e}")

    for file_id in list(renaming_operations.keys()):
        if isinstance(file_id, tuple) and file_id[0] == user_id:
            del renaming_operations[file_id]
        elif isinstance(file_id, str) and str(user_id) in file_id:
            del renaming_operations[file_id]

    secantial_operations.pop(user_id, None)
    user_semaphores.pop(user_id, None)
    
    if user_id in user_queue_messages:
        for msg in user_queue_messages[user_id]:
            try:
                await msg.delete()
            except Exception as e:
                print(f"Erreur suppression message: {e}")
        del user_queue_messages[user_id]

    last_refresh[user_id] = datetime.now()

    report_msg = (
        f"♻️ **Réinitialisation complète effectuée**\n\n"
        f"• {deleted['dirs']} dossiers utilisateur nettoyés\n"
        f"• Variables opérationnelles réinitialisées\n\n"
        f"⏳ Prochain refresh possible dans 1h"
    )
    
    await message.reply_text(report_msg)

@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message):
    if not message.from_user:
        return
    user_id = message.from_user.id

    user_data = await hyoshcoder.read_user(user_id)
    if not user_data:
        return await message.reply_text("❌ ɪᴍᴘᴏssɪʙʟᴇ ᴅᴇ ᴄʜᴀʀɢᴇʀ ᴠᴏs ɪɴꜰᴏʀᴍᴀᴛɪᴏɴs. ᴠᴇᴜɪʟʟᴇᴢ ᴠᴏᴜs ɪɴsᴄʀɪʀᴇ /start.")

    user_points = user_data.get("points", 0)
    from plugins.backup_points import get_valid_backup_points
    backup_pts, _, _ = await get_valid_backup_points(user_id)
    total_points = user_points + backup_pts

    format_template  = user_data.get("format_template", "")
    media_preference = (user_data.get("media_preference") or "").lower().strip()
    sequential_mode  = user_data.get("sequential_mode", False)
    src_info         = await hyoshcoder.get_src_info(user_id)

    if total_points < 1:
        return await message.reply_text("❌ ᴠᴏᴜs ɴ'ᴀᴠᴇᴢ ᴘᴀs ᴀssᴇᴢ ᴅᴇ ᴘᴏɪɴᴛs ᴘᴏᴜʀ ʀᴇɴᴏᴍᴍᴇʀ ᴜɴ ꜰɪᴄʜɪᴇʀ. ʀᴇᴄʜᴀʀɢᴇᴢ ᴠᴏs ᴘᴏɪɴᴛs.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Free points", callback_data="free_points")]]))

    if not format_template:
        return await message.reply_text(
            "ᴠᴇᴜɪʟʟᴇᴢ ᴅ'ᴀʙᴏʀᴅ ᴅᴇ́ғɪɴɪʀ ᴜɴ ғᴏʀᴍᴀᴛ ᴅᴇ ʀᴇɴᴏᴍᴍᴀɢᴇ ᴀᴜᴛᴏᴍᴀᴛɪǫᴜᴇ ᴇɴ ᴜᴛɪʟɪsᴀɴᴛ /autorename"
        )

    if message.document:
        file_id   = message.document.file_id
        file_name = message.document.file_name or "file.mkv"
    elif message.video:
        file_id   = message.video.file_id
        file_name = getattr(message.video, "file_name", None) or f"video_{message.video.file_unique_id[:6]}.mp4"
        if not os.path.splitext(file_name)[1]:
            file_name += ".mp4"
    elif message.audio:
        file_id   = message.audio.file_id
        file_name = getattr(message.audio, "file_name", None) or f"audio_{message.audio.file_unique_id[:6]}.mp3"
        if not os.path.splitext(file_name)[1]:
            file_name += ".mp3"
    else:
        return await message.reply_text("ᴜɴsᴜᴘᴘᴏʀᴛᴇᴅ ꜰɪʟᴇ ᴛʏᴘᴇ")

    # Type de média final pour l'envoi : préférence utilisateur explicite > type de message d'origine
    if media_preference in ("document", "video", "audio"):
        media_type = media_preference
    else:
        if message.video:
            media_type = "video"
        elif message.audio:
            media_type = "audio"
        else:
            media_type = "document"

    if file_id in renaming_operations:
        elapsed_time = (datetime.now() - renaming_operations[file_id]).seconds
        if elapsed_time < 10:
            return

    renaming_operations[file_id] = datetime.now()

    if src_info == "file_name":
        episode_number = await extract_episode(file_name)
        saison = await extract_season(file_name)
        extracted_qualities = await extract_quality(file_name)
    elif src_info == "caption":
        caption = message.caption if message.caption else ""
        episode_number = await extract_episode(caption)
        saison = await extract_season(caption)
        extracted_qualities = await extract_quality(caption)
    else:
        episode_number = await extract_episode(file_name)
        saison = await extract_season(file_name)
        extracted_qualities = await extract_quality(file_name)

    assurance_message = (
        "**ꜰɪᴄʜɪᴇʀ ᴀᴊᴏᴜᴛᴇ́ ᴀ̀ ʟᴀ ꜰɪʟᴇ ᴅ'ᴀᴛᴛᴇɴᴛᴇ ✅**\n"
        f"➲ **ɴᴏᴍ :** `{file_name}`\n"
        f"➲ **sᴀɪsᴏɴ :** `{saison if saison else 'N/A'}`\n"
        f"➲ **ᴇᴘɪsᴏᴅᴇ :** `{episode_number if episode_number else 'N/A'}`\n"
        f"➲ **ǫᴜᴀʟɪᴛᴇ́ :** `{extracted_qualities if extracted_qualities else 'N/A'}`"

    )

    queue_message = await message.reply_text(assurance_message)

    if user_id not in user_queue_messages:
        user_queue_messages[user_id] = []
    user_queue_messages[user_id].append(queue_message)

    user_semaphore = await get_user_semaphore(user_id)
    await user_semaphore.acquire()

    try:
        if user_id in user_queue_messages and user_queue_messages[user_id]:
            await user_queue_messages[user_id][0].edit_text(f"🔄 **ᴛʀᴀɪᴛᴇᴍᴇɴᴛ ᴅᴜ ғɪᴄʜɪᴇʀ :**\n➲ **ғɪʟᴇɴᴀᴍᴇ :** `{file_name}`")
            user_queue_messages[user_id].pop(0)
            
        if user_id not in secantial_operations:
            secantial_operations[user_id] = {"files": [], "expected_count": 0}

        secantial_operations[user_id]["expected_count"] += 1

        if episode_number or saison:
            placeholders = [
                "episode", "Episode", "EPISODE", "{episode}",
                "saison", "Saison", "SAISON", "{saison}"
            ]
            for placeholder in placeholders:
                if placeholder.lower() in ["episode", "{episode}"] and episode_number:
                    format_template = format_template.replace(placeholder, str(episode_number), 1)
                elif placeholder.lower() in ["saison", "{saison}"] and saison:
                    format_template = format_template.replace(placeholder, str(saison), 1)

            quality_placeholders = ["quality", "Quality", "QUALITY", "{quality}"]
            for quality_placeholder in quality_placeholders:
                if quality_placeholder in format_template:
                    if extracted_qualities == "Unknown":
                        await queue_message.edit_text("**ᴊᴇ ɴ'ᴀɪ ᴘᴀs ᴘᴜ ᴇxᴛʀᴀɪʀᴇ ʟᴀ ǫᴜᴀʟɪᴛᴇ́ ᴄᴏʀʀᴇᴄᴛᴇᴍᴇɴᴛ. ʀᴇɴᴏᴍᴍᴀɢᴇ ᴇɴ 'Unknown'...**")
                        del renaming_operations[file_id]
                        return

                    format_template = format_template.replace(quality_placeholder, "".join(extracted_qualities))

        _, file_extension = os.path.splitext(file_name)
        renamed_file_name = f"{format_template}{file_extension}"
        renamed_file_path = f"downloads/{renamed_file_name}"
        metadata_file_path = f"Metadata/{renamed_file_name}"
        os.makedirs(os.path.dirname(renamed_file_path), exist_ok=True)
        os.makedirs(os.path.dirname(metadata_file_path), exist_ok=True)

        file_uuid = str(uuid.uuid4())[:8]
        renamed_file_path_with_uuid = f"{renamed_file_path}_{file_uuid}"

        await queue_message.edit_text(f"📥 **ᴛᴇ́ʟᴇ́ᴄʜᴀʀɢᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs :** `{file_name}`")

        try:
            path = await client.download_media(
                message,
                file_name=renamed_file_path_with_uuid,
                progress=progress_for_pyrogram,
                progress_args=("ᴛᴇ́ʟᴇ́ᴄʜᴀʀɢᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs...", queue_message, time.time()),
            )
        except Exception as e:
            del renaming_operations[file_id]
            return await queue_message.edit_text(f"**ᴇʀʀᴇᴜʀ ᴅᴇ ᴛᴇʟᴇ́ᴄʜᴀʀɢᴇᴍᴇɴᴛ:** {e}")

        await queue_message.edit_text(f"🔄 **ʀᴇɴᴏᴍᴍᴀɢᴇ ᴇᴛ ᴀᴊᴏᴜᴛ ᴅᴇ ᴍᴇ́ᴛᴀᴅᴏɴɴᴇ́ᴇs ᴇɴ ᴄᴏᴜʀs :** `{file_name}`")

        try:
            os.rename(path, renamed_file_path)
            path = renamed_file_path

            metadata_added = False
            _bool_metadata = await hyoshcoder.get_metadata(user_id)
            if _bool_metadata:
                metadata = await hyoshcoder.get_metadata_code(user_id)
                if metadata:
                    cmd = f'ffmpeg -i "{renamed_file_path}"  -map 0 -c:s copy -c:a copy -c:v copy -metadata title="{metadata}" -metadata author="{metadata}" -metadata:s:s title="{metadata}" -metadata:s:a title="{metadata}" -metadata:s:v title="{metadata}"  "{metadata_file_path}"'
                    try:
                        process = await asyncio.create_subprocess_shell(
                            cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        stdout, stderr = await process.communicate()
                        if process.returncode == 0:
                            metadata_added = True
                            path = metadata_file_path
                        else:
                            error_message = stderr.decode()
                            await queue_message.edit_text(f"**ᴇʀʀᴇᴜʀ ᴅᴇ ᴍᴇ́ᴛᴀᴅᴏɴɴᴇ́ᴇs:**\n{error_message}")
                    except asyncio.TimeoutError:
                        await queue_message.edit_text("**ᴄᴏᴍᴍᴀɴᴅᴇ ғғᴍᴘᴇɢ ᴇxᴘɪʀᴇ́ᴇ.**")
                        return
                    except Exception as e:
                        await queue_message.edit_text(f"**ᴜɴᴇ ᴇxᴄᴇᴘᴛɪᴏɴ s'ᴇsᴛ ᴘʀᴏᴅᴜɪᴛᴇ:**\n{str(e)}")
                        return
            else:
                metadata_added = True

            if not metadata_added:
                await queue_message.edit_text(
                    "L'ᴀᴊᴏᴜᴛ ᴅᴇs mᴇ́ᴛᴀᴅᴏɴɴᴇᴇs ᴀ ᴇ́ᴄʜᴏᴜᴇ́. ᴛᴇ́ʟᴇᴠᴇʀsᴇᴍᴇɴᴛ ᴅᴜ ғɪᴄʜɪᴇʀ ʀᴇɴᴏᴍᴍᴇ́."
                )
                path = renamed_file_path

            await queue_message.edit_text(f"📤 **ᴛᴇ́ʟᴇ́ᴠᴇʀsᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs :** `{file_name}`")
            await asyncio.sleep(5)
            ph_path = None
            c_caption = await hyoshcoder.get_caption(message.chat.id)
            c_thumb = await hyoshcoder.get_thumbnail(message.chat.id)

            # ── Métadonnées réelles via ffprobe ───────────────────────────
            vid_width = 0
            vid_height = 0
            vid_duration = 0
            try:
                import json as _json, shutil as _shutil
                _ffprobe = _shutil.which("ffprobe") or "ffprobe"
                _probe_proc = await asyncio.create_subprocess_exec(
                    _ffprobe, "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height:format=duration",
                    "-of", "json", path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                _probe_out, _ = await _probe_proc.communicate()
                if _probe_out:
                    _probe = _json.loads(_probe_out)
                    _st = (_probe.get("streams") or [{}])[0]
                    vid_width = int(_st.get("width") or 0)
                    vid_height = int(_st.get("height") or 0)
                    vid_duration = int(float((_probe.get("format") or {}).get("duration") or 0))
            except Exception as _probe_err:
                print(f"ffprobe error: {_probe_err}")
            # ─────────────────────────────────────────────────────────────

            if message.document:
                file_size = humanbytes(message.document.file_size)
                duration = convert(vid_duration)
            elif message.video:
                file_size = humanbytes(message.video.file_size)
                duration = convert(vid_duration or message.video.duration or 0)
            else:
                await queue_message.edit_text("Le message ne contient pas de document ou de vidéo pris en charge.")
                return

            caption = (
                c_caption.format(
                    filename=renamed_file_name,
                    filesize=file_size,
                    duration=duration,
                )
                if c_caption
                else f"**{renamed_file_name}**"
            )

            # ── Thumbnail : custom > interne > auto-capture à 40% ────────
            if c_thumb:
                ph_path = await client.download_media(c_thumb)
            elif media_type == "video" and message.video and getattr(message.video, "thumbs", None):
                ph_path = await client.download_media(message.video.thumbs[0].file_id)
            elif media_type == "video" and vid_duration > 0:
                thumb_dir = f"thumbnails/{user_id}"
                os.makedirs(thumb_dir, exist_ok=True)
                seek = max(1.0, vid_duration * 0.40)
                ph_path = await take_screen_shot(path, thumb_dir, seek)

            if ph_path and os.path.exists(ph_path):
                try:
                    img = Image.open(ph_path).convert("RGB")
                    w, h = img.size
                    new_h = 320
                    new_w = int((new_h / h) * w) if h else 320
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    img.save(ph_path, "JPEG", quality=90)
                except Exception:
                    ph_path = None

            try:
                async def _send_media(target_chat_id, is_log=False):
                    video_cover = user_data.get("video_cover", False)
                    if media_type == "video" and video_cover and not is_log and ph_path and os.path.exists(ph_path):
                        try:
                            await client.send_photo(
                                target_chat_id,
                                photo=ph_path,
                                caption=f"🖼 **Cover** — `{renamed_file_name}`",
                            )
                        except Exception as _cover_err:
                            print(f"video_cover send failed: {_cover_err}")

                    if media_type == "video":
                        return await client.send_video(
                            target_chat_id,
                            video=path,
                            caption=caption,
                            thumb=ph_path,
                            duration=vid_duration,
                            width=vid_width,
                            height=vid_height,
                            supports_streaming=True,
                            progress=progress_for_pyrogram,
                            progress_args=("ᴛéʟᴇᴠᴇʀsᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs...", queue_message, time.time()),
                        )
                    elif media_type == "audio":
                        return await client.send_audio(
                            target_chat_id,
                            audio=path,
                            caption=caption,
                            thumb=ph_path,
                            duration=vid_duration,
                            progress=progress_for_pyrogram,
                            progress_args=("ᴛᴇ́ʟᴇᴠᴇʀsᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs...", queue_message, time.time()),
                        )
                    else:
                        return await client.send_document(
                            target_chat_id,
                            document=path,
                            thumb=ph_path,
                            caption=caption,
                            progress=progress_for_pyrogram,
                            progress_args=("ᴛᴇ́ʟᴇᴠᴇʀsᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs...", queue_message, time.time()),
                        )

                if sequential_mode:
                    log_message = await _send_media(settings.LOG_CHANNEL, is_log=True)
                    secantial_operations[user_id]["files"].append({
                        "message_id": log_message.id,
                        "file_name": renamed_file_name,
                        "season": saison,
                        "episode": episode_number
                    })

                    if len(secantial_operations[user_id]["files"]) == secantial_operations[user_id]["expected_count"]:
                        sorted_files = sorted(
                            secantial_operations[user_id]["files"],
                            key=lambda x: (x["season"], x["episode"])
                        )

                        user_channel = await hyoshcoder.get_user_channel(user_id)
                        if not user_channel:
                            user_channel = user_id

                        try:
                            await client.get_chat(user_channel)
                            for file_info in sorted_files:
                                await asyncio.sleep(3)  # Pause pour éviter le flood
                                await client.copy_message(
                                    user_channel,
                                    settings.LOG_CHANNEL,
                                    file_info["message_id"]
                                )
                            await queue_message.reply_text(
                                f"✅ **Tous les fichiers ont été envoyés dans le canal :** `{user_channel}`\n"
                                "Si des fichiers n'ont pas été complètement envoyés, ce problème est dû au flood de requêtes par Telegram. "
                                "Veuillez m'envoyer individuellement ces fichiers."
                            )
                        except Exception as e:
                            await queue_message.reply_text(
                                f"❌ **Erreur : Le canal {user_channel} n'est pas accessible. {e}\n"
                            )
                            for file_info in sorted_files:
                                await asyncio.sleep(3)  # Pause pour éviter le flood
                                await client.copy_message(
                                    user_id,
                                    settings.LOG_CHANNEL,
                                    file_info["message_id"]
                                )
                            await queue_message.reply_text("✅ **Tous les fichiers ont été envoyés à votre ID utilisateur.**")

                        del secantial_operations[user_id]
                else:
                    await _send_media(message.chat.id, is_log=False)
            except Exception as e:
                os.remove(renamed_file_path)
                if ph_path:
                    os.remove(ph_path)
                return await queue_message.edit_text(f"❌ **Erreur :** {e}")

            os.remove(renamed_file_path)
            if ph_path:
                os.remove(ph_path)

            await queue_message.delete()

        finally:
            if user_points > 0:
                await hyoshcoder.degrade_points(user_id, 1)
            elif backup_pts > 0:
                await hyoshcoder.consume_backup_point(user_id)
            if os.path.exists(renamed_file_path):
                os.remove(renamed_file_path)
            if os.path.exists(metadata_file_path):
                os.remove(metadata_file_path)
            if ph_path and os.path.exists(ph_path):
                os.remove(ph_path)
            del renaming_operations[file_id]
    finally:
        user_semaphore.release()