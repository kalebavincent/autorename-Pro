from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InputMediaDocument, Message, InlineKeyboardButton, InlineKeyboardMarkup
from PIL import Image
from datetime import datetime, timedelta
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from helpers.utils import progress_for_pyrogram, humanbytes, convert, extract_episode, extract_quality, extract_season, get_media_duration
from database.data import hyoshcoder
from config import settings
import os
import time
import re
import subprocess
import asyncio
import uuid
from shutil import rmtree

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

def get_user_file_paths(user_id, file_name=None, timestamp=None):
    """Retourne les chemins des fichiers organisés par utilisateur"""
    if not timestamp:
        timestamp = int(time.time())
    
    base_paths = {
        'downloads': f"downloads/{user_id}/{timestamp}",
        'metadata': f"Metadata/{user_id}/{timestamp}",
        'thumbnails': f"thumbnails/{user_id}/{timestamp}"
    }
    
    if file_name:
        _, file_extension = os.path.splitext(file_name)
        return {
            'renamed': f"{base_paths['downloads']}/{file_name}",
            'metadata': f"{base_paths['metadata']}/{file_name}",
            'thumbnail': f"{base_paths['thumbnails']}/thumbnail.jpg"
        }
    return base_paths

async def generate_video_thumbnail(video_path, output_path, time_position="00:00:01"):
    try:
        cmd = [
            'ffmpeg',
            '-ss', time_position,
            '-i', video_path,
            '-vframes', '1',
            '-q:v', '2',
            '-y', output_path
        ]
        process = await asyncio.create_subprocess_shell(
            ' '.join(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        return process.returncode == 0
    except Exception as e:
        print(f"Erreur génération thumbnail: {e}")
        return False

@Client.on_message(filters.command("refresh") & filters.private)
async def refresh_user_data(client, message):
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
    user_id = message.from_user.id
    timestamp = int(time.time())
    
    user_paths = get_user_file_paths(user_id, timestamp=timestamp)
    for path in user_paths.values():
        os.makedirs(path, exist_ok=True)

    user_data = await hyoshcoder.read_user(user_id)
    if not user_data:
        return await message.reply_text("❌ Impossible de charger vos informations. Veuillez vous inscrire /start.")

    user_points = user_data.get("points", 0)
    if user_points < 1:
        return await message.reply_text(
            "❌ Vous n'avez pas assez de points pour renommer un fichier.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Free points", callback_data="free_points")]])
        )

    format_template = user_data.get("format_template", "")
    if not format_template:
        return await message.reply_text("Veuillez d'abord définir un format de renommage automatique en utilisant /autorename")

    media_preference = user_data.get("media_type", "")
    sequential_mode = user_data.get("sequential_mode", False)
    src_info = await hyoshcoder.get_src_info(user_id)

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "document"
        media_type = media_preference or "document"
    elif message.video:
        file_id = message.video.file_id
        file_name = f"{message.video.file_name or 'video'}.mp4"
        media_type = media_preference or "video"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = f"{message.audio.file_name or 'audio'}.mp3"
        media_type = media_preference or "audio"
    else:
        return await message.reply_text("Type de fichier non supporté")

    if file_id in renaming_operations:
        elapsed_time = (datetime.now() - renaming_operations[file_id]).seconds
        if elapsed_time < 10:
            return

    renaming_operations[file_id] = datetime.now()

    try:
        if src_info == "file_name":
            episode_number = await extract_episode(file_name)
            saison = await extract_season(file_name)
            extracted_qualities = await extract_quality(file_name)
        elif src_info == "caption":
            caption = message.caption or ""
            episode_number = await extract_episode(caption) or await extract_episode(file_name)
            saison = await extract_season(caption) or await extract_season(file_name)
            extracted_qualities = await extract_quality(caption) or await extract_quality(file_name)
        else:
            episode_number = await extract_episode(file_name)
            saison = await extract_season(file_name)
            extracted_qualities = await extract_quality(file_name)
    except Exception as e:
        print(f"Erreur extraction métadonnées: {e}")
        episode_number = None
        saison = None
        extracted_qualities = None

    assurance_message = (
        "**Fichier ajouté à la file d'attente ✅**\n"
        f"➲ **Nom :** `{file_name}`\n"
        f"➲ **Saison :** `{saison or 'N/A'}`\n"
        f"➲ **Épisode :** `{episode_number or 'N/A'}`\n"
        f"➲ **Qualité :** `{extracted_qualities or 'N/A'}`"
    )

    queue_message = await message.reply_text(assurance_message)

    if user_id not in user_queue_messages:
        user_queue_messages[user_id] = []
    user_queue_messages[user_id].append(queue_message)

    user_semaphore = await get_user_semaphore(user_id)
    await user_semaphore.acquire()

    try:
        if user_queue_messages.get(user_id):
            try:
                await user_queue_messages[user_id][0].edit_text(f"🔄 **Traitement du fichier :**\n➲ **Filename :** `{file_name}`")
                user_queue_messages[user_id].pop(0)
            except Exception as e:
                print(f"Erreur mise à jour message file d'attente: {e}")
            
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
        file_paths = get_user_file_paths(user_id, renamed_file_name, timestamp)
        
        file_uuid = str(uuid.uuid4())[:8]
        temp_file_path = f"{file_paths['renamed']}_{file_uuid}"

        await queue_message.edit_text(f"📥 **Téléchargement en cours :** `{file_name}`")
        try:
            path = await client.download_media(
                message,
                file_name=temp_file_path,
                progress=progress_for_pyrogram,
                progress_args=("Téléchargement en cours...", queue_message, time.time()),
            )
        except Exception as e:
            del renaming_operations[file_id]
            secantial_operations[user_id]["expected_count"] -= 1
            return await queue_message.edit_text(f"**Erreur de téléchargement:** {e}")
        finally:
            if os.path.exists(temp_file_path):
                os.rename(temp_file_path, file_paths['renamed'])
                path = file_paths['renamed']

        await queue_message.edit_text(f"🔄 **Renommage et ajout de métadonnées :** `{file_name}`")
        try:
            metadata_added = False
            if await hyoshcoder.get_metadata(user_id):
                metadata = await hyoshcoder.get_metadata_code(user_id)
                if metadata:
                    cmd = f'ffmpeg -i "{file_paths["renamed"]}" -map 0 -c copy -metadata title="{metadata}" -metadata author="{metadata}" "{file_paths["metadata"]}"'
                    try:
                        process = await asyncio.create_subprocess_shell(
                            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                        await process.communicate()
                        
                        if process.returncode == 0:
                            metadata_added = True
                            path = file_paths['metadata']
                    except Exception as e:
                        print(f"Erreur métadonnées: {e}")
            else:
                metadata_added = True

            if not metadata_added:
                await queue_message.edit_text("L'ajout des métadonnées a échoué. Téléversement du fichier renommé.")
                path = file_paths['renamed']

            await queue_message.edit_text(f"📤 **Téléversement en cours :** `{file_name}`")
            await asyncio.sleep(2)
            
            ph_path = None
            c_caption = await hyoshcoder.get_caption(message.chat.id)
            c_thumb = await hyoshcoder.get_thumbnail(message.chat.id)

            file_size = humanbytes(message.document.file_size if message.document else (
                message.video.file_size if message.video else message.audio.file_size))
            
            duration = 0
            width, height = 320, 180
            if media_type != "document":
                try:
                    duration = get_media_duration(path)
                    metadata = extractMetadata(createParser(path))
                    if metadata and metadata.has("width") and metadata.has("height"):
                        original_width = metadata.get("width")
                        original_height = metadata.get("height")
                        if original_width / original_height != 16 / 9:
                            height = 180
                            width = int(height * 16 / 9)
                        else:
                            width = original_width
                            height = original_height
                except Exception as e:
                    print(f"Erreur lecture métadonnées: {e}")

            caption = (
                c_caption.format(
                    filename=renamed_file_name,
                    filesize=file_size,
                    duration=convert(duration),
                ) if c_caption else f"**{renamed_file_name}**"
            )

            try:
                if c_thumb:
                    ph_path = await client.download_media(c_thumb, file_name=file_paths['thumbnail'])
                elif media_type == "video" and hasattr(message.video, 'thumbs') and message.video.thumbs:
                    ph_path = await client.download_media(
                        message.video.thumbs[0].file_id, 
                        file_name=file_paths['thumbnail']
                    )
                elif media_type == "video":
                    ph_path = file_paths['thumbnail']
                    if not await generate_video_thumbnail(path, ph_path):
                        ph_path = None
            except Exception as e:
                print(f"Erreur gestion thumbnail: {e}")
                ph_path = None

            if ph_path and os.path.exists(ph_path):
                try:
                    img = Image.open(ph_path).convert("RGB")
                    img = img.resize((320, 320))
                    img.save(ph_path, "JPEG", quality=90)
                except Exception as e:
                    print(f"Erreur traitement miniature: {e}")
                    ph_path = None

            try:
                if sequential_mode:
                    send_method = {
                        "document": client.send_document,
                        "video": client.send_video,
                        "audio": client.send_audio
                    }.get(media_type)
                    
                    if not send_method:
                        await queue_message.reply_text("❌ Type de média non pris en charge.")
                        secantial_operations[user_id]["expected_count"] -= 1
                        return

                    send_params = {
                        "chat_id": settings.DUMP_CHANNEL,
                        "caption": caption,
                        "thumb": ph_path,
                        "progress": progress_for_pyrogram,
                        "progress_args": ("Téléversement en cours...", queue_message, time.time())
                    }
                    
                    if media_type == "video":
                        send_params.update({
                            "width": width,
                            "height": height,
                            "duration": int(duration),
                            "video": path
                        })
                    elif media_type == "audio":
                        send_params.update({
                            "duration": int(duration),
                            "audio": path
                        })
                    else:
                        send_params["document"] = path
                    
                    log_message = await send_method(**send_params)

                    secantial_operations[user_id]["files"].append({
                        "message_id": log_message.id,
                        "file_name": renamed_file_name,
                        "season": saison,
                        "episode": episode_number
                    })

                    if len(secantial_operations[user_id]["files"]) == secantial_operations[user_id]["expected_count"]:
                        sorted_files = sorted(
                            secantial_operations[user_id]["files"],
                            key=lambda x: (
                                int(x["season"]) if x["season"] else 0,
                                int(x["episode"]) if x["episode"] else 0
                            )
                        )

                        user_channel = await hyoshcoder.get_user_channel(user_id) or user_id
                        
                        try:
                            await client.get_chat(user_channel)
                            for file_info in sorted_files:
                                await asyncio.sleep(3)
                                await client.copy_message(
                                    user_channel,
                                    settings.DUMP_CHANNEL,
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
                                    settings.DUMP_CHANNEL,
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

                    send_params = {
                        "chat_id": message.chat.id,
                        "thumb": ph_path,
                        "caption": caption,
                        "progress": progress_for_pyrogram,
                        "progress_args": ("Téléversement en cours...", queue_message, time.time())
                    }
                    
                    if media_type == "video":
                        send_params.update({
                            "width": width,
                            "height": height,
                            "duration": int(duration),
                            "video": path
                        })
                    elif media_type == "audio":
                        send_params.update({
                            "duration": int(duration),
                            "audio": path
                        })
                    else:
                        send_params["document"] = path
                    
                    await send_method(**send_params)

            except Exception as e:
                if os.path.exists(file_paths['renamed']):
                    os.remove(file_paths['renamed'])
                if ph_path and os.path.exists(ph_path):
                    os.remove(ph_path)
                del renaming_operations[file_id]
                secantial_operations[user_id]["expected_count"] -= 1
                return await queue_message.edit_text(f"❌ Erreur : {e}")

            for file_path in [file_paths['renamed'], file_paths['metadata'], ph_path]:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        print(f"Erreur suppression fichier {file_path}: {e}")
            del renaming_operations[file_id]
        except Exception as e:
            print(f"Erreur traitement fichier: {e}")
            if os.path.exists(file_paths['renamed']):
                os.remove(file_paths['renamed'])
            if ph_path and os.path.exists(ph_path):
                os.remove(ph_path)
            del renaming_operations[file_id]
            secantial_operations[user_id]["expected_count"] -= 1
            return await queue_message.edit_text(f"❌ Erreur lors du traitement: {e}")
    finally:
        user_semaphore.release()