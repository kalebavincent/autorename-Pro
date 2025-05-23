from datetime import datetime, timezone
import math
import random
import re
import time
from typing import Optional, Tuple
import math, time
from shortzy import Shortzy
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from scripts import Txt

import ffmpeg

from config import settings



# Patterns for extracting season numbers
SEASON_PATTERNS = [
    re.compile(r'(?:S|Saison)\s*-?\s*(\d+)', re.IGNORECASE),
    re.compile(r'Saison\s*(\d+)\s*\b(?:Episode|Ep|E)\s*\d+', re.IGNORECASE),
    re.compile(r'S(?P<season>\d+)(?:E|EP)\d+', re.IGNORECASE),
    re.compile(r'S(?P<season>\d+)\s*-\s*E\d+', re.IGNORECASE),
    re.compile(r'SO?\s*(\d+)\s*EP?\s*\d+', re.IGNORECASE),
]

# Patterns for extracting episode numbers
EPISODE_PATTERNS = [
    re.compile(r'(?:E|Épisode)\s*-?\s*(\d+)', re.IGNORECASE),
    re.compile(r'Saison\s*\d+\s*(?:Episode|Ep|E)\s*(\d+)', re.IGNORECASE),
    re.compile(r'S\d+(?:E|EP)(\d+)', re.IGNORECASE),
    re.compile(r'S\d+\s*-\s*E(\d+)', re.IGNORECASE),
    re.compile(r'EP?(\d{2})\b', re.IGNORECASE),
    re.compile(r'\b(\d{1,4})\b(?!\s*[pP])', re.IGNORECASE),
]

# Patterns for extracting quality
QUALITY_PATTERNS = {
    re.compile(r'\b(?:.*?(\d{3,4}[^\dp]*p).*?|.*?(\d{3,4}p))\b', re.IGNORECASE): lambda match: match.group(1) or match.group(2),
    re.compile(r'[([<{]?\s*4k\s*[)\]>}]?', re.IGNORECASE): lambda _: "4k",
    re.compile(r'[([<{]?\s*2k\s*[)\]>}]?', re.IGNORECASE): lambda _: "2k",
    re.compile(r'[([<{]?\s*HdRip\s*[)\]>}]?|\bHdRip\b', re.IGNORECASE): lambda _: "HdRip",
    re.compile(r'[([<{]?\s*4kX264\s*[)\]>}]?', re.IGNORECASE): lambda _: "4kX264",
    re.compile(r'[([<{]?\s*4kx265\s*[)\]>}]?', re.IGNORECASE): lambda _: "4kx265",
    re.compile(r'[([<{]?\s*UHD\s*[)\]>}]?', re.IGNORECASE): lambda _: "UHD",
    re.compile(r'[([<{]?\s*HD\s*[)\]>}]?', re.IGNORECASE): lambda _: "HD",
    re.compile(r'[([<{]?\s*SD\s*[)\]>}]?', re.IGNORECASE): lambda _: "SD",
    re.compile(r'[([<{]?\s*convertie\s*[)\]>}]?', re.IGNORECASE): lambda _: "convertie",
    re.compile(r'[([<{]?\s*converti\s*[)\]>}]?', re.IGNORECASE): lambda _: "convertie",
    re.compile(r'[([<{]?\s*convertis\s*[)\]>}]?', re.IGNORECASE): lambda _: "convertie",
}

async def extract_season(filename: str) -> Optional[str]:
    """
    Extrait le numéro de saison sous forme de chaîne de caractères.
    Retourne None si aucun numéro de saison n'est trouvé.
    """
    for pattern in SEASON_PATTERNS:
        match = pattern.search(filename)
        if match:
            return match.group(1)
    return None

async def extract_episode(filename: str) -> Optional[str]:
    """
    Extrait le numéro d'épisode sous forme de chaîne de caractères.
    Retourne None si aucun numéro d'épisode n'est trouvé.
    """
    for pattern in EPISODE_PATTERNS:
        match = pattern.search(filename)
        if match:
            return match.group(1)  
    return None

