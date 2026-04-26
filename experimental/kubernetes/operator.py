"""
KeyForge Kubernetes Operator

A kopf-based operator that watches KeyForgeSecret custom resources and
synchronises KeyForge credentials into native Kubernetes Secrets.
"""

import base64
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import kopf
import kubernetes
from kubernetes import client as k8s_client
from kubernetes.client.rest import ApiException

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KEYFORGE_URL = os.environ.get("KEYFORGE_URL", "http://localhost:8000")
KEYFORGE_TOKEN = os.environ.get("KEYFORGE_TOKEN", "")
DEFAULT_REFRESH_INTERVAL = 60  # seconds

logger = logging.getLogger("keyforge.operator")

# ---------------------------------------------------------------------------
# KeyForge API helpers
# ---------------------------------------------------------------------------


class KeyForgeClient:
    """Thin async wrapper around the KeyForge REST API."""

    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def get_credential(self, credential_id: str) -> Dict[str, Any]:
        """Fetch a single credential by ID from the KeyForge API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self._base_url}/api/credentials/{credential_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_credentials(self, credential_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch multiple credentials, returning a dict keyed by credential ID."""
        results: Dict[str, Dict[str, Any]] = {}
        for cid in credential_ids:
            results[cid] = await self.get_credential(cid)
        return results


_kf_client: Optional[KeyForgeClient] = None


def _get_keyforge_client() -> KeyForgeClient:
    global _kf_client
    if _kf_client is None:
        _kf_client = KeyForgeClient(KEYFORGE_URL, KEYFORGE_TOKEN)
    return _kf_client


# ---------------------------------------------------------------------------
# Kubernetes helpers
# ---------------------------------------------------------------------------


def _load_kube_config() -> k8s_client.CoreV1Api:
    """Load in-cluster config (or fall back to kubeconfig for local dev)."""
    try:
        kubernetes.config.load_incluster_config()
    except kubernetes.config.ConfigException:
        kubernetes.config.load_kube_config()
    return k8s_client.CoreV1Api()


def _build_secret(
    name: str,
    namespace: str,
    data: Dict[str, str],
    owner_ref: Optional[Dict[str, Any]] = None,
) -> k8s_client.V1Secret:
    """Construct a V1Secret object from plain-text key/value pairs."""
    labels = {
        "app.kubernetes.io/managed-by": "keyforge-operator",
    }
    metadata = k8s_client.V1ObjectMetadata(
        name=name,
        namespace=namespace,
        labels=labels,
    )
    if owner_ref:
        metadata.owner_references = [
            k8s_client.V1OwnerReference(
                api_version="keyforge.io/v1alpha1",
                kind="KeyForgeSecret",
                name=owner_ref["name"],
                uid=owner_ref["uid"],
                block_owner_deletion=True,
                controller=True,
            )
        ]
    return k8s_client.V1Secret(
        api_version="v1",
        kind="Secret",
        metadata=metadata,
        type="Opaque",
        string_data=data,
    )


def _upsert_secret(
    core_api: k8s_client.CoreV1Api,
    name: str,
    namespace: str,
    data: Dict[str, str],
    owner_ref: Optional[Dict[str, Any]] = None,
) -> None:
    """Create or update a Kubernetes Secret."""
    secret = _build_secret(name, namespace, data, owner_ref)
    try:
        core_api.read_namespaced_secret(name, namespace)
        # Secret exists -- update it
        core_api.replace_namespaced_secret(name, namespace, secret)
        logger.info("Updated Secret %s/%s", namespace, name)
    except ApiException as exc:
        if exc.status == 404:
            core_api.create_namespaced_secret(namespace, secret)
            logger.info("Created Secret %s/%s", namespace, name)
        else:
            raise


def _delete_secret(
    core_api: k8s_client.CoreV1Api,
    name: str,
    namespace: str,
) -> None:
    """Delete a Kubernetes Secret if it exists."""
    try:
        core_api.delete_namespaced_secret(name, namespace)
        logger.info("Deleted Secret %s/%s", namespace, name)
    except ApiException as exc:
        if exc.status == 404:
            logger.info("Secret %s/%s already absent", namespace, name)
        else:
            raise


# ---------------------------------------------------------------------------
# Credential-to-Secret data mapping
# ---------------------------------------------------------------------------


