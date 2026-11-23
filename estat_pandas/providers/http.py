import time

import requests

from ..errors import ProviderError


def get_response(url, params, timeout, provider, retry_count=1, session=None):
    client = session or requests
    for attempt in range(retry_count + 1):
        try:
            response = client.get(url, params=params, timeout=timeout)
        except requests.RequestException as error:
            if attempt < retry_count:
                time.sleep(0.25 * (attempt + 1))
                continue
            raise ProviderError(
                f"{provider} request failed ({type(error).__name__})"
            ) from error

        if response.status_code >= 500 and attempt < retry_count:
            time.sleep(0.25 * (attempt + 1))
            continue
        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderError(
                f"{provider} request failed with HTTP {response.status_code}"
            )
        return response

    raise ProviderError(f"{provider} request failed after retries")


def get_json(url, params, timeout, provider, retry_count=1, session=None):
    response = get_response(
        url,
        params,
        timeout,
        provider,
        retry_count=retry_count,
        session=session,
    )
    try:
        payload = response.json()
    except ValueError as error:
        raise ProviderError(f"{provider} returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise ProviderError(f"{provider} response must be a JSON object")
    return payload

