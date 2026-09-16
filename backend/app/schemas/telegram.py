"""Subconjunto del modelo de datos de Telegram.

Solo se declaran los campos que Silu usa. `extra="ignore"` es deliberado aquí,
al revés que en los esquemas propios: Telegram agrega campos con frecuencia y
un campo nuevo no debe hacer fallar el webhook.
"""

from pydantic import BaseModel, ConfigDict, Field


class TelegramUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    first_name: str | None = None
    username: str | None = None


class TelegramChat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int


class TelegramVoice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file_id: str
    duration: int | None = None
    mime_type: str | None = None


class TelegramAudio(TelegramVoice):
    """Un audio enviado como archivo, no como nota de voz."""

    file_name: str | None = None


class TelegramMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    message_id: int
    chat: TelegramChat
    # Telegram manda el remitente en "from", que es palabra reservada en Python.
    from_user: TelegramUser | None = Field(default=None, alias="from")
    text: str | None = None
    caption: str | None = None
    voice: TelegramVoice | None = None
    audio: TelegramAudio | None = None

    @property
    def audio_file_id(self) -> str | None:
        """El file_id del audio, venga como nota de voz o como archivo."""
        media = self.voice or self.audio
        return media.file_id if media else None

    @property
    def plain_text(self) -> str | None:
        text = self.text or self.caption
        return text.strip() if text and text.strip() else None


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    update_id: int
    message: TelegramMessage | None = None
    edited_message: TelegramMessage | None = None

    @property
    def effective_message(self) -> TelegramMessage | None:
        return self.message or self.edited_message
