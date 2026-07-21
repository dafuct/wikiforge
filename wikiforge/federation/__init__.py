"""Cross-wiki federation: read other wikis, never write to them."""

from wikiforge.federation.fanout import Sourced, active_peers, fan_out, safe_origin
from wikiforge.federation.registry import PeerRef

__all__ = ["PeerRef", "Sourced", "active_peers", "fan_out", "safe_origin"]