async def extract_season_episode(filename: str) -> Optional[Tuple[str, str]]:
    """
    Extrait à la fois le numéro de saison et d'épisode sous forme de chaînes de caractères.
    Retourne None si aucun des deux n'est trouvé.
    """
    season = await extract_season(filename)
    episode = await extract_episode(filename)
    
    if episode is not None and season is None:
        season = "01"  # Valeur par défaut pour la saison si elle n'est pas trouvée
    
    if season is not None and episode is not None:
        return season, episode
    return None

async def extract_quality(filename: str) -> str:
    """
    Extrait la qualité de la vidéo.
    Retourne "Unknown" si aucune qualité n'est trouvée.
    """
    for pattern, extractor in QUALITY_PATTERNS.items():
        match = pattern.search(filename)
        if match:
            return extractor(match)
    return "Unknown"


async def progress_for_pyrogram(current, total, ud_type, message, start):
    now = time.time()
    diff = now - start
    if round(diff % 5.00) == 0 or current == total:        
        percentage = current * 100 / total
        speed = current / diff
        elapsed_time = round(diff) * 1000
        time_to_completion = round((total - current) / speed) * 1000
        estimated_total_time = elapsed_time + time_to_completion

        elapsed_time = TimeFormatter(milliseconds=elapsed_time)
        estimated_total_time = TimeFormatter(milliseconds=estimated_total_time)

        progress = "{0}{1}".format(
            ''.join(["█" for i in range(math.floor(percentage / 5))]),
            ''.join(["░" for i in range(20 - math.floor(percentage / 5))])
        )            
        tmp = progress + Txt.PROGRESS_BAR.format( 
            round(percentage, 2),
            humanbytes(current),
            humanbytes(total),
            humanbytes(speed),            
            estimated_total_time if estimated_total_time != '' else "0 s"
        )

        full_text = f"{ud_type}\n\n{tmp}"

        if len(full_text) <= 4096:
            try:
                await message.edit(text=full_text)
            except Exception as e:
                print(f"Erreur lors de l'édition du message : {e}")
                try:
                    new_message = await message.reply(text=full_text)
                    message = new_message
                except Exception as e:
                    print(f"Erreur lors de la création d'un nouveau message : {e}")
        else:
            chunks = [full_text[i:i + 4096] for i in range(0, len(full_text), 4096)]
            try:
                await message.edit(text=chunks[0])
                for chunk in chunks[1:]:
                    await message.reply(text=chunk)
            except Exception as e:
                print(f"Erreur lors de l'envoi du message : {e}")
                try:
                    new_message = await message.reply(text=chunks[0])
                    message = new_message
                    for chunk in chunks[1:]:
                        await message.reply(text=chunk)
                except Exception as e:
                    print(f"Erreur lors de la création d'un nouveau message : {e}")

def humanbytes(size):    
    if not size:
        return ""
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'ʙ'


def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "ᴅ, ") if days else "") + \
        ((str(hours) + "ʜ, ") if hours else "") + \
        ((str(minutes) + "ᴍ, ") if minutes else "") + \
        ((str(seconds) + "ꜱ, ") if seconds else "") + \
        ((str(milliseconds) + "ᴍꜱ, ") if milliseconds else "")
    return tmp[:-2] 

def convert(seconds):
    seconds = seconds % (24 * 3600)
    hour = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60      
    return "%d:%02d:%02d" % (hour, minutes, seconds)

