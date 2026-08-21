class MillionVerifierError(RuntimeError):
    pass


class MillionVerifierAPIError(MillionVerifierError):
    pass


class MillionVerifierTransportError(MillionVerifierError):
    pass
