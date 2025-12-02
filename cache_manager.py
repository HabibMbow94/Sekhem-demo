# cache_manager.py
from __future__ import annotations
import os
from typing import Callable, Iterable, Optional
from diskcache import Cache


class CacheManager:
    """
    Enveloppe simple autour de diskcache.Cache avec :
      - TTL par défaut configurable
      - Génération de clés cohérentes (namespace | name | parts…)
      - getset(key, compute_fn, expire) pratique
      - purge par 'scope' (département + période)
    """

    def __init__(
        self,
        dir: Optional[str] = None,
        default_ttl: int = 7200,  # 2h
        namespace: str = "SEKHEM",
    ) -> None:
        self.dir = dir or os.environ.get("SEKHEM_CACHE_DIR", ".sekhem_cache")
        self.default_ttl = int(
            os.environ.get("SEKHEM_CACHE_TTL", str(default_ttl))
        )
        self.namespace = namespace
        self._cache = Cache(self.dir)

    # -----------------------------
    # Config
    # -----------------------------
    def set_ttl(self, seconds: int) -> None:
        self.default_ttl = int(seconds)

    # -----------------------------
    # Key building
    # -----------------------------
    def make_key(self, name: str, parts: Optional[Iterable[str]] = None) -> str:
        segs = [self.namespace, name.strip()]
        if parts:
            segs.extend(str(p).strip() for p in parts)
        # Séparateur constant pour permettre startswith()
        return "|".join(segs)

    def key_context(
        self,
        name: str,
        dpt: str,
        begin: str,
        end: str,
        extra: Optional[str] = None,
    ) -> str:
        parts = [f"dpt={dpt}", f"b={begin}", f"e={end}"]
        if extra:
            parts.append(f"x={extra}")
        return self.make_key(name, parts)

    # -----------------------------
    # Get / Set
    # -----------------------------
    def getset(
        self,
        key: str,
        compute_fn: Callable[[], object],
        expire: Optional[int] = None,
    ):
        """
        Tente un get() ; sinon compute_fn(), puis set() avec TTL.
        Sérialise automatiquement (pickle).
        """
        val = self._cache.get(key, default=None)
        if val is not None:
            return val
        val = compute_fn()
        try:
            self._cache.set(key, val, expire=expire or self.default_ttl)
        except Exception:
            # on ne casse pas l'exécution si l'écriture échoue
            pass
        return val

    # -----------------------------
    # Clear helpers
    # -----------------------------
    def clear_prefix(self, prefix: str) -> int:
        """
        Supprime toutes les entrées dont la clé commence par 'prefix'.
        Retourne le nombre d'entrées supprimées.
        """
        count = 0
        # iterkeys() -> toutes les clés, on filtre par startswith
        for k in list(self._cache.iterkeys()):
            if isinstance(k, str) and k.startswith(prefix):
                try:
                    del self._cache[k]
                    count += 1
                except Exception:
                    pass
        return count

    def clear_context(self, dpt: str, begin: str, end: str) -> int:
        """
        Purge tout le cache lié au département + période.
        """
        # On génère un 'préfixe de scope' stable
        scope_prefix = self.make_key(
            "", [f"dpt={dpt}", f"b={begin}", f"e={end}"]
        ).rstrip("|")
        return self.clear_prefix(scope_prefix)

    # -----------------------------
    # Lifecycle
    # -----------------------------
    def close(self) -> None:
        try:
            self._cache.close()
        except Exception:
            pass
