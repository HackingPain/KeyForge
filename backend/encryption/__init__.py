"""Envelope encryption package for KeyForge.

Provides per-user data keys wrapped by a master key (two-level Fernet).
"""

from backend.encryption.envelope import EnvelopeEncryption, envelope_encryption

__all__ = ["EnvelopeEncryption", "envelope_encryption"]
