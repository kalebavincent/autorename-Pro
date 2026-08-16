
import re, os, time
from os import environ, getenv
id_pattern = re.compile(r'^.\d+$') 
from dotenv import load_dotenv
load_dotenv()


class Settings():
    
    API_HASH = os.getenv("API_HASH")
    API_ID = os.getenv("API_ID")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    DATA_URI =  os.getenv("DATA_URI")
    DATA_NAME = os.getenv("DATA_NAME")
    
    TEMP_DIR = os.environ.get("TEMP_DIR", "temp/")
    DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "downloads/")
    
    PORT = os.environ.get("PORT")
    WEBHOOK = bool(os.environ.get("WEBHOOK", "True"))
    
    BOT_UPTIME  = time.time()
    ADMIN       = [int(admin) if id_pattern.search(admin) else admin for admin in os.environ.get('ADMIN').split()]
    FORCE_SUB_CHANNELS = os.environ.get('FORCE_SUB_CHANNELS').split(',')
    CHANNEL_LOG = int(os.environ.get("CHANNEL_LOG"))
    LOG_CHANNEL = CHANNEL_LOG
    DUMP_CHANNEL = int(os.environ.get("DUMP_CHANNEL"))
    UPDATE_CHANNEL = os.environ.get("UPDATE_CHANNEL")
    SUPPORT_GROUP = os.environ.get("SUPPORT_GROUP")
    SHORTED_LINK = os.environ.get("SHORTED_LINK")
    SHORTED_LINK_API = os.environ.get("SHORTED_LINK_API")
    
    IMAGES = os.environ.get("IMAGES")
    
    # --- Points de secours ---
    BACKUP_GROUP_ID = int(os.environ.get("BACKUP_GROUP_ID", 0))
    DAILY_BACKUP_POINTS = int(os.environ.get("DAILY_BACKUP_POINTS", 70))
    
    
    
settings = Settings()