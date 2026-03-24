"""
Helix Self-Healing Client for Python
Wraps MPP payment calls with PCEC self-repair.

Usage:
    from helix.client import helix_wrap

    # Before: bare payment call
    result = tempo("/sandbox/create", data)

    # After: self-healing payment call
    result = helix_wrap(lambda: tempo("/sandbox/create", data),
                        agent_id="nanogpt-trainer",
                        platform="tempo")
"""

import requests
import time


HELIX_URL = "http://localhost:7842"


class HelixClient:
    def __init__(self, base_url=HELIX_URL, agent_id="mpp-agent", platform="tempo"):
        self.base_url = base_url
        self.agent_id = agent_id
        self.platform = platform
        self._available = None

    @property
    def available(self):
        if self._available is None:
            try:
                r = requests.get(f"{self.base_url}/health", timeout=2)
                self._available = r.status_code == 200
            except Exception:
                self._available = False
        return self._available

    def repair(self, error, context=None):
        """Send error to Helix PCEC for diagnosis + repair strategy."""
        if not self.available:
            return None

        try:
            payload = {
                "error": str(error),
                "errorType": type(error).__name__,
                "agentId": self.agent_id,
                "platform": self.platform,
                "context": context or {},
            }
            r = requests.post(
                f"{self.base_url}/repair",
                json=payload,
                timeout=5,
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[helix] sidecar unavailable: {e}")
        return None


_client = HelixClient()


def helix_wrap(fn, agent_id=None, platform="tempo", max_retries=3, context=None):
    """
    Wrap a payment function with Helix self-healing.

    If the function fails, Helix diagnoses the error and suggests
    a repair strategy. The wrapper applies the strategy and retries.

    Args:
        fn: callable that performs the payment
        agent_id: identifier for this agent
        platform: payment platform (tempo, coinbase, privy)
        max_retries: maximum repair attempts
        context: additional context for diagnosis

    Returns:
        The result of fn() after successful execution or repair

    Raises:
        The original exception if Helix cannot repair
    """
    client = _client
    if agent_id:
        client = HelixClient(agent_id=agent_id, platform=platform)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = fn()
            if attempt > 0 and client.available:
                print(f"[helix] ✅ REPAIRED on attempt {attempt + 1}")
            return result
        except Exception as e:
            last_error = e

            if not client.available:
                if attempt < max_retries:
                    time.sleep(2**attempt)
                    continue
                raise

            repair = client.repair(e, context=context)

            if repair is None:
                if attempt < max_retries:
                    time.sleep(2**attempt)
                    continue
                raise

            strategy = repair.get("strategy", {})
            strategy_name = strategy.get("name", "unknown")
            repair_ms = repair.get("repairMs", 0)
            immune = repair.get("immune", False)

            if immune:
                print(f"[helix] ⚡ IMMUNE via {strategy_name} ({repair_ms}ms)")
            else:
                print(f"[helix] 🔧 Attempting repair via {strategy_name}")

            action = strategy.get("action")
            if action == "wait_and_retry":
                wait_ms = strategy.get("params", {}).get("waitMs", 2000)
                print(f"[helix]    Waiting {wait_ms}ms before retry...")
                time.sleep(wait_ms / 1000)
            elif action == "refresh_session":
                print("[helix]    Session refresh recommended")
            elif action == "escalate":
                root = repair.get("failure", {}).get("rootCause", str(e))
                print(f"[helix]    ⚠️ Requires human intervention: {root}")
                raise

            if repair.get("failure"):
                failure = repair["failure"]
                print(
                    f"[helix]    Diagnosed: {failure.get('code', '?')} "
                    f"({failure.get('category', '?')})"
                )

    raise last_error


def helix_status():
    """Check if Helix sidecar is running and return status."""
    try:
        r = requests.get(f"{HELIX_URL}/status", timeout=2)
        if r.status_code == 200:
            data = r.json()
            print("[helix] Status: running")
            print(f"[helix] Gene Map: {data.get('geneCount', '?')} genes")
            print(f"[helix] Repairs: {data.get('totalRepairs', '?')} total")
            return data
    except Exception:
        print("[helix] Status: not running (start with: bash helix/start.sh)")
    return None
