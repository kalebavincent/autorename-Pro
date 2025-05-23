from shutil import rmtree
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InputMediaDocument, Message, InlineKeyboardButton, InlineKeyboardMarkup
from PIL import Image
from datetime import datetime, timedelta
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

def get_user_directories(user_id, timestamp=None):
    """Retourne les chemins des dossiers utilisateur"""
    if timestamp is None:
        timestamp = int(time.time())
    base_dirs = {
        'downloads': f"downloads/{user_id}/{timestamp}",
        'metadata': f"Metadata/{user_id}/{timestamp}",
        'thumbnails': f"thumbnails/{user_id}/{timestamp}"
    }
    return base_dirs

async def cleanup_user_files(user_id):
    """Nettoie tous les fichiers et dossiers d'un utilisateur"""
    deleted = {'files': 0, 'dirs': 0}

    for base_dir in ['downloads', 'Metadata', 'thumbnails']:
        user_dir = os.path.join(base_dir, str(user_id))
        if os.path.exists(user_dir):
            try:
                rmtree(user_dir)
                deleted['dirs'] += 1
            except Exception as e:
                print(f"Erreur suppression {user_dir}: {e}")

    for root, dirs, files in os.walk("."):
        for file in files:
            if str(user_id) in file and file.endswith(('.mp4', '.mkv', '.avi', '.mp3', '.jpg', '.jpeg')):
                try:
                    os.remove(os.path.join(root, file))
                    deleted['files'] += 1
                except Exception as e:
                    print(f"Erreur suppression fichier {file}: {e}")
    
    return deleted

@Client.on_message(filters.command("refresh") & filters.private)
async def refresh_user_data(client, message):
    user_id = message.from_user.id
    
    if user_id in last_refresh:
        elapsed = datetime.now() - last_refresh[user_id]
        if elapsed < timedelta(hours=1):
            remaining = timedelta(hours=1) - elapsed
            return await message.reply_text(
                f"⏳ Veuillez attendre {remaining.seconds//3600}h {(remaining.seconds%3600)//60}min "
                "avant de pouvoir utiliser cette commande à nouveau."
            )
    
    cleanup_result = await cleanup_user_files(user_id)

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
            except:
                pass
        del user_queue_messages[user_id]

    last_refresh[user_id] = datetime.now()
    
    report_msg = (
        f"♻️ **Réinitialisation complète effectuée**\n\n"
        f"• {cleanup_result['dirs']} dossiers utilisateur nettoyés\n"
        f"• {cleanup_result['files']} fichiers temporaires supprimés\n"
        f"• Variables opérationnelles réinitialisées\n\n"
        f"⏳ Prochain refresh possible dans 1h"
    )
    
    await message.reply_text(report_msg)

