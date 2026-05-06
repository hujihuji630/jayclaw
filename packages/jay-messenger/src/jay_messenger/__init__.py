"""Pig Messenger - Universal messenger abstraction library."""

from jay_messenger.base import (
    BaseMessengerAdapter,
    IncomingMessage,
    MessengerCapabilities,
    MessengerThread,
    MessengerType,
    MessengerUser,
)
from jay_messenger.config import (
    DiscordConfig,
    SlackConfig,
    TelegramConfig,
    WhatsAppConfig,
)
from jay_messenger.manager import MessengerManager, split_message
from jay_messenger.registry import MessengerRegistry
from jay_messenger.state import MessengerState
from jay_messenger.stores import (
    ConnectionStore,
    CredentialStore,
    WorkspaceAlreadyClaimedError,
    decrypt_value,
    encrypt_value,
)

__all__ = [
    # Base
    "BaseMessengerAdapter",
    "IncomingMessage",
    "MessengerCapabilities",
    "MessengerThread",
    "MessengerType",
    "MessengerUser",
    # Config
    "DiscordConfig",
    "SlackConfig",
    "TelegramConfig",
    "WhatsAppConfig",
    # Manager
    "MessengerManager",
    "split_message",
    # Registry
    "MessengerRegistry",
    # State
    "MessengerState",
    # Stores
    "ConnectionStore",
    "CredentialStore",
    "WorkspaceAlreadyClaimedError",
    "decrypt_value",
    "encrypt_value",
]

__version__ = "0.2.0"
