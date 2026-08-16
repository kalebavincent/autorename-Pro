"""
Plugin : AutoCaption / Édition Automatique de Caption en Lot
Fonctionne dans les canaux et supergroupes / groupes.

Principe :
1. Écoute les messages ÉDITÉS (`@Client.on_edited_message`).
2. Si le message édité contient un document ou une vidéo :
   - Extrait le nouveau caption du message édité.
   - Analyser le caption/filename pour détecter l'épisode, la saison et la qualité ainsi que leurs emplacements.
   - Génère un modèle de caption (`template`) avec les placeholders {saison}, {episode}, {quality}.
   - Sauvegarde ce modèle pour le canal.
3. Parcours les messages SUIVANTS (ID > message.id) :
   - Si le message contient un document ou une vidéo :
     - Extrait les informations (saison, épisode, qualité) de son caption ou de son filename.
     - Si l'épisode manque, auto-incrémente par rapport au fichier précédent.
     - Applique le modèle et modifie automatiquement le caption (`edit_message_caption`).
   - Si on rencontre un message texte seul, sticker, image, animation ou autre non-vidéo/document :
     - S'ARRÊTE IMMÉDIATEMENT.
"""

import asyncio
import re
import logging
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, MessageNotModified, MessageIdInvalid

from database.data import hyoshcoder
from helpers.utils import extract_episode, extract_season, extract_quality

logger = logging.getLogger(__name__)

# Locks par chat pour éviter que deux éditions simultanées s'affrontent
channel_locks = {}


def create_caption_template(caption: str, ep: Optional[str], season: Optional[str], quality: Optional[str]) -> str:
    """
    Crée un modèle de caption en remplaçant les valeurs détectées (qualité, épisode, saison)
    par les placeholders {quality}, {episode}, {saison}.
    """
    template = caption

    # 1. Remplacement de la qualité (ex: 1080p, 720p, 4k, Convertie)
    if quality and quality in template:
        template = template.replace(quality, "{quality}", 1)

    # 2. Remplacement de l'épisode
    if ep:
        ep_patterns = [
            rf'(?i)(Épisode|Episode|Ép|Ep|E)\s*[-:]?\s*{re.escape(ep)}',
            rf'\b{re.escape(ep)}\b'
        ]
        replaced = False
        for pat in ep_patterns:
            m = re.search(pat, template)
            if m:
                prefix = m.group(1) if m.groups() else ""
                if prefix:
                    template = template[:m.start()] + f"{prefix}{{episode}}" + template[m.end():]
                else:
                    template = template[:m.start()] + "{episode}" + template[m.end():]
                replaced = True
                break
        if not replaced and ep in template:
            template = template.replace(ep, "{episode}", 1)

    # 3. Remplacement de la saison
    if season:
        sn_patterns = [
            rf'(?i)(Saison|S)\s*[-:]?\s*{re.escape(season)}',
            rf'\b{re.escape(season)}\b'
        ]
        replaced = False
        for pat in sn_patterns:
            m = re.search(pat, template)
            if m:
                prefix = m.group(1) if m.groups() else ""
                if prefix:
                    template = template[:m.start()] + f"{prefix}{{saison}}" + template[m.end():]
                else:
                    template = template[:m.start()] + "{saison}" + template[m.end():]
                replaced = True
                break
        if not replaced and season in template:
            template = template.replace(season, "{saison}", 1)

    return template


def safe_format_caption(template: str, season: str, episode: str, quality: str) -> str:
    """
    Formatage sécurisé par remplacement direct de chaînes (évite les erreurs KeyError sur les acrotères {}).
    """
    res = template
    res = res.replace("{saison}", str(season))
    res = res.replace("{season}", str(season))
    res = res.replace("{episode}", str(episode))
    res = res.replace("{quality}", str(quality))
    return res