@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message):
    user_id = message.from_user.id
    timestamp = int(time.time())
    user_dirs = get_user_directories(user_id, timestamp)

    for dir_path in user_dirs.values():
        os.makedirs(dir_path, exist_ok=True)

    user_data = await hyoshcoder.read_user(user_id)
    if not user_data:
        return await message.reply_text("❌ Impossible de charger vos informations. Veuillez vous inscrire /start.")

    user_points = user_data.get("points", 0)
    format_template = user_data.get("format_template", "")
    media_preference = user_data.get("media_preference", "")
    sequential_mode = user_data.get("sequential_mode", False)
    src_info = await hyoshcoder.get_src_info(user_id)  

    if user_points < 1:
        return await message.reply_text("❌ Vous n'avez pas assez de points pour renommer un fichier.", 
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Free points", callback_data="free_points")]]))

    if not format_template:
        return await message.reply_text("Veuillez d'abord définir un format de renommage automatique en utilisant /autorename")

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        media_type = media_preference or "document"
    elif message.video:
        file_id = message.video.file_id
        file_name = f"{message.video.file_name}.mp4" if message.video.file_name else "video.mp4"
        media_type = media_preference or "video"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = f"{message.audio.file_name}.mp3" if message.audio.file_name else "audio.mp3"
        media_type = media_preference or "audio"
    else:
        return await message.reply_text("Type de fichier non supporté")

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
        "**Fichier ajouté à la file d'attente ✅**\n"
        f"➲ **Nom :** `{file_name}`\n"
        f"➲ **Saison :** `{saison if saison else 'N/A'}`\n"
        f"➲ **Épisode :** `{episode_number if episode_number else 'N/A'}`\n"
        f"➲ **Qualité :** `{extracted_qualities if extracted_qualities else 'N/A'}`"
    )

    queue_message = await message.reply_text(assurance_message)

    if user_id not in user_queue_messages:
        user_queue_messages[user_id] = []
    user_queue_messages[user_id].append(queue_message)

    user_semaphore = await get_user_semaphore(user_id)
    await user_semaphore.acquire()

    try:
        if user_queue_messages.get(user_id):
            await user_queue_messages[user_id][0].edit_text(f"🔄 **Traitement du fichier :**\n➲ **Filename :** `{file_name}`")
            user_queue_messages[user_id].pop(0)
            
        if user_id not in secantial_operations:
            secantial_operations[user_id] = {"files": [], "expected_count": 0}
        secantial_operations[user_id]["expected_count"] += 1

        if episode_number or saison:
            placeholders = {
                "episode": episode_number,
                "saison": saison,
                "quality": extracted_qualities
            }
            
            for ph, value in placeholders.items():
                if value:
                    for variant in [ph, ph.capitalize(), ph.upper(), f"{{{ph}}}"]:
                        if variant in format_template:
                            format_template = format_template.replace(variant, str(value))

        _, file_extension = os.path.splitext(file_name)
        renamed_file_name = f"{format_template}{file_extension}"
        renamed_file_path = os.path.join(user_dirs['downloads'], renamed_file_name)
        metadata_file_path = os.path.join(user_dirs['metadata'], renamed_file_name)
        file_uuid = str(uuid.uuid4())[:8]
        renamed_file_path_with_uuid = f"{renamed_file_path}_{file_uuid}"

        await queue_message.edit_text(f"📥 **Téléchargement en cours :** `{file_name}`")
        try:
            path = await client.download_media(
                message,
                file_name=renamed_file_path_with_uuid,
                progress=progress_for_pyrogram,
                progress_args=("Téléchargement en cours...", queue_message, time.time()),
            )
        except Exception as e:
            del renaming_operations[file_id]
            return await queue_message.edit_text(f"**Erreur de téléchargement:** {e}")

        await queue_message.edit_text(f"🔄 **Renommage et ajout de métadonnées :** `{file_name}`")
        try:
            os.rename(path, renamed_file_path)
            path = renamed_file_path

            metadata_added = False
            if await hyoshcoder.get_metadata(user_id):
                metadata = await hyoshcoder.get_metadata_code(user_id)
                if metadata:
                    cmd = f'ffmpeg -i "{renamed_file_path}" -map 0 -c copy -metadata title="{metadata}" -metadata author="{metadata}" "{metadata_file_path}"'
                    try:
                        process = await asyncio.create_subprocess_shell(
                            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                        stdout, stderr = await process.communicate()
                        
                        if process.returncode == 0:
                            metadata_added = True
                            path = metadata_file_path
                        else:
                            error_message = stderr.decode()
                            await queue_message.edit_text(f"**Erreur de métadonnées:**\n{error_message[:200]}...")
                    except Exception as e:
                        await queue_message.edit_text(f"**Exception lors de l'ajout des métadonnées:**\n{str(e)}")
            else:
                metadata_added = True

            if not metadata_added:
                await queue_message.edit_text("L'ajout des métadonnées a échoué. Téléversement du fichier renommé.")
                path = renamed_file_path

            await queue_message.edit_text(f"📤 **Téléversement en cours :** `{file_name}`")
            await asyncio.sleep(2)
            
            ph_path = None
            c_caption = await hyoshcoder.get_caption(message.chat.id)
            c_thumb = await hyoshcoder.get_thumbnail(message.chat.id)

            if message.document:
                file_size = humanbytes(message.document.file_size)
                duration = convert(0)
            elif message.video:
                file_size = humanbytes(message.video.file_size)
                duration = convert(message.video.duration or 0)
            else:
                await queue_message.edit_text("Type de fichier non supporté")
                return

            caption = (
                c_caption.format(
                    filename=renamed_file_name,
                    filesize=file_size,
                    duration=duration,
                ) if c_caption else f"**{renamed_file_name}**"
            )

            if c_thumb:
                ph_path = await client.download_media(c_thumb, file_name=os.path.join(user_dirs['thumbnails'], "thumbnail.jpg"))
            elif media_type == "video" and hasattr(message.video, 'thumbs') and message.video.thumbs:
                ph_path = await client.download_media(
                    message.video.thumbs[0].file_id, 
                    file_name=os.path.join(user_dirs['thumbnails'], "video_thumb.jpg")
                )

            if ph_path:
                try:
                    img = Image.open(ph_path).convert("RGB")
                    img = img.resize((320, 320))
                    img.save(ph_path, "JPEG", quality=90)
                except Exception as e:
                    print(f"Erreur traitement miniature: {e}")
                    ph_path = None

            try:
                if sequential_mode:
                    log_message = await client.send_document(
                        settings.LOG_CHANNEL,
                        document=path,
                        thumb=ph_path,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=("Téléversement en cours...", queue_message, time.time()),
                    )
                    
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

                        user_channel = await hyoshcoder.get_user_channel(user_id) or user_id
                        
                        try:
                            await client.get_chat(user_channel)
                            for file_info in sorted_files:
                                await asyncio.sleep(3)
                                await client.copy_message(
                                    user_channel,
                                    settings.LOG_CHANNEL,
                                    file_info["message_id"]
                                )
                            await queue_message.reply_text(
                                f"✅ Tous les fichiers envoyés dans: `{user_channel}`\n"
                                "Si certains fichiers manquent, c'est dû aux limites de Telegram."
                            )
                        except Exception as e:
                            await queue_message.reply_text(f"❌ Erreur avec le canal {user_channel}: {e}")
                            for file_info in sorted_files:
                                await asyncio.sleep(3)
                                await client.copy_message(
                                    user_id,
                                    settings.LOG_CHANNEL,
                                    file_info["message_id"]
                                )
                            await queue_message.reply_text("✅ Fichiers envoyés en privé")

                        del secantial_operations[user_id]
                else:
                    send_method = {
                        "document": client.send_document,
                        "video": client.send_video,
                        "audio": client.send_audio
                    }.get(media_type, client.send_document)

                    await send_method(
                        message.chat.id,
                        path,
                        thumb=ph_path,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=("Téléversement en cours...", queue_message, time.time()),
                        **({"duration": duration} if media_type != "document" else {})
                    )

            except Exception as e:
                if os.path.exists(renamed_file_path):
                    os.remove(renamed_file_path)
                if ph_path and os.path.exists(ph_path):
                    os.remove(ph_path)
                return await queue_message.edit_text(f"❌ Erreur : {e}")

            if os.path.exists(renamed_file_path):
                os.remove(renamed_file_path)
            if ph_path and os.path.exists(ph_path):
                os.remove(ph_path)

            await queue_message.delete()

        finally:
            await hyoshcoder.degrade_points(user_id, 1)
            for file_path in [renamed_file_path, metadata_file_path, ph_path]:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
            del renaming_operations[file_id]
    finally:
        user_semaphore.release()