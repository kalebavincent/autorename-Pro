"""
Plugin : Points de Secours — /ilove_thebot
- 50 points/jour régénérés uniquement dans le groupe dédié
- Si l'user n'est pas membre → lien d'invitation 1 personne/24h
- Expire à 00:00 UTC chaque jour
"""
import datetime
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, PeerIdInvalid
from database.data import hyoshcoder
from config import settings
from helpers.utils import get_random_photo
import logging

logger = logging.getLogger(__name__)

BACKUP_GROUP_ID = settings.BACKUP_GROUP_ID
DAILY_BACKUP   = settings.DAILY_BACKUP_POINTS   # 50


# ──────────────────────────────────────────────────────────────────────────────
# Helper : points valides ou reset automatique
# ──────────────────────────────────────────────────────────────────────────────

async def get_valid_backup_points(user_id: int) -> tuple:
    """
    Retourne (backup_points, backup_date, already_generated_today).

    - Si backup_date == aujourd'hui UTC → retourne les points restants, date, True.
    - Si backup_date != aujourd'hui UTC → les points d'hier ont expiré (retourne 0, date, False).
    """
    bp, bd = await hyoshcoder.get_backup_info(user_id)
    today_utc = datetime.date.today().isoformat()

    if bd == today_utc:
        return bp, bd, True          # Déjà régénérés aujourd'hui, points valides
    else:
        return 0, bd, False         # Non régénérés aujourd'hui → 0 points (points d'hier expirés)


# ──────────────────────────────────────────────────────────────────────────────
# /ilove_thebot
# ──────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("ilove_thebot"))
async def ilove_thebot(client: Client, message: Message):
    user_id   = message.from_user.id
    chat_id   = message.chat.id
    chat_type = message.chat.type.name  # "PRIVATE" | "GROUP" | "SUPERGROUP"
    img       = await get_random_photo()

    # ── Dans le groupe dédié ─────────────────────────────────────────────────
    if chat_id == BACKUP_GROUP_ID:
        bp, bd, already_done = await get_valid_backup_points(user_id)
        today_utc = datetime.date.today().isoformat()

        if already_done:
            # Calculer les secondes restantes avant 00:00 UTC
            now_utc   = datetime.datetime.utcnow()
            midnight  = datetime.datetime(now_utc.year, now_utc.month, now_utc.day) \
                        + datetime.timedelta(days=1)
            remaining = midnight - now_utc
            hours, rem   = divmod(int(remaining.total_seconds()), 3600)
            minutes, secs = divmod(rem, 60)

            txt = (
                f"⏳ **Points de secours déjà régénérés aujourd'hui !**\n\n"
                f"🔋 Points restants : **{bp}/{DAILY_BACKUP}**\n"
                f"🕛 Prochain reset dans : **{hours}h {minutes}m {secs}s** (00:00 UTC)\n\n"
                "Utilisez vos points de secours pour renommer des fichiers."
            )
            await message.reply_text(txt)
            return

        # Pas encore régénérés → reset
        await hyoshcoder.reset_backup_points(user_id)
        txt = (
            f"💙 **{message.from_user.mention} — Points de secours régénérés !**\n\n"
            f"🔋 **+{DAILY_BACKUP} points de secours** ajoutés à votre compte.\n"
            f"📅 Valides jusqu'à **00:00 UTC** ce soir.\n\n"
            "_Ces points s'utilisent automatiquement quand votre quota d'abonnement "
            "est épuisé._"
        )
        if img:
            await message.reply_photo(photo=img, caption=txt)
        else:
            await message.reply_text(txt)
        return

    # ── En message privé (ou autre groupe) ───────────────────────────────────
    if chat_type == "PRIVATE":
        if BACKUP_GROUP_ID == 0:
            await message.reply_text("❌ Groupe de secours non configuré.")
            return

        # Vérifier si l'user est déjà dans le groupe
        already_member = False
        try:
            member = await client.get_chat_member(BACKUP_GROUP_ID, user_id)
            if member.status.name not in ("LEFT", "BANNED", "KICKED"):
                already_member = True
        except UserNotParticipant:
            already_member = False
        except Exception as e:
            logger.warning(f"Cannot check membership for {user_id}: {e}")

        if already_member:
            # Déjà membre → lui dire de taper dans le groupe
            bp, _, already_done = await get_valid_backup_points(user_id)
            try:
                group = await client.get_chat(BACKUP_GROUP_ID)
                group_link = f"https://t.me/{group.username}" if group.username else None
            except Exception:
                group_link = None

            if already_done:
                now_utc   = datetime.datetime.utcnow()
                midnight  = datetime.datetime(now_utc.year, now_utc.month, now_utc.day) \
                            + datetime.timedelta(days=1)
                remaining = midnight - now_utc
                hours, rem   = divmod(int(remaining.total_seconds()), 3600)
                minutes, secs = divmod(rem, 60)
                txt = (
                    f"⏳ **Vous avez déjà régénéré vos points aujourd'hui !**\n\n"
                    f"🔋 Points de secours restants : **{bp}/{DAILY_BACKUP}**\n"
                    f"🕛 Prochain reset dans : **{hours}h {minutes}m {secs}s**\n\n"
                    "Revenez demain après **00:00 UTC** pour en obtenir de nouveaux."
                )
            else:
                txt = (
                    f"✅ Vous êtes déjà dans le groupe !\n\n"
                    f"🔋 Points de secours disponibles : **{bp}**\n\n"
                    "Tapez `/ilove_thebot` directement dans le groupe pour régénérer "
                    "vos **50 points de secours** journaliers."
                )

            buttons = []
            if group_link:
                buttons.append([InlineKeyboardButton("💬 Aller dans le groupe", url=group_link)])
            if img:
                await message.reply_photo(photo=img, caption=txt,
                                          reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
            else:
                await message.reply_text(txt,
                                         reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
            return

        # Pas membre → générer un lien d'invitation à usage unique (24h)
        try:
            expire_dt = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
            invite = await client.create_chat_invite_link(
                BACKUP_GROUP_ID,
                member_limit=1,
                expire_date=expire_dt,
                name=f"backup_{user_id}"
            )
            invite_url = invite.invite_link

            txt = (
                "💙 **Points de Secours Journaliers**\n\n"
                "Rejoignez notre groupe dédié pour régénérer **vos points de secours** "
                "chaque jour gratuitement.\n\n"
                "🔑 Ce lien est **à usage unique** et expire dans **24h**.\n\n"
                "Une fois dans le groupe, tapez `/ilove_thebot` pour activer vos points."
            )
            buttons = [[InlineKeyboardButton("🚀 Rejoindre le groupe", url=invite_url)]]
            if img:
                await message.reply_photo(photo=img, caption=txt,
                                          reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await message.reply_text(txt, reply_markup=InlineKeyboardMarkup(buttons))

        except ChatAdminRequired:
            await message.reply_text(
                "❌ Le bot n'est pas admin du groupe de secours.\n"
                "Contactez l'administrateur."
            )
        except Exception as e:
            logger.error(f"Error creating invite link for {user_id}: {e}")
            await message.reply_text(
                "❌ Impossible de générer le lien d'invitation. Réessayez plus tard."
            )
    else:
        # Mauvais groupe → ignorer silencieusement ou répondre
        await message.reply_text(
            "⚠️ Cette commande ne fonctionne que dans le groupe dédié ou en message privé."
        )