def get_media_duration(file_path: str) -> float:
    """
    Récupère la durée d'un fichier vidéo ou audio en secondes avec ffmpeg.
    """
    try:
        probe = ffmpeg.probe(file_path)
        
        if 'format' in probe and 'duration' in probe['format']:
            duration = probe['format']['duration']
            if isinstance(duration, (int, float)):
                return float(duration)
            elif isinstance(duration, str):
                return float(duration)
            else:
                print(f"Format de durée non pris en charge dans 'format' : {type(duration)}")
        
        for stream in probe.get('streams', []):
            if stream.get('codec_type') in ['video', 'audio'] and 'duration' in stream:
                duration = stream['duration']
                if isinstance(duration, (int, float)):
                    return float(duration)
                elif isinstance(duration, str):
                    return float(duration)
                else:
                    print(f"Format de durée non pris en charge dans 'streams' : {type(duration)}")
        
        print("Aucune durée trouvée dans les métadonnées.")
        return 0
    except Exception as e:
        print(f"Erreur lors de la récupération de la durée : {e}")
        return 0

async def send_log(b, u):
    if settings.LOG_CHANNEL is not None:
        curr = datetime.now(timezone("Africa/Lubumbashi"))
        date = curr.strftime('%d %B, %Y')
        time = curr.strftime('%I:%M:%S %p')
        await b.send_message(
            settings.LOG_CHANNEL,
            f"**--Nᴏᴜᴠᴇᴀᴜ Uᴛɪʟɪꜱᴀᴛᴇᴜʀ A Dᴇ́ᴍᴀʀʀᴇ́ Lᴇ Bᴏᴛ--**\n\nUᴛɪʟɪꜱᴀᴛᴇᴜʀ : {u.mention}\nIᴅ : `{u.id}`\nNᴏᴍ ᴅ'ᴜᴛɪʟɪꜱᴀᴛᴇᴜʀ : @{u.username}\n\nDᴀᴛᴇ : {date}\nHᴏʀᴀɪʀᴇ : {time}\n\nPᴀʀ : {b.mention}"

        )

def add_prefix_suffix(input_string, prefix='', suffix=''):
    pattern = r'(?P<filename>.*?)(\.\w+)?$'
    match = re.search(pattern, input_string)
    if match:
        filename = match.group('filename')
        extension = match.group(2) or ''
        if prefix == None:
            if suffix == None:
                return f"{filename}{extension}"
            return f"{filename} {suffix}{extension}"
        elif suffix == None:
            if prefix == None:
               return f"{filename}{extension}"
            return f"{prefix}{filename}{extension}"
        else:
            return f"{prefix}{filename} {suffix}{extension}"


    else:
        return input_string
    
   
async def get_random_photo():
    try: 
        photos = settings.IMAGES.split(' ')
        random_photo = random.choice(photos)
        if random_photo:
            return random_photo
        else:
            return None
    except Exception as e:
        print(f"er: {e}")
        return None

async def get_shortlink(url, api, link):
    """
    Crée un lien raccourci avec Shortzy.
    """
    shortzy = Shortzy(api_key=api, base_site=url)
    shortlink = await shortzy.convert(link)
    return shortlink


