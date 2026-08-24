from pyrogram.types import InlineKeyboardButton as PyroButton

try:
    from pyrogram.enums import ButtonStyle
except ImportError:
    class ButtonStyle:
        PRIMARY = "primary"
        SUCCESS = "success"
        DANGER = "danger"
        DEFAULT = "default"


class Button(PyroButton):
    def __init__(
        self,
        text,
        callback_data=None,
        url=None,
        web_app=None,
        login_url=None,
        user_id=None,
        switch_inline_query=None,
        switch_inline_query_current_chat=None,
        callback_game=None,
        requires_password=None,
        pay=None,
        copy_text=None,
        icon_custom_emoji_id=None,
        style=None,
    ):
        text = str(text)

        if style is None:
            lower_text = text.lower()
            words = lower_text.split()
            if any(x in lower_text for x in ["❌", "✖️", "⬅️", "stop", "fermer", "retour", "annuler", "supprimer", "close", "cancel", "delete", "ban", "back"]):
                style = ButtonStyle.DANGER
            elif any(x in lower_text for x in ["✓", "✅", "success", "done", "active", "premium", "vip", "joined"]) or any(w in words for w in ["on", "active", "yes", "oui"]):
                style = ButtonStyle.SUCCESS
            elif any(x in lower_text for x in ["◀", "▶", "aide", "options", "paramètres", "parametres", "stats", "statut", "help", "about", "info", "settings", "preview"]):
                style = ButtonStyle.DEFAULT
            else:
                style = ButtonStyle.PRIMARY

        kwargs = {}
        if callback_data is not None:
            kwargs["callback_data"] = callback_data
        if url is not None:
            kwargs["url"] = url
        if web_app is not None:
            kwargs["web_app"] = web_app
        if login_url is not None:
            kwargs["login_url"] = login_url
        if user_id is not None:
            kwargs["user_id"] = user_id
        if switch_inline_query is not None:
            kwargs["switch_inline_query"] = switch_inline_query
        if switch_inline_query_current_chat is not None:
            kwargs["switch_inline_query_current_chat"] = switch_inline_query_current_chat
        if callback_game is not None:
            kwargs["callback_game"] = callback_game
        if requires_password is not None:
            kwargs["requires_password"] = requires_password
        if pay is not None:
            kwargs["pay"] = pay

        super().__init__(text, **kwargs)
        self.style = style
        self.icon_custom_emoji_id = icon_custom_emoji_id
