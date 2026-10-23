"""
Provider-neutral errors. Messages are written for API clients: they never
include credentials, request URLs or raw provider payloads.
"""


class ProviderError(Exception):
    code = "provider_error"
    message = "The external data provider failed."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.message)
        self.message = message or self.message


class ProviderNotConfigured(ProviderError):
    code = "provider_not_configured"
    message = "The routing provider is not configured on the server."


class ProviderAuthFailed(ProviderError):
    code = "provider_auth_failed"
    message = "The routing provider rejected the server's credentials."


class ProviderRateLimited(ProviderError):
    code = "provider_rate_limited"
    message = "The routing provider's rate limit was reached. Please try again shortly."


class ProviderTimeout(ProviderError):
    code = "provider_timeout"
    message = "The routing provider did not respond in time. Please try again."


class ProviderUnavailable(ProviderError):
    code = "provider_unavailable"
    message = "The routing provider is currently unavailable. Please try again later."


class ProviderBadResponse(ProviderError):
    code = "provider_bad_response"
    message = "The routing provider returned an unexpected response."


class NoRouteFound(ProviderError):
    code = "no_route_found"
    message = "No drivable route was found between these locations."


class ProviderRejectedRequest(ProviderError):
    code = "provider_rejected_request"
    message = "The routing provider could not process this request."