nsfw_keywords = {
    "general": [
        "porn", "sex", "nude", "naked", "boobs", "tits", "pussy", "dick", "cock", "ass",
        "fuck", "blowjob", "cum", "orgasm", "shemale", "erotic", "masturbate", "anal",
        "hardcore", "bdsm", "fetish", "lingerie", "xxx", "milf", "gay", "lesbian",
        "threesome", "squirting", "butt plug", "dildo", "vibrator", "escort", "handjob",
        "striptease", "kinky", "pornstar", "sex tape", "spank", "swinger", "taboo", "cumshot",
        "deepthroat", "domination", "submission", "handcuffs", "orgy", "roleplay", "sex toy",
        "voyeur", "cosplay", "adult", "culture", "pornhwa",
        "netorare", "netori", "netorase", "eromanga", "incest", "stepmom", "stepdad",
        "stepsister", "stepbrother", "stepson", "stepdaughter", "ntr", "gangbang",
        "facial", "golden shower", "pegging", "rimming", "rough sex", "dirty talk",
        "sex chat", "nude pic", "lewd", "titty", "twerk", "breasts", "penis", "vagina",
        "clitoris", "genitals", "sexual", "kamasutra", "incest", "pedo", "rape", "bondage",
        "cum inside", "creampie", "sex slave", "sex doll", "sex machine", "latex", "oral sex",
        "butt", "slut", "whore", "tramp", "skank", "cumdumpster", "cultured", "ecchi", "doujin",
        "hentai", "smut", "lewd", "waifu", "futanari", "tentacle"
    ],
    "hentai": [
        "hentai", "doujinshi", "ecchi", "yaoi", "shota", "loli", "tentacle", "futanari",
        "bishoujo", "bishounen", "mecha hentai", "hentai manga", "hentai anime", "smut",
        "eroge", "visual novel", "h-manga", "h-anime", "adult manga", "18+ anime", "18+ manga",
        "lewd anime", "lewd manga", "animated porn", "animated sex", "hentai game", "hentai art",
        "hentai drawing", "hentai doujin", "yaoi hentai", "hentai comic",
        "hentai picture", "hentai scene", "hentai story", "hentai video", "hentai movie",
        "hentai episode", "hentai series"
    ],
    "abbreviations": [
        "pr0n", "s3x", "n00d", "fck", "bj", "hj", "l33t", "p0rn", "h3ntai", "h-ntai", "pnwh",
        "p0rnhwa", "l33tsp34k", "l3wd", "cultur3d", "s3xual"
    ],
    "offensive_slang": [
        "slut", "whore", "tramp", "skank", "cumdumpster", "gangbang", "facial", "golden shower",
        "pegging", "rimming", "rough sex", "dirty talk", "sex chat", "nude pic", "lewd", "titty",
        "twerk", "breasts", "penis", "vagina", "clitoris", "genitals", "sexual", "kamasutra",
        "incest", "pedo", "rape", "sex slave", "bondage", "creampie", "cum inside", "sex doll",
        "sex machine", "latex", "oral sex", "cumshot", "deepthroat", "domination", "submission",
        "handcuffs", "orgy", "roleplay", "sex toy", "voyeur", "cosplay", "adult", "culture",
        "anal", "erotic", "masturbate", "hardcore", "bdsm", "fetish", "lingerie", "milf", "taboo"
    ]
}

exception_keywords = ["nxivm", "classroom", "assassination", "geass"]

async def check_anti_nsfw(new_name: str, message) -> bool:
    """
    Vérifie si un nom de fichier contient du contenu NSFW en utilisant une liste de mots-clés.
    Si un mot-clé NSFW est trouvé, envoie un message d'avertissement.

    :param new_name: Le nom de fichier à vérifier.
    :param message: L'objet message pour répondre à l'utilisateur.
    :return: True si du contenu NSFW est détecté, False sinon.
    """
    try:
        lower_name = new_name.lower()

        for keyword in exception_keywords:
            if keyword.lower() in lower_name:
                return False  

        for category, keywords in nsfw_keywords.items():
            for keyword in keywords:
                if keyword.lower() in lower_name:
                    await message.reply_text(
                        f"⚠️ **Du contenue NSFW Detecté**\n"
                        f"Votre fichier contient du contenue pour adulte.\n"
                        f"Ce contenue sont interdit sur ce bot.\n"
                    )
                    return True 

        return False  

    except Exception as e:
        print(f"Error in check_anti_nsfw: {e}")
        return False  

# # Example usage
# import asyncio

# async def main():
#     filename = "Naruto Shippuden Ssaison01 EP07 - convertie [Dual Audio] @hyoshassistantbot.mkv"
#     season = await extract_season(filename)
#     episode = await extract_episode(filename)
#     quality = await extract_quality(filename)

#     print(f"Season: {season if season else 'Not found'}")
#     print(f"Episode: {episode if episode else 'Not found'}")
#     print(f"Quality: {quality}")

# # Run the async main function
# asyncio.run(main())