@Client.on_edited_message(filters.channel | filters.group | filters.supergroup)
async def auto_caption_on_edited(client: Client, message: Message):
    # Ne traiter que les messages ayant un document ou une vidéo et un caption
    if not (message.document or message.video):
        return

    edited_caption = message.caption
    if not edited_caption or not edited_caption.strip():
        return

    chat_id  = message.chat.id
    start_id = message.id

    # Obtenir ou créer un verrou pour ce canal/groupe
    if chat_id not in channel_locks:
        channel_locks[chat_id] = asyncio.Lock()

    # Tenter d'acquérir le verrou (si un batch est déjà en cours, ignorer les nouveaux déclenchements)
    if channel_locks[chat_id].locked():
        return

    async with channel_locks[chat_id]:
        media = message.document or message.video
        file_name = media.file_name or ""

        # 1. Extraire les métadonnées de l'élément édité (caption ou filename)
        ep     = await extract_episode(edited_caption) or await extract_episode(file_name)
        season = await extract_season(edited_caption) or await extract_season(file_name)
        quality = await extract_quality(edited_caption)
        if quality == "Convertie" and file_name:
            quality = await extract_quality(file_name)

        # 2. Créer le modèle de caption pour ce canal
        template = create_caption_template(edited_caption, ep, season, quality)
        await hyoshcoder.set_channel_template(chat_id, template)

        logger.info(
            f"AutoCaption déclenché dans {chat_id} (msg {start_id}). "
            f"Détectés -> S:{season}, E:{ep}, Q:{quality}. Modèle généré: '{template}'"
        )

        last_ep_num = int(ep) if (ep and ep.isdigit()) else None
        last_season = season or "01"

        # 3. Parcourir les messages suivants pour appliquer le modèle
        batch_limit = 200  # Sécurité : traiter au max 200 messages consécutifs
        for offset in range(1, batch_limit + 1):
            next_id = start_id + offset
            try:
                next_msg = await client.get_messages(chat_id, next_id)
            except Exception as e:
                logger.warning(f"AutoCaption: Erreur lors de la récupération du message {next_id}: {e}")
                break

            # Message inexistant ou vide (ex: supprimé) -> continuer
            if not next_msg or next_msg.empty:
                continue

            # Vérifier s'il s'agit d'un document ou d'une vidéo
            is_valid_media = bool(next_msg.document or next_msg.video)

            # RÈGLE STRICTE : Si c'est un message texte seul, sticker, photo, image, etc. -> S'ARRÊTER !
            if not is_valid_media:
                logger.info(
                    f"AutoCaption: Message non-document/vidéo rencontré (ID: {next_id}). "
                    f"Arrêt du traitement par lot."
                )
                break

            # C'est un document ou une vidéo -> procéder à la détection et mise à jour
            target_media = next_msg.document or next_msg.video
            msg_file_name = target_media.file_name or ""
            curr_caption = next_msg.caption or ""

            msg_ep     = await extract_episode(curr_caption) or await extract_episode(msg_file_name)
            msg_season = await extract_season(curr_caption) or await extract_season(msg_file_name) or last_season
            msg_quality = await extract_quality(curr_caption)
            if msg_quality == "Convertie" and msg_file_name:
                msg_quality = await extract_quality(msg_file_name)

            # Auto-incrémentation si l'épisode est introuvable
            if not msg_ep and last_ep_num is not None:
                last_ep_num += 1
                msg_ep = f"{last_ep_num:02d}"
            elif msg_ep and msg_ep.isdigit():
                last_ep_num = int(msg_ep)

            if not msg_ep:
                msg_ep = "01"

            # Formater la nouvelle caption
            new_caption = safe_format_caption(
                template=template,
                season=msg_season or "01",
                episode=msg_ep or "01",
                quality=msg_quality or "HD"
            )

            # Si la caption a besoin d'être éditée
            if next_msg.caption != new_caption:
                try:
                    await client.edit_message_caption(chat_id, next_id, caption=new_caption)
                    logger.info(f"AutoCaption: Message {next_id} édité avec succès (E:{msg_ep})")
                    await asyncio.sleep(0.8)  # Pause pour éviter FloodWait
                except MessageNotModified:
                    pass
                except FloodWait as f:
                    logger.warning(f"AutoCaption: FloodWait de {f.value}s sur le message {next_id}. Attente...")
                    await asyncio.sleep(f.value + 1)
                    try:
                        await client.edit_message_caption(chat_id, next_id, caption=new_caption)
                    except Exception as ex:
                        logger.error(f"AutoCaption: Échec édition après FloodWait sur {next_id}: {ex}")
                except Exception as e:
                    logger.error(f"AutoCaption: Impossible d'éditer le message {next_id}: {e}")
