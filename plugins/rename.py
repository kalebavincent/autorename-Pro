from io import BytesIO
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import (
    InputMediaDocument,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from PIL import Image
from datetime import datetime
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from helpers.utils import (
    fix_thumb,
    get_filename,
    progress_for_pyrogram,
    humanbytes,
    convert,
    extract_episode,
    extract_quality,
    extract_season,
    get_media_duration,
    determine_file_extension,
    take_screen_shot,
    verify_actual_file_type,
)
from database.data import hyoshcoder
from config import settings
import os
import time
import re
import subprocess
import asyncio
from hachoir.metadata import extractMetadata
import uuid

# Variables globales pour gérer les opérations
renaming_operations = {}
secantial_operations = {}
user_semaphores = {}
user_queue_messages = {}


async def get_user_semaphore(user_id):
    if user_id not in user_semaphores:
        user_semaphores[user_id] = asyncio.Semaphore(3)
    return user_semaphores[user_id]


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message):
    user_id = message.from_user.id
    ph_path = None
    user_data = await hyoshcoder.read_user(user_id)
    if not user_data:
        return await message.reply_text(
            "❌ ɪᴍᴘᴏssɪʙʟᴇ ᴅᴇ ᴄʜᴀʀɢᴇʀ ᴠᴏs ɪɴꜰᴏʀᴍᴀᴛɪᴏɴs. ᴠᴇᴜɪʟʟᴇᴢ ᴠᴏᴜs ɪɴsᴄʀɪʀᴇ /start."
        )

    user_points = user_data.get("points", 0)
    format_template = user_data.get("format_template", "")
    media_preference = user_data.get("media_type", "")
    sequential_mode = user_data.get("sequential_mode", False)
    src_info = await hyoshcoder.get_src_info(user_id)

    if user_points < 1:
        return await message.reply_text(
            "❌ ᴠᴏᴜs ɴ'ᴀᴠᴇᴢ ᴘᴀs ᴀssᴇᴢ ᴅᴇ ᴘᴏɪɴᴛs ᴘᴏᴜʀ ʀᴇɴᴏᴍᴍᴇʀ ᴜɴ ꜰɪᴄʜɪᴇʀ. ʀᴇᴄʜᴀʀɢᴇᴢ ᴠᴏs ᴘᴏɪɴᴛs.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Free points", callback_data="free_points")]]
            ),
        )

    if not format_template:
        return await message.reply_text(
            "ᴠᴇᴜɪʟʟᴇᴢ ᴅ'ᴀʙᴏʀᴅ ᴅᴇ́ғɪɴɪʀ ᴜɴ ғᴏʀᴍᴀᴛ ᴅᴇ ʀᴇɴᴏᴍᴍᴀɢᴇ ᴀᴜᴛᴏᴍᴀᴛɪǫᴜᴇ ᴇɴ ᴜᴛɪʟɪsᴀɴᴛ /autorename"
        )

    if message.document:
        file_id = message.document.file_id
        original_name = message.document.file_name or get_filename(
            extension="",  
            prefix="doc",
            use_timestamp=True
        )
        mime_type = message.document.mime_type
        ext =  determine_file_extension(mime_type, original_name)
        file_name = f"{os.path.splitext(original_name)[0]}{ext}"
        media_type = media_preference if media_preference else "document"

    elif message.video:
        file_id = message.video.file_id
        original_name = message.video.file_name or get_filename(
            extension="",  
            prefix="vid",
            use_timestamp=True
        )
        mime_type = message.video.mime_type or "video/mp4"
        ext =  determine_file_extension(mime_type, original_name)
        file_name = f"{os.path.splitext(original_name)[0]}{ext}"
        media_type = media_preference if media_preference else "video"

    elif message.audio:
        file_id = message.audio.file_id
        original_name = message.audio.file_name or get_filename(
            extension="",  
            prefix="aud",
            use_timestamp=True
        )
        mime_type = message.audio.mime_type or "audio/mpeg"
        ext =  determine_file_extension(mime_type, original_name)
        file_name = f"{os.path.splitext(original_name)[0]}{ext}"
        media_type = media_preference if media_preference else "audio"

    else:
        return await message.reply_text("Unsupported file type")

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
        if caption:
            episode_number = await extract_episode(caption)
            saison = await extract_season(caption)
            extracted_qualities = await extract_quality(caption)
        else:
            episode_number = await extract_episode(file_name)
            saison = await extract_season(file_name)
            extracted_qualities = await extract_quality(file_name)
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
            await user_queue_messages[user_id][0].edit_text(
                f"🔄 **ᴛʀᴀɪᴛᴇᴍᴇɴᴛ ᴅᴜ ғɪᴄʜɪᴇʀ :**\n➲ **ғɪʟᴇɴᴀᴍᴇ :** `{file_name}`"
            )
            user_queue_messages[user_id].pop(0)

        if user_id not in secantial_operations:
            secantial_operations[user_id] = {"files": [], "expected_count": 0}

        secantial_operations[user_id]["expected_count"] += 1

        if episode_number or saison:
            placeholders = [
                "episode",
                "épisode",
                "Episode",
                "EPISODE",
                "{episode}",
                "saison",
                "Saison",
                "SAISON",
                "{saison}",
            ]
            for placeholder in placeholders:
                if placeholder.lower() in ["episode", "{episode}"] and episode_number:
                    format_template = format_template.replace(
                        placeholder, str(episode_number), 1
                    )
                elif placeholder.lower() in ["saison", "{saison}"] and saison:
                    format_template = format_template.replace(
                        placeholder, str(saison), 1
                    )

            quality_placeholders = ["quality", "Quality", "QUALITY", "{quality}"]
            for quality_placeholder in quality_placeholders:
                if quality_placeholder in format_template:
                    if extracted_qualities == "Unknown":
                        await queue_message.edit_text(
                            "**ᴊᴇ ɴ'ᴀɪ ᴘᴀs ᴘᴜ ᴇxᴛʀᴀɪʀᴇ ʟᴀ ǫᴜᴀʟɪᴛᴇ́ ᴄᴏʀʀᴇᴄᴛᴇᴍᴇɴᴛ. ʀᴇɴᴏᴍᴍᴀɢᴇ ᴇɴ 'Unknown'...**"
                        )
                        del renaming_operations[file_id]
                        secantial_operations[user_id]["expected_count"] -= 1
                        return

                    format_template = format_template.replace(
                        quality_placeholder, "".join(extracted_qualities)
                    )

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
                progress_args=(
                    "ᴛᴇʟᴇ́ᴄʜᴀʀɢᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs...",
                    queue_message,
                    time.time(),
                ),
            )
        except Exception as e:
            del renaming_operations[file_id]
            secantial_operations[user_id]["expected_count"] -= 1
            return await queue_message.edit_text(f"**ᴇʀʀᴇᴜʀ ᴅᴇ ᴛᴇʟᴇ́ᴄʜᴀʀɢᴇᴍᴇɴᴛ:** {e}")

        await queue_message.edit_text(
            f"🔄 **ʀᴇɴᴏᴍᴍᴀɢᴇ ᴇᴛ ᴀᴊᴏᴜᴛ ᴅᴇ ᴍᴇ́ᴛᴀᴅᴏɴɴᴇ́ᴇs ᴇɴ ᴄᴏᴜʀs :** `{file_name}`"
        )

        try:
            real_mime, real_ext = verify_actual_file_type(path)
            if not real_mime:
                real_mime = "video/mp4"
            file_ext =  determine_file_extension(real_mime, renamed_file_path)

            current_ext = os.path.splitext(renamed_file_path)[1]
            if file_ext.lower() != current_ext.lower():
                corrected_path = f"{os.path.splitext(renamed_file_path)[0]}{file_ext}"
                os.rename(path, corrected_path)
                path = corrected_path
                renamed_file_path = corrected_path
                metadata_file_path = f"Metadata/{os.path.basename(corrected_path)}"
                renamed_file_name = os.path.basename(corrected_path) 
                await queue_message.edit_text(f"✅ Extension corrigée : {file_ext}")

            os.rename(path, renamed_file_path)
            path = renamed_file_path

            metadata_added = False
            _bool_metadata = await hyoshcoder.get_metadata(user_id)
            if _bool_metadata:
                metadata = await hyoshcoder.get_metadata_code(user_id)
                if metadata:
                    if real_mime.startswith(("video/", "audio/")):
                        cmd = (
                            f'ffmpeg -i "{renamed_file_path}" -map 0 -c copy '
                            f'-metadata title="{metadata}" '
                            f'-metadata author="{metadata}" '
                            f'-metadata:s:s title="{metadata}" '
                            f'-metadata:s:a title="{metadata}" '
                            f'-metadata:s:v title="{metadata}" '
                            f'"{metadata_file_path}"'
                        )
                    else:
                        cmd = None
                        metadata_added = True
                        await queue_message.edit_text(
                            "ℹ️ Les métadonnées étendues ne sont applicables qu'aux fichiers audio/vidéo"
                        )

                    if cmd:
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

                                if (
                                    not os.path.exists(metadata_file_path)
                                    or os.path.getsize(metadata_file_path) == 0
                                ):
                                    raise Exception("Le fichier de sortie est vide")

                            else:
                                error_message = stderr.decode()
                                if "Invalid data found" in error_message:
                                    await queue_message.edit_text(
                                        "❌ Format de fichier incompatible avec les métadonnées"
                                    )
                                else:
                                    await queue_message.edit_text(
                                        f"❌ Erreur FFmpeg: {error_message[:500]}..."
                                    )

                        except asyncio.TimeoutError:
                            await queue_message.edit_text(
                                "⌛ Timeout lors de l'ajout des métadonnées"
                            )
                            metadata_added = True
                        except Exception as e:
                            await queue_message.edit_text(f"⚠️ Exception: {str(e)}")
                            metadata_added = True
            else:
                metadata_added = True

            if not metadata_added:
                await queue_message.edit_text(
                    "⚠️ Échec de l'ajout des métadonnées. Envoi du fichier original."
                )
                path = renamed_file_path

            await queue_message.edit_text(
                f"📤 **ᴛᴇ́ʟᴇ́ᴠᴇʀsᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs :** `{file_name}`"
            )
            await asyncio.sleep(5)
            # ph_path = None
            c_caption = await hyoshcoder.get_caption(message.chat.id)
            c_thumb = await hyoshcoder.get_thumbnail(message.chat.id)

            if message.document:
                file_size = humanbytes(message.document.file_size)
                duration = convert(0)
            elif message.video:
                file_size = humanbytes(message.video.file_size)
                duration = convert(message.video.duration or 0)
            else:
                await queue_message.edit_text(
                    "Le message ne contient pas de document ou de vidéo pris en charge."
                )
                del renaming_operations[file_id]
                secantial_operations[user_id]["expected_count"] -= 1
                return

            if c_caption:
                formatted_caption = c_caption.format(
                    filename=f"**{renamed_file_name}**", 
                    filesize=f"**{file_size}**",         
                    duration=f"**{duration}**"          
                )
                if not formatted_caption.startswith("**"):
                    formatted_caption = f"**{formatted_caption}**"
                caption = formatted_caption
            else:
                caption = f"**{renamed_file_name}**"

            # Gestion des thumbnails
            ph_path = None
            try:
                if c_thumb:
                    ph_path = await client.download_media(c_thumb)
                elif media_type == "video":
                    if hasattr(message, 'video') and message.video:
                        if hasattr(message.video, 'thumbs') and message.video.thumbs:
                            ph_path = await client.download_media(message.video.thumbs[0].file_id)
                        else:
                            try:
                                video_duration = get_media_duration(path)
                                screenshot_time = min(30, int(video_duration) // 2) if video_duration else 10
                                ph_path = await take_screen_shot(path, "downloads/", screenshot_time)
                                if ph_path:
                                    width, height, ph_path = await fix_thumb(ph_path)
                            except Exception as e:
                                print(f"Erreur lors de la génération de la miniature: {e}")
                                ph_path = None
            except Exception as e:
                print(f"Erreur lors du traitement de la miniature: {e}")
                ph_path = None

            try:
                if ph_path:
                    with open(ph_path, 'rb') as f:
                        img_data = f.read()
                    
                    img = Image.open(BytesIO(img_data))
                    img = img.convert("RGB")
                    img = img.resize((320, 320))
                    
                    img.save(ph_path, "JPEG", quality=85)
            except Exception as e:
                print(f"Erreur de ré-encodage: {e}")
                ph_path = None

            metadata = extractMetadata(createParser(path))
            if metadata and metadata.has("duration"):
                duration = metadata.get("duration").seconds

            width, height = 320, 180  # Valeurs par défaut

            if metadata is not None:
                if metadata.has("duration"):
                    duration = metadata.get("duration").seconds

                has_width = metadata.has("width")
                has_height = metadata.has("height")

                if has_width and has_height:
                    original_width = metadata.get("width")
                    original_height = metadata.get("height")

                    if original_width is not None and original_height is not None:
                        if original_width / original_height != 16 / 9:
                            height = 180
                            width = int(height * 16 / 9)
                        else:
                            width = original_width
                            height = original_height

            try:
                if sequential_mode:
                    if media_type == "document":
                        log_message = await client.send_document(
                            settings.DUMP_CHANNEL,
                            document=path,
                            thumb=ph_path,
                            caption=caption,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                "ᴛᴇ́ʟᴇᴠᴇʀsᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs...",
                                queue_message,
                                time.time(),
                            ),
                        )
                    elif media_type == "video":
                        log_message = await client.send_video(
                            settings.DUMP_CHANNEL,
                            video=path,
                            caption=caption,
                            thumb=ph_path,
                            width=width,
                            height=height,
                            duration=int(get_media_duration(path)),
                            progress=progress_for_pyrogram,
                            progress_args=(
                                "ᴛᴇ́ʟᴇᴠᴇʀsᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs...",
                                queue_message,
                                time.time(),
                            ),
                        )
                    elif media_type == "audio":
                        log_message = await client.send_audio(
                            settings.DUMP_CHANNEL,
                            audio=path,
                            caption=caption,
                            thumb=ph_path,
                            duration=int(get_media_duration(path)),
                            progress=progress_for_pyrogram,
                            progress_args=(
                                "ᴛᴇ́ʟᴇᴠᴇʀsᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs...",
                                queue_message,
                                time.time(),
                            ),
                        )
                    else:
                        await queue_message.reply_text(
                            "❌ **ᴛʏᴘᴇ ᴅᴇ ᴍᴇ́ᴅɪᴀ ɴᴏɴ ᴘʀɪs ᴇɴ ᴄʜᴀʀɢᴇ.**"
                        )
                        secantial_operations[user_id]["expected_count"] -= 1
                        return

                    secantial_operations[user_id]["files"].append(
                        {
                            "message_id": log_message.id,
                            "file_name": renamed_file_name,
                            "season": saison,
                            "episode": episode_number,
                        }
                    )

                    if (
                        len(secantial_operations[user_id]["files"])
                        == secantial_operations[user_id]["expected_count"]
                    ):
                        sorted_files = sorted(
                            secantial_operations[user_id]["files"],
                            key=lambda x: (
                                int(x["season"]) if x["season"] is not None else 0,
                                int(x["episode"]) if x["episode"] is not None else 0,
                            ),
                        )

                        user_channel = await hyoshcoder.get_user_channel(user_id)
                        if not user_channel:
                            user_channel = user_id

                        try:
                            await client.get_chat(user_channel)
                            for file_info in sorted_files:
                                await asyncio.sleep(3)
                                await client.copy_message(
                                    user_channel,
                                    settings.DUMP_CHANNEL,
                                    file_info["message_id"],
                                )
                            await queue_message.reply_text(
                                f"✅ **ᴛᴏᴜs ʟᴇs ғɪᴄʜɪᴇʀs ᴏɴᴛ ᴇ́ᴛᴇ́ ᴇɴᴠᴏʏᴇ́s ᴅᴀɴs ʟᴇ ᴄᴀɴᴀʟ :** {user_channel}\n"
                                "sɪ ᴅᴇs ғɪᴄʜɪᴇʀs ɴ'ᴏɴᴛ ᴘᴀs ᴇ́ᴛᴇ́ ᴄᴏᴍᴘʟᴇ̀ᴛᴇᴍᴇɴᴛ ᴇɴᴠᴏʏᴇ́s, ᴄᴇ ᴘʀᴏʙʟᴇ̀ᴍᴇ ᴇsᴛ ᴅᴜ̂ ᴀᴜ ғʟᴏᴏᴅ ᴅᴇ ʀᴇǫᴜᴇ̂ᴛᴇs ᴘᴀʀ ᴛᴇʟᴇɢʀᴀᴍ.\n"
                                "ᴠᴇᴜɪʟʟᴇᴢ ᴍ'ᴇɴᴠᴏʏᴇʀ ɪɴᴅɪᴠɪᴅᴜᴇʟʟᴇᴍᴇɴᴛ ᴄᴇs ғɪᴄʜɪᴇʀs."
                            )
                        except Exception as e:
                            await queue_message.reply_text(
                                f"❌ **ᴇʀʀᴇᴜʀ : ʟᴇ ᴄᴀɴᴀʟ {user_channel} ɴ'ᴇsᴛ ᴘᴀs ᴀᴄᴄᴇssɪʙʟᴇ.**\n"
                                "sɪ ʟᴇ ᴘʀᴏʙʟᴇ̀ᴍᴇ ᴘᴇʀsɪsᴛᴇ, ᴠᴇᴜɪʟʟᴇᴢ :\n"
                                "1. ʀᴇᴛɪʀᴇʀ ʟᴇ ʙᴏᴛ ᴅᴇ ᴠᴏᴛʀᴇ ᴄᴀɴᴀʟ.\n"
                                "2. ʀᴇɴᴏᴍᴍᴇʀ ʟᴇ ʙᴏᴛ ᴀᴅᴍɪɴɪsᴛʀᴀᴛᴇᴜʀ ᴅᴜ ᴄᴀɴᴀʟ.\n"
                                f"ᴇʀʀᴇᴜʀ ᴅᴇ́ᴛᴀɪʟʟᴇ́ᴇ : {e}"
                            )
                            for file_info in sorted_files:
                                await asyncio.sleep(3)
                                await client.copy_message(
                                    user_id,
                                    settings.DUMP_CHANNEL,
                                    file_info["message_id"],
                                )
                            await queue_message.reply_text(
                                "✅ **ᴛᴏᴜs ʟᴇs ғɪᴄʜɪᴇʀs ᴏɴᴛ ᴇ́ᴛᴇ́ ᴇɴᴠᴏʏᴇ́s ᴀ̀ ᴠᴏᴛʀᴇ ɪᴅ ᴜᴛɪʟɪsᴀᴛᴇᴜʀ.**"
                            )

                        del secantial_operations[user_id]
                else:
                    if media_type == "document":
                        await client.send_document(
                            message.chat.id,
                            document=path,
                            thumb=ph_path,
                            caption=caption,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                "ᴛᴇ́ʟᴇᴠᴇʀsᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs...",
                                queue_message,
                                time.time(),
                            ),
                        )
                    elif media_type == "video":
                        await client.send_video(
                            message.chat.id,
                            video=path,
                            caption=caption,
                            thumb=ph_path,
                            width=width,
                            height=height,
                            duration=int(get_media_duration(path)),
                            progress=progress_for_pyrogram,
                            progress_args=(
                                "ᴛᴇ́ʟᴇᴠᴇʀsᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs...",
                                queue_message,
                                time.time(),
                            ),
                        )
                    elif media_type == "audio":
                        await client.send_audio(
                            message.chat.id,
                            audio=path,
                            caption=caption,
                            thumb=ph_path,
                            duration=int(get_media_duration(path)),
                            progress=progress_for_pyrogram,
                            progress_args=(
                                "ᴛᴇ́ʟᴇᴠᴇʀsᴇᴍᴇɴᴛ ᴇɴ ᴄᴏᴜʀs...",
                                queue_message,
                                time.time(),
                            ),
                        )
            except Exception as e:
                os.remove(renamed_file_path)
                if ph_path:
                    os.remove(ph_path)
                    del renaming_operations[file_id]
                    secantial_operations[user_id]["expected_count"] -= 1
                return await queue_message.edit_text(f"❌ **Erreur :** {e}")

            os.remove(renamed_file_path)
            if ph_path:
                os.remove(ph_path)

            await queue_message.delete()

        finally:
            await hyoshcoder.degrade_points(user_id, 1)
            if os.path.exists(renamed_file_path):
                os.remove(renamed_file_path)
            if os.path.exists(metadata_file_path):
                os.remove(metadata_file_path)
            if ph_path and os.path.exists(ph_path):
                os.remove(ph_path)
            if file_id in renaming_operations:
                del renaming_operations[file_id]
    finally:
        user_semaphore.release()