def _map_credentials(
    credentials: Dict[str, Dict[str, Any]],
    key_mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Convert fetched KeyForge credentials into a flat dict suitable for a
    Kubernetes Secret's ``stringData``.

    Each credential is stored under a key derived from its ``api_name`` field
    (lower-cased, spaces replaced with underscores).  ``key_mapping`` allows
    callers to override the key name for a given credential ID.
    """
    data: Dict[str, str] = {}
    for cred_id, cred in credentials.items():
        # Determine the key name
        if key_mapping and cred_id in key_mapping:
            key = key_mapping[cred_id]
        else:
            api_name: str = cred.get("api_name", cred_id)
            key = api_name.lower().replace(" ", "_").replace("-", "_")

        # Use the credential value (api_key or api_key_preview as fallback)
        value = cred.get("api_key", cred.get("api_key_preview", ""))
        data[key] = value

    return data


# ---------------------------------------------------------------------------
# Sync logic (shared between create/update/timer handlers)
# ---------------------------------------------------------------------------


async def _sync(
    spec: Dict[str, Any],
    name: str,
    namespace: str,
    uid: str,
    patch: kopf.Patch,
    **_: Any,
) -> str:
    """Core sync routine used by all handlers."""
    credential_ids: List[str] = spec.get("credentialIds", [])
    secret_name: str = spec.get("secretName", name)
    target_ns: str = spec.get("namespace", namespace)
    key_mapping: Optional[Dict[str, str]] = spec.get("keyMapping")

    kf = _get_keyforge_client()
    core_api = _load_kube_config()

    try:
        credentials = await kf.get_credentials(credential_ids)
        data = _map_credentials(credentials, key_mapping)
        owner_ref = {"name": name, "uid": uid}
        _upsert_secret(core_api, secret_name, target_ns, data, owner_ref)

        now = datetime.now(timezone.utc).isoformat()
        patch.status["synced"] = True
        patch.status["lastSyncTime"] = now
        patch.status["error"] = ""
        return f"Synced {len(credential_ids)} credential(s) into Secret {target_ns}/{secret_name}"

    except httpx.HTTPStatusError as exc:
        msg = f"KeyForge API error: {exc.response.status_code} {exc.response.text[:200]}"
        logger.error(msg)
        patch.status["synced"] = False
        patch.status["error"] = msg
        raise kopf.TemporaryError(msg, delay=30)

    except ApiException as exc:
        msg = f"Kubernetes API error: {exc.status} {exc.reason}"
        logger.error(msg)
        patch.status["synced"] = False
        patch.status["error"] = msg
        raise kopf.TemporaryError(msg, delay=30)

    except Exception as exc:
        msg = f"Unexpected error: {exc}"
        logger.exception(msg)
        patch.status["synced"] = False
        patch.status["error"] = msg
        raise kopf.TemporaryError(msg, delay=60)


# ---------------------------------------------------------------------------
# Kopf handlers
# ---------------------------------------------------------------------------


@kopf.on.create("keyforge.io", "v1alpha1", "keyforgesecrets")
async def on_create(spec, name, namespace, uid, patch, **kwargs):
    """Handle creation of a KeyForgeSecret CR."""
    logger.info("KeyForgeSecret created: %s/%s", namespace, name)
    return await _sync(spec, name, namespace, uid, patch)


@kopf.on.update("keyforge.io", "v1alpha1", "keyforgesecrets")
async def on_update(spec, name, namespace, uid, patch, **kwargs):
    """Handle updates to a KeyForgeSecret CR."""
    logger.info("KeyForgeSecret updated: %s/%s", namespace, name)
    return await _sync(spec, name, namespace, uid, patch)


@kopf.on.delete("keyforge.io", "v1alpha1", "keyforgesecrets")
async def on_delete(spec, name, namespace, **kwargs):
    """Clean up the managed Secret when the CR is deleted."""
    logger.info("KeyForgeSecret deleted: %s/%s", namespace, name)
    secret_name = spec.get("secretName", name)
    target_ns = spec.get("namespace", namespace)

    core_api = _load_kube_config()
    _delete_secret(core_api, secret_name, target_ns)
    return f"Deleted Secret {target_ns}/{secret_name}"


@kopf.timer("keyforge.io", "v1alpha1", "keyforgesecrets", interval=60, initial_delay=30)
async def reconcile(spec, name, namespace, uid, patch, **kwargs):
    """
    Periodic reconciliation to catch drift.

    The interval is fixed at 60 s at the handler level; per-resource
    ``spec.refreshInterval`` can be respected by skipping early if the last
    sync was recent enough.
    """
    refresh = spec.get("refreshInterval", DEFAULT_REFRESH_INTERVAL)

    # Quick drift check: skip if last sync was within refreshInterval
    status = kwargs.get("status", {})
    last_sync = status.get("lastSyncTime")
    if last_sync:
        try:
            last_dt = datetime.fromisoformat(last_sync)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
            if elapsed < refresh:
                logger.debug(
                    "Skipping reconcile for %s/%s - last sync %ds ago (interval %ds)",
                    namespace,
                    name,
                    int(elapsed),
                    refresh,
                )
                return
        except (ValueError, TypeError):
            pass  # fall through to sync

    logger.info("Reconciling KeyForgeSecret %s/%s", namespace, name)
    return await _sync(spec, name, namespace, uid, patch)


# ---------------------------------------------------------------------------
# Health-check endpoint (for liveness/readiness probes)
# ---------------------------------------------------------------------------


@kopf.on.probe(id="healthz")
def health_check(**kwargs):
    """Return health status for Kubernetes probes."""
    return {"status": "healthy"}


# ---------------------------------------------------------------------------
# Startup hook
# ---------------------------------------------------------------------------


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    """Tweak kopf operator settings on startup."""
    settings.posting.level = logging.WARNING
    settings.persistence.finalizer = "keyforge.io/operator-finalizer"
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage(
        prefix="keyforge.io",
    )
    logger.info(
        "KeyForge operator starting - API at %s, token %s",
        KEYFORGE_URL,
        "configured" if KEYFORGE_TOKEN else "NOT SET",
    )